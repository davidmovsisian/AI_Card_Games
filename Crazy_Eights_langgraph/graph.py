"""LangGraph orchestration for Crazy Eights.

Every player is a node. A run of the graph always ends at a clean resting point:
the game is over, or it is a human's turn (including a human who still has to
declare a suit after drawing an 8). Human input is passed in as `human_move`
when the graph is invoked, so no interrupts are needed:

    START ──► (entry router) ──► setup ──► (router) ──► player_i ──► (router) ──► player_j …
                                                                         └──────────► END

The router sends the run to the next player's node, or to END when the game is
over or it is a human's turn.
"""
from typing import Awaitable, Callable, List, Optional, Tuple, TypedDict
from langgraph.graph import END, START, StateGraph
import engine
from engine import GameState
from ai_player import AIMoveDecision

AIChooser = Callable[..., Awaitable[Optional[AIMoveDecision]]]

class GraphState(TypedDict, total = False):
    game: dict                      # GameState.model_dump(), plain dict, because the checkpointer has to serialize it
    human_move: Optional[dict]      # {"player", "action": "play"|"draw"|"declare", ...}; consumed by a human node
    last_event: Optional[dict]      # what the most recent node did (streamed to the client)

def node_name(index : int) -> str:
    return f"player_{index}"

# ── events ────────────────────────────────────────────────────────────────────

def _event(type: str, player: Optional[str], text: str, g: GameState, **extra) -> dict:
    return {"type": type, "player": player, "text": text, "state": engine.summarize(g), **extra}

def _draw_event(name: str, g: GameState, res: engine.DrawResult, banter: Optional[str] = None) -> dict:
    labels = ", ".join(c.label for c in res.drawn)
    if res.passed:
        text = (f"{name} drew {labels} but nothing was playable — turn skipped." 
        if res.drawn else f"{name} could not draw (no cards left) — turn skipped.")
    elif res.awaiting_suit:
        text = f"{name} drew {labels} and played 8 — choosing a suit…"
    elif res.declared_suit:
        text = f"{name} drew {labels}, played the 8 and changed the suit to {res.declared_suit}."
    else:
        text = f"{name} drew {labels} and played {res.played.label}."

    return _event(
        "draw", name, text, g,
        drawn_cards=[c.to_dict() for c in res.drawn],
        played=res.played.to_dict() if res.played else None,
        awaiting_suit=res.awaiting_suit,
        declared_suit=res.declared_suit,
        banter=banter,
    )

def _play_event(name: str, g: GameState, card: engine.Card, suit: Optional[str], banter: Optional[str] = None) -> dict:
    text = f"{name} played {card.label}"
    if suit:
        text += f" and changed the suit to {suit}."
    return _event("play", name, text, g, card=card.to_dict(), declared_suit=suit, banter=banter)

# ── nodes ─────────────────────────────────────────────────────────────────────

async def setup_node(state: GraphState) -> dict:
    g = GameState.model_validate(state["game"])
    engine.deal(g)
    return{
        "game": g.model_dump(),
        "last_event": _event("deal", None, f"Cards dealt. The top card is {g.top_card.label}.", g)
    }

def make_human_node(name: str):
    async def human_node(state: GraphState) -> dict:
        g = GameState.model_validate(state["game"])
        move = state.get("human_move") or {}
        try:
            if move.get("player") != name:
                raise ValueError(f"It is not {move.get('player')}'s turn." if move.get("player") else "No move was provided.")
            action = move.get("action")

            if g.pending_suit_player == name:
                if action != "declare":
                    raise ValueError("You must declare a suit for the 8 you drew first.")
                suit = move.get("suit")
                engine.declare_suit(g, name, suit)
                event = _event("declare", name, f"{name} declared {suit}", g, declared_suit=suit)
            elif action == "play":
                suit = move.get("declared_suit")
                card = engine.play_card(g, name, move.get("card_index"), suit)
                event = _play_event(name, g, card, suit if card.rank == '8' else None)
            elif action == "draw":
                res = engine.draw_until_playable(g, name, auto_declare=False)
                event = _draw_event(name, g, res)
            else:
                raise ValueError(f"Unknown action: {action!r}")
        except(ValueError, TypeError) as exc:
            return {"human_move": None, "last_event": {"type": "error", "player": name, "text": str(exc)}}
        return {"game": g.model_dump(), "human_move": None, "last_event": event}

    return human_node

def make_ai_node(name: str, ai_chooser: AIChooser) -> dict:
    async def ai_node(state: GraphState):
        g = GameState.model_validate(state["game"])
        legal = engine.legal_moves(g, name)

        if not legal:
            res = engine.draw_until_playable(g, name, auto_declare=True)
            return {"game": g.model_dump(), "last_event": _draw_event(name, g, res)}

        chosen, suit, banter = legal[0], None, None   # fallback: first legal card
        try:
            decision = await ai_chooser(
                ai_hand=[c.to_dict() for c in g.players[name].hand],
                legal_indices=legal,
                top_card=g.top_card.to_dict(),
                active_suit=g.active_suit,
                house_rules=g.house_rules,
            )
        except Exception:
            decision = None                    # API failure -> fall back to a legal move

        if decision is not None:
            # Comments only exist when the players set house rules, whatever the model returned
            comment = (decision.roleplay_comment or "").strip()
            banter = comment if comment and g.house_rules.strip() else None
            if decision.chosen_index in legal:
                chosen, suit = decision.chosen_index, decision.declared_suit

        card = g.players[name].hand[chosen]
        if card.rank == '8':
            if suit not in engine.SUITS:
                suit = engine.best_suit([c for i, c in enumerate(g.players[name].hand) if i != chosen ])
        else:
            suit = None

        engine.play_card(g, name, chosen, suit)

        return {"game": g.model_dump(), "last_event": _play_event(name, g, card, suit, banter)}

    return ai_node

# ── graph assembly ────────────────────────────────────────────────────────────

def build_graph(players: List[Tuple[str, str]], checkpointer=None, ai_chooser: Optional[AIChooser] = None):
    """Compile the game graph for a fixed roster of (name, player_type) pairs, in turn order."""
    if ai_chooser is None:
        from ai_player import choose_move
        ai_chooser = choose_move

    names = [n for n, _ in players]
    is_human = {n: t=='human' for n, t in players}
    node_of = {n: node_name(i) for i, n in enumerate(names)} #{name: player_1}

    def current_name(game: dict) -> str:
        return names[game["current_turn_index"]]
    
    def entry_root(state: GraphState):
        game = state["game"]
        if not game["started"]:
            return "setup"
        if game["game_over"]:
            return END
        return node_of[current_name(game)]            # a human's node consumes `human_move`

    def router(state: GraphState):
        game = state["game"]
        if game["game_over"]:
            return END
        who = current_name(game)
        if game["pending_suit_player"] or is_human[who]: 
            return END                  # rest here until the human acts
        return node_of[who]             # ai node

    path_map ={"setup": "setup", **{v: v for v in node_of.values()}, END: END}

    builder = StateGraph(GraphState)
    builder.add_node("setup", setup_node)
    for name in names:
        node = make_human_node(name) if is_human[name] else make_ai_node(name, ai_chooser)
        builder.add_node(node_of[name], node)

    builder.add_conditional_edges(START, entry_root, path_map)
    for current_node in ["setup", *node_of.values()]:
        builder.add_conditional_edges(current_node, router, path_map)

    return builder.compile(checkpointer=checkpointer)