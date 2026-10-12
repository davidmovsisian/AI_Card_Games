from uuid import uuid4
import json
from fastapi import FastAPI, HTTPException
import uvicorn
from typing import Dict
from pathlib import Path
from engine import GameEngine
# from ai_service import AIService
from ai_service import choose_move
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models import (
    CreateGameRequest,
    JoinGameRequest,
    PlayCardRequest,
    GameStateSummary,
    CardModel,
    PlayerModel
)

app = FastAPI(title="Crazy Eights AI Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ai_service = AIService()
FRONTEND_DIR = Path(__file__).parent / "frontend"
if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

ACTIVE_GAMES: Dict[str, GameEngine] = {}
SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']

@app.get("/", include_in_schema=False)
async def frontend_root():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.post("/game/create")
async def create_game(req: CreateGameRequest):
    engine = GameEngine(house_rules=req.house_rules)
    game_id = uuid4().hex
    ACTIVE_GAMES[game_id] = engine
    
    return {"status": "Game created", "game_id": game_id}

@app.get("/game/{game_id}/state")
def get_state(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = ACTIVE_GAMES[game_id]
    if not game:
        raise HTTPException(status_code=400, detail="Game not initialized. Call /start first.")
    
    if not game.players:
        raise HTTPException(status_code=400, detail="No players have joined the game yet.")
    return get_game_state_summary('state', game, game.current_player_name)

@app.post("/game/{game_id}/join_game")
async def join_game(game_id: str, req: JoinGameRequest):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    
    engine = ACTIVE_GAMES[game_id]
    if req.player_name in engine.players:
        raise HTTPException(status_code=400, detail="Player name already taken.")
    
    engine.add_player(req.player_name, player_type=req.player_type)
        
    return {"status": f"{req.player_name} joined the game."}

@app.post("/game/{game_id}/start")
async def start_game(game_id: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    
    game = ACTIVE_GAMES[game_id]
    if len(game.players) < 2:
        game.add_player("AI_Opponent", player_type="ai")  # Add an AI opponent if only one human player

    try:
        game.initialize_game()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "status": "Game started",
        "state": get_game_state_summary('start', game)
    }

@app.post("/game/{game_id}/play")
async def play_card(game_id: str, payload: PlayCardRequest):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    
    game = ACTIVE_GAMES[game_id]
    if not game:
        raise HTTPException(status_code=400, detail="Game not initialized.")
    if game.current_player_name != payload.player_name:
        raise HTTPException(status_code=400, detail=f"It is not {payload.player_name}'s turn.")

    try:
        game.play_card(payload.player_name, payload.card_index, payload.declared_suit)
        return {
            "message": "Card played successfully.", 
            "state": get_game_state_summary('play', game, payload.player_name)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/game/{game_id}/draw")
def draw_card(game_id: str, player_name: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = ACTIVE_GAMES[game_id]
    if not game:
        raise HTTPException(status_code=400, detail="Game not initialized.")
    if game.current_player_name != player_name:
        raise HTTPException(status_code=400, detail=f"It is not {player_name}'s turn.")

    try:
        auto = game.players[player_name].player_type == "ai"
        drawn_cards = game.draw_until_playable(player_name, auto_declare=auto)
        return {
            "message": "Drawing process complete.",
            "drawn_cards": drawn_cards,
            "awaiting_suit": game.pending_suit_player == player_name,
            "state": get_game_state_summary('draw', game, player_name)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/game/{game_id}/declare_suit")
async def declare_suit(game_id: str, player_name: str, suit: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = ACTIVE_GAMES[game_id]

    try:
        game.declare_suit(player_name, suit)
    except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return{
        "message": f"player {player_name} declared suit {suit}",
        "state": get_game_state_summary("declare_suit", game, player_name)
    }
        
@app.post("/game/{game_id}/ai-turn")
async def ai_turn(game_id: str, ai_player_name: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = ACTIVE_GAMES[game_id]
    if not game:
        raise HTTPException(status_code=400, detail="Game not initialized.")
    if game.current_player_name != ai_player_name:
        raise HTTPException(status_code=400, detail=f"It is not {ai_player_name}'s turn.")

    current_player = game.players[ai_player_name]
    legal = game.legal_moves(ai_player_name) #legal moves which are allowed to AI player
    drawn_cards = []
    banter = None

    if not legal:
        # No playable card: draw. No LLM call needed.
        try:
            drawn_cards = game.draw_until_playable(ai_player_name, auto_declare=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI execution error: {str(e)}")
        action_taken = "AI had no playable cards and drew from the pile."
        if drawn_cards and game.top_card.to_dict() == drawn_cards[-1] and game.top_card.rank == '8':
            action_taken += f" It drew an 8 and changed the suit to {game.declared_suit}."
    else:
        chosen_index, declared_suit = legal[0], None
        ai_decision = await choose_move(
            ai_hand=[c.to_dict() for c in current_player.hand],
            legal_indices=legal,
            top_card=game.top_card.to_dict(),
            active_suit=game.active_suit,
            house_rules=game.house_rules
        )

        if ai_decision is not None:
            banter = ai_decision.roleplay_comment
            if ai_decision.chosen_index in legal:
                chosen_index = ai_decision.chosen_index
                declared_suit = ai_decision.declared_suit

        card_played = current_player.hand[chosen_index]
        if card_played.rank == '8':
            if declared_suit not in SUITS:
                declared_suit = game.best_suit(current_player.hand)
        else:
            declared_suit = None

        try:
            game.play_card(ai_player_name, chosen_index, declared_suit)
        except Exception as e:
                    raise HTTPException(status_code=500, detail=f"AI move failed: {str(e)}")

        action_taken = f"AI played {card_played}"
        if declared_suit:
            action_taken += f" and changed the suit to {declared_suit}"

    return {
        "action": action_taken,
        "ai_banter": banter,
        "drawn_cards": drawn_cards,
        "state": get_game_state_summary('ai_turn', game)
    }

def get_game_state_summary(action : str, game: GameEngine, viewer: str = None) -> GameStateSummary:
    # write state to the file
    summary_file_path = Path("game_state_summary.json")
    state = GameStateSummary(
        current_player=game.current_player_name,
        top_card=CardModel(suit=game.top_card.suit, rank=game.top_card.rank),
        active_suit=game.active_suit,
        winner=game.winner,
        pending_suit_player=game.pending_suit_player,
        players={
            name: PlayerModel(
                type=p.player_type,
                hand_count=len(p.hand),
                # only reveal the hand of the current human player for privacy
                hand=[CardModel(suit=c.suit, rank=c.rank) for c in p.hand] 
                    if p.player_type == "human" and (viewer is None or name == viewer)
                    else "HIDDEN"
            ) for name, p in game.players.items()
        }
    )
    summary_file_path.write_text(
        json.dumps({"action": action, "state": state.model_dump()}, indent=2),
        encoding="utf-8"
    )

    return state

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)