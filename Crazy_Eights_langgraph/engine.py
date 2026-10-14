"""Crazy Eights rules engine.

Pure, serializable game logic. `GameState` is a plain Pydantic model, so it can be
dumped to a dict and stored in a LangGraph checkpoint. All rule functions mutate a
`GameState` in place and raise ValueError for illegal actions; callers (graph nodes)
work on a deep copy.
"""
import random
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'K', 'Q', 'A']
SUIT_SYMBOL = {'Hearts': '♥', 'Diamonds': '♦', 'Clubs': '♣', 'Spades': '♠'}


class Card(BaseModel):
    suit: str
    rank: str

    @property
    def label(self) -> str:
        return f"{self.rank}{SUIT_SYMBOL[self.suit]}"

    def __str__(self) -> str:
        return f"{self.rank} of {self.suit}"

    def to_dict(self) -> dict:
        return {"suit": self.suit, "rank": self.rank}


class Player(BaseModel):
    name: str
    player_type: str = "human"          # "human" | "ai"
    hand: List[Card] = Field(default_factory=list)


class GameState(BaseModel):
    players: Dict[str, Player] = Field(default_factory=dict)
    player_order: List[str] = Field(default_factory=list)
    house_rules: str = ""
    current_turn_index: int = 0
    draw_pile: List[Card] = Field(default_factory=list)
    discard_pile: List[Card] = Field(default_factory=list)
    declared_suit: Optional[str] = None
    started: bool = False
    winner: Optional[str] = None
    game_over: bool = False
    pending_suit_player: Optional[str] = None   # human who drew a playable 8 and must declare a suit

    # ── derived values ────────────────────────────────────────────────────────

    @property
    def current_player_name(self) -> str:
        return self.player_order[self.current_turn_index]

    @property
    def top_card(self) -> Optional[Card]:
        return self.discard_pile[-1] if self.discard_pile else None

    @property
    def active_suit(self) -> Optional[str]:
        return self.declared_suit if self.declared_suit else (self.top_card.suit if self.top_card else None)


class DrawResult(BaseModel):
    drawn: List[Card] = Field(default_factory=list)
    played: Optional[Card] = None          # the drawn card that was played, if any
    awaiting_suit: bool = False            # a human drew a playable 8 and must now declare a suit
    declared_suit: Optional[str] = None    # suit chosen automatically (AI draws an 8)
    passed: bool = False                   # nothing playable could be drawn; turn skipped


# ── setup ─────────────────────────────────────────────────────────────────────

def new_game(players: List[tuple], house_rules: str = "") -> GameState:
    """players: list of (name, player_type). The game is created undealt."""
    g = GameState(house_rules=house_rules)
    for name, ptype in players:
        if name in g.players:
            raise ValueError(f"Duplicate player name: {name}")
        g.players[name] = Player(name=name, player_type=ptype)
        g.player_order.append(name)
    return g


def deal(g: GameState) -> None:
    if g.started:
        raise ValueError("Game already started.")
    if len(g.players) < 2:
        raise ValueError("At least two players are required.")
    g.started = True

    deck = [Card(suit=s, rank=r) for s in SUITS for r in RANKS]
    random.shuffle(deck)

    # 7 cards each for two players, otherwise 8
    cards_each = 7 if len(g.players) == 2 else 8
    for _ in range(cards_each):
        for p in g.players.values():
            p.hand.append(deck.pop())

    g.draw_pile = deck

    # The starting card must not be an 8: bury any 8 at the bottom, reshuffle, flip again
    initial = g.draw_pile.pop()
    while initial.rank == '8':
        g.draw_pile.insert(0, initial)
        random.shuffle(g.draw_pile)
        initial = g.draw_pile.pop()
    g.discard_pile = [initial]
    g.declared_suit = None


# ── queries ───────────────────────────────────────────────────────────────────

def is_playable(g: GameState, card: Card) -> bool:
    if card.rank == '8':
        return True
    return card.suit == g.active_suit or card.rank == g.top_card.rank


def legal_moves(g: GameState, player_name: str) -> List[int]:
    """Indices (into the player's hand) of every card that can be played now."""
    return [i for i, c in enumerate(g.players[player_name].hand) if is_playable(g, c)]


def best_suit(cards: List[Card]) -> str:
    """Most common suit among non-8 cards (ties / empty -> random among the best)."""
    counts = {s: 0 for s in SUITS}
    for c in cards:
        if c.rank != '8':
            counts[c.suit] += 1
    top = max(counts.values())
    return random.choice([s for s in SUITS if counts[s] == top])


# ── internals ─────────────────────────────────────────────────────────────────

def _advance_turn(g: GameState) -> None:
    g.current_turn_index = (g.current_turn_index + 1) % len(g.player_order)


def _recycle_discard_pile(g: GameState) -> bool:
    """Shuffle all but the top discard back into the draw pile."""
    if len(g.discard_pile) <= 1:
        return False
    top = g.discard_pile.pop()
    g.draw_pile = g.discard_pile
    random.shuffle(g.draw_pile)
    g.discard_pile = [top]
    return True


def _ensure_can_act(g: GameState, player_name: str) -> None:
    if g.game_over:
        raise ValueError("The game is already over.")
    if g.pending_suit_player:
        raise ValueError("A suit must be declared for the drawn 8 first.")
    if player_name != g.current_player_name:
        raise ValueError("It's not this player's turn.")


# ── actions ───────────────────────────────────────────────────────────────────

def play_card(g: GameState, player_name: str, card_index: int, declared_suit: Optional[str] = None) -> Card:
    _ensure_can_act(g, player_name)
    player = g.players[player_name]

    if card_index < 0 or card_index >= len(player.hand):
        raise ValueError("Card index out of range.")

    card = player.hand[card_index]
    if not is_playable(g, card):
        raise ValueError(f"Cannot play {card} on top of {g.top_card} (Active suit: {g.active_suit})")
    if card.rank == '8' and declared_suit not in SUITS:
        raise ValueError("Must declare a valid suit (Hearts, Diamonds, Clubs, Spades) when playing an 8.")

    player.hand.pop(card_index)
    g.discard_pile.append(card)
    g.declared_suit = declared_suit if card.rank == '8' else None

    if not player.hand:
        g.winner = player_name
        g.game_over = True
        return card

    _advance_turn(g)
    return card


def draw_until_playable(g: GameState, player_name: str, auto_declare: bool = False) -> DrawResult:
    """Draw until a playable card appears, and play it.

    If that card is an 8: with auto_declare=True (AI players) the suit is chosen
    automatically; otherwise the turn stays with the player until declare_suit().
    """
    _ensure_can_act(g, player_name)
    player = g.players[player_name]
    if legal_moves(g, player_name):
        raise ValueError("You have a playable card; you may only draw when you have none.")

    result = DrawResult()
    while True:
        if not g.draw_pile and not _recycle_discard_pile(g):
            # Practically unreachable (needs all 51 other cards in hands): avoid a crash
            result.passed = True
            _advance_turn(g)
            return result

        card = g.draw_pile.pop()
        result.drawn.append(card)

        if not is_playable(g, card):
            player.hand.append(card)
            continue

        g.discard_pile.append(card)
        result.played = card
        if card.rank == '8':
            if auto_declare:
                g.declared_suit = best_suit(player.hand)
                result.declared_suit = g.declared_suit
            else:
                g.declared_suit = None
                g.pending_suit_player = player_name
                result.awaiting_suit = True
                return result          # turn does not advance yet
        else:
            g.declared_suit = None
        _advance_turn(g)
        return result


def declare_suit(g: GameState, player_name: str, suit: str) -> None:
    """Finish a human's turn after they drew a playable 8."""
    if g.game_over:
        raise ValueError("The game is already over.")
    if g.pending_suit_player != player_name:
        raise ValueError("No suit declaration is pending for this player.")
    if suit not in SUITS:
        raise ValueError("Must declare a valid suit (Hearts, Diamonds, Clubs, Spades).")
    g.declared_suit = suit
    g.pending_suit_player = None
    _advance_turn(g)


# ── public view ───────────────────────────────────────────────────────────────

def summarize(g: GameState) -> dict:
    """The state as sent to clients. Human hands are shown, AI hands are hidden."""
    return {
        "current_player": g.current_player_name,
        "top_card": g.top_card.to_dict(),
        "active_suit": g.active_suit,
        "winner": g.winner,
        "game_over": g.game_over,
        "pending_suit_player": g.pending_suit_player,
        "players": {
            name: {
                "type": p.player_type,
                "hand_count": len(p.hand),
                "hand": [c.to_dict() for c in p.hand] if p.player_type == "human" else "HIDDEN",
            }
            for name, p in g.players.items()
        },
    }
