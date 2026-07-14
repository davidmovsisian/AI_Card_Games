from uuid import uuid4
import json
from fastapi import FastAPI, HTTPException
import uvicorn
from typing import Dict
from pathlib import Path
from engine import GameEngine
from ai_service import AIService
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

ai_service = AIService()
FRONTEND_DIR = Path(__file__).parent / "frontend"
if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

ACTIVE_GAMES: Dict[str, GameEngine] = {}

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
    return get_game_state_summary('state', game)

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
    
    game.initialize_game()
    
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
            "state": get_game_state_summary('play', game)}
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
        drawn_cards = game.draw_until_playable(player_name)
        return {
            "message": "Drawing process complete.",
            "drawn_cards": drawn_cards,
            "state": get_game_state_summary('draw', game)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/game/{game_id}/ai-turn")
async def ai_turn(game_id: str, ai_player_name: str):
    if game_id not in ACTIVE_GAMES:
        raise HTTPException(status_code=404, detail="Game not found.")
    game = ACTIVE_GAMES[game_id]
    if not game:
        raise HTTPException(status_code=400, detail="Game not initialized.")
    current_player = game.players[game.current_player_name]
    if current_player.name != ai_player_name:
        raise HTTPException(status_code=400, detail=f"It is not {ai_player_name}'s turn.")

    ai_hand_list = [c.to_dict() for c in current_player.hand]
    
    # Request strategic move from OpenAI via the service
    ai_decision = await ai_service.get_ai_move(
        ai_hand=ai_hand_list,
        top_card=game.top_card.to_dict(),
        active_suit=game.active_suit,
        house_rules=game.house_rules
    )

    action_taken = ""
    drawn_cards = []

    if ai_decision.use_draw_pile:
        try:
            drawn_cards = game.draw_until_playable(current_player.name)
            action_taken = "AI had no playable cards and drew from the pile."
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI execution error: {str(e)}")
    else:
        try:
            card_played = current_player.hand[ai_decision.chosen_index]
            game.play_card(current_player.name, ai_decision.chosen_index, ai_decision.declared_suit)
            action_taken = f"AI played {card_played}"
            if ai_decision.declared_suit:
                action_taken += f" and changed the suit to {ai_decision.declared_suit}"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"AI chose an illegal move: {str(e)}")

    return {
        "action": action_taken,
        "ai_banter": ai_decision.roleplay_comment,


"drawn_cards": drawn_cards,
        "state": get_game_state_summary('ai_turn', game)
    }

def get_game_state_summary(action : str, game: GameEngine) -> GameStateSummary:
    # write state ro the file
    summary_file_path = Path("game_state_summary.json")
    state = GameStateSummary(
        current_player=game.current_player_name,
        top_card=CardModel(suit=game.top_card.suit, rank=game.top_card.rank),
        active_suit=game.active_suit,
        winner=game.winner,
        players={
            name: PlayerModel(
                type=p.player_type,
                hand_count=len(p.hand),
                # only reveal the hand of the current human player for privacy
                hand=[CardModel(suit=c.suit, rank=c.rank) for c in p.hand] 
                    if p.player_type == "human" # and p.name == game.current_player_name 
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