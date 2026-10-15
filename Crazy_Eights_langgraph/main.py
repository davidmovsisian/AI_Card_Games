"""FastAPI server for Crazy Eights.

The game itself runs as a LangGraph graph (see graph.py). Each HTTP request that moves the
game invokes the graph with the human's move; the graph then plays every AI turn until it is
a human's turn again (or the game ends), and the request returns the list of events that
happened. Graph state lives in a SQLite checkpoint, so games survive a server restart.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, AsyncGenerator
from uuid import uuid4

import aiosqlite
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import engine
from engine import GameState
from graph import build_graph
from models import (CreateGameRequest, CreateGameResponse, GameStateSummary, JoinGameRequest, MoveResponse,
                    PlayCardRequest, StartGameResponse, StatusResponse)

DB_PATH = os.environ.get("CRAZY8_DB", str(Path(__file__).parent / "games.db"))
FRONTEND_DIR = Path(__file__).parent / "frontend"
if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")


class Runtime:
    """Process-wide resources, created in the app lifespan."""
    def __init__(self):
        self.checkpointer: Optional[AsyncSqliteSaver] = None
        self.db: Optional[aiosqlite.Connection] = None
        self.graphs: Dict[str, object] = {}             # game_id -> compiled graph
        self.locks: Dict[str, asyncio.Lock] = {}        # game_id -> lock (one run at a time per game)    

rt = Runtime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
        rt.checkpointer = saver
        rt.db = await aiosqlite.connect(DB_PATH)
        await rt.db.execute(
            "CREATE TABLE IF NOT EXISTS games ("
            "game_id TEXT PRIMARY KEY, house_rules TEXT NOT NULL, players TEXT NOT NULL, started INTEGER NOT NULL DEFAULT 0)"
        )
        await rt.db.commit()
        try:
            yield
        finally:
            await rt.db.close()
            rt.graphs.clear()


app = FastAPI(title="Crazy Eights AI Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/", include_in_schema=False)
async def frontend_root():
    return FileResponse(FRONTEND_DIR / "index.html")


# ── helpers ───────────────────────────────────────────────────────────────────

async def load_game_row(game_id: str) -> dict:
    cur = await rt.db.execute("SELECT house_rules, players, started FROM games WHERE game_id = ?", (game_id,))
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    return {"house_rules": row[0], "players": [tuple(p) for p in json.loads(row[1])], "started": bool(row[2])}


async def get_graph(game_id: str):
    """The compiled graph for a started game; rebuilt from the stored roster after a restart."""
    if game_id not in rt.graphs:
        row = await load_game_row(game_id)
        if not row["started"]:
            raise HTTPException(status_code=400, detail="Game not started yet. Call /start first.")
        rt.graphs[game_id] = build_graph(row["players"], rt.checkpointer)
    return rt.graphs[game_id]


def config_for(game_id: str) -> dict:
    # A game is at most a few hundred node steps; this is only a safety net against runaway loops.
    return {"configurable": {"thread_id": game_id}, "recursion_limit": 5000}


async def run_graph(game_id: str, graph_input: dict) -> dict:
    """Invoke the graph and collect the events produced until it comes to rest."""
    graph = await get_graph(game_id)
    lock = rt.locks.setdefault(game_id, asyncio.Lock())
    if lock.locked():
        # Reject instead of queueing: the client would otherwise hang until the previous run (AI turns) ends.
        raise HTTPException(status_code=409, detail="The game is busy - wait for the current move to finish.")
    async with lock:
        events: List[dict] = []
        async for chunk in graph.astream(graph_input, config_for(game_id), stream_mode="updates"):
            for update in chunk.values():
                if update and update.get("last_event"):
                    events.append(update["last_event"])
        snapshot = await graph.aget_state(config_for(game_id))
    game = GameState.model_validate(snapshot.values["game"])

    error = next((e for e in events if e["type"] == "error"), None)
    if error:
        raise HTTPException(status_code=400, detail=error["text"])
    return {"events": events, "state": engine.summarize(game)}


# ── streaming helper ──────────────────────────────────────────────────────────

async def _sse_generator_for_graph(game_id: str, graph_input: dict) -> AsyncGenerator[bytes, None]:
    """Async generator that yields Server-Sent Events (text/event-stream) for every graph event as it arrives.

    Each yielded chunk is a properly formatted SSE block with a single `data: ...` line containing JSON.
    At the end a final object with `type: "final"` and `state: <GameStateSummary>` is emitted.
    """
    graph = await get_graph(game_id)
    lock = rt.locks.setdefault(game_id, asyncio.Lock())
    if lock.locked():
        # The route caller will observe the 409 before the stream starts; raise to abort.
        raise HTTPException(status_code=409, detail="The game is busy - wait for the current move to finish.")

    async with lock:
        events: List[dict] = []
        async for chunk in graph.astream(graph_input, config_for(game_id), stream_mode="updates"):
            for update in chunk.values():
                if update and update.get("last_event"):
                    ev = update["last_event"]
                    events.append(ev)
                    payload = json.dumps({"type": "event", "event": ev})
                    yield f"data: {payload}\n\n".encode()
        snapshot = await graph.aget_state(config_for(game_id))
    game = GameState.model_validate(snapshot.values["game"])

    # If any error event happened, emit it as the last event and close with a final payload containing the error.
    error = next((e for e in events if e["type"] == "error"), None)
    if error:
        payload = json.dumps({"type": "error", "error": error["text"]})
        yield f"data: {payload}\n\n".encode()
        return

    final_state = engine.summarize(game)
    payload = json.dumps({"type": "final", "state": final_state})
    yield f"data: {payload}\n\n".encode()


# ── lobby ─────────────────────────────────────────────────────────────────────

@app.post("/game/create", response_model=CreateGameResponse)
async def create_game(req: CreateGameRequest):
    game_id = uuid4().hex
    await rt.db.execute("INSERT INTO games (game_id, house_rules, players) VALUES (?, ?, ?)",
                        (game_id, req.house_rules, "[]"))
    await rt.db.commit()
    return {"status": "Game created", "game_id": game_id}


@app.post("/game/{game_id}/join_game", response_model=StatusResponse)
async def join_game(game_id: str, req: JoinGameRequest):
    row = await load_game_row(game_id)
    if row["started"]:
        raise HTTPException(status_code=400, detail="Game already started.")
    if req.player_type not in ("human", "ai"):
        raise HTTPException(status_code=400, detail="player_type must be 'human' or 'ai'.")
    if any(name == req.player_name for name, _ in row["players"]):
        raise HTTPException(status_code=400, detail="Player name already taken.")
    players = row["players"] + [(req.player_name, req.player_type)]
    await rt.db.execute("UPDATE games SET players = ? WHERE game_id = ?", (json.dumps(players), game_id))
    await rt.db.commit()
    return {"status": f"{req.player_name} joined the game."}


@app.post("/game/{game_id}/start", response_model=StartGameResponse)
async def start_game(game_id: str):
    row = await load_game_row(game_id)
    if row["started"]:
        raise HTTPException(status_code=400, detail="Game already started.")
    players = row["players"]
    if len(players) < 2:
        players = players + [("AI_Opponent", "ai")]   # add an AI opponent if only one player joined

    await rt.db.execute("UPDATE games SET players = ?, started = 1 WHERE game_id = ?",
                        (json.dumps(players), game_id))
    await rt.db.commit()

    initial = engine.new_game(players, house_rules=row["house_rules"])
    result = await run_graph(game_id, {"game": initial.model_dump()})
    return {"status": "Game started", **result}


# ── gameplay ──────────────────────────────────────────────────────────────────

@app.get("/game/{game_id}/state", response_model=GameStateSummary)
async def get_state(game_id: str):
    graph = await get_graph(game_id)
    snapshot = await graph.aget_state(config_for(game_id))
    game = GameState.model_validate(snapshot.values["game"])
    return engine.summarize(game)


@app.post("/game/{game_id}/play", response_model=MoveResponse)
async def play_card(game_id: str, payload: PlayCardRequest):
    return await run_graph(game_id, {"human_move": {
        "player": payload.player_name, "action": "play",
        "card_index": payload.card_index, "declared_suit": payload.declared_suit,
    }})


@app.post("/game/{game_id}/draw", response_model=MoveResponse)
async def draw_card(game_id: str, player_name: str):
    return await run_graph(game_id, {"human_move": {"player": player_name, "action": "draw"}})


@app.post("/game/{game_id}/declare_suit", response_model=MoveResponse)
async def declare_suit(game_id: str, player_name: str, suit: str):
    return await run_graph(game_id, {"human_move": {"player": player_name, "action": "declare", "suit": suit}})


# ── streaming endpoints (SSE) ─────────────────────────────────────────────────

@app.post("/game/{game_id}/play/stream")
async def play_card_stream(game_id: str, payload: PlayCardRequest):
    try:
        gen = _sse_generator_for_graph(game_id, {"human_move": {
            "player": payload.player_name, "action": "play",
            "card_index": payload.card_index, "declared_suit": payload.declared_suit,
        }})
    except HTTPException as exc:
        raise
    return StreamingResponse(gen, media_type="text/event-stream")


@app.post("/game/{game_id}/draw/stream")
async def draw_card_stream(game_id: str, player_name: str):
    gen = _sse_generator_for_graph(game_id, {"human_move": {"player": player_name, "action": "draw"}})
    return StreamingResponse(gen, media_type="text/event-stream")


@app.post("/game/{game_id}/declare_suit/stream")
async def declare_suit_stream(game_id: str, player_name: str, suit: str):
    gen = _sse_generator_for_graph(game_id, {"human_move": {"player": player_name, "action": "declare", "suit": suit}})
    return StreamingResponse(gen, media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
