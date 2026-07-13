# AI Old Maid Game

## Frontend (pure HTML/CSS/JS)

A vanilla frontend is available in `/frontend` and is served by FastAPI.

### Run locally

1. Start the app (backend APIs + frontend) with one command:
   ```bash
   python main.py
   ```
2. Open:
   ```
   http://127.0.0.1:8000
   ```

### API base URL configuration

On the setup page, use the **API Base URL** field to point to a different backend URL.
The value is saved in local storage and reused for future sessions.

### Frontend flow

- Enter player name
- Select 1, 2, or 3 AI players
- Enter house rules
- Start game
- Setup view transitions in-place to game view in the same browser window
- On game over, use **New Game** to return to setup and start fresh
