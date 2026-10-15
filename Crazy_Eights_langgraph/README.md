# Crazy Eights — LangGraph edition

Each player is a node in a LangGraph graph; the rules live in `engine.py` and the LLM only picks among legal moves.

```
START ─► entry router ─► setup ─► router ─► player_0 ─► router ─► player_1 ─► … ─► END
```

* `engine.py` – serializable `GameState` (Pydantic) + rule functions (deal, play, draw, declare suit).
* `graph.py` – `build_graph(players, checkpointer)`: one node per player. Human nodes consume `human_move`
  from the input; AI nodes call the LLM. A run ends when the game is over or it is a human's turn
  (including a human who still has to declare a suit after drawing an 8). No interrupts are used.
* `ai_player.py` – LangChain chain (`prompt | ChatOpenAI.with_structured_output`). Illegal or failed
  LLM answers fall back to a legal move.
* `main.py` – FastAPI. Each move request invokes the graph and returns `{events, state}`.
  Game state is checkpointed in SQLite (`games.db`), so games survive a restart.
* `frontend/` – replays the returned events one by one.

## Run
```
pip install -r requirements.txt
export OPENAI_API_KEY=...
python main.py            # http://localhost:8000
pytest                    # tests use a fake LLM; no API key or network needed
```

## API
`POST /game/create` · `POST /game/{id}/join_game` · `POST /game/{id}/start` · `GET /game/{id}/state` ·
`POST /game/{id}/play` · `POST /game/{id}/draw?player_name=` · `POST /game/{id}/declare_suit?player_name=&suit=`

`start`, `play`, `draw` and `declare_suit` return `{events, state}`. An event with `awaiting_suit: true`
means the human drew a playable 8 and must call `declare_suit` next.
