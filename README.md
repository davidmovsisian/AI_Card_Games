# AI Old Maid Game

## Frontend (pure HTML/CSS/JS)

A new vanilla frontend is available in `/frontend`.

### Run locally

1. Start the FastAPI backend (default `http://127.0.0.1:8000`):
   ```bash
   python main.py
   ```
2. In another terminal, start the frontend static server:
   ```bash
   node frontend/server.js
   ```
3. Open:
   ```
   http://127.0.0.1:5173
   ```

### API base URL configuration

On the setup page, use the **API Base URL** field to point to a different backend URL.
The value is saved in local storage and reused for future sessions.

### Frontend flow

- Enter player name
- Select 1, 2, or 3 AI players
- Enter house rules
- Start game
- A new game page opens showing players, cards (AI cards hidden), and a game log
