const API_BASE = 'http://127.0.0.1:8000';

// ── Low-level request helper ──────────────────────────────────────────────────

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    try {
      const errorData = await response.json();
      errorMessage = errorData?.detail || errorData?.message || JSON.stringify(errorData);
    } catch {
      // no-op
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

// ── Game lifecycle ────────────────────────────────────────────────────────────

/** POST /game/create  →  { game_id } */
export function createGame(house_rules) {
  return request('/game/create', {
    method: 'POST',
    body: JSON.stringify({ house_rules }),
  });
}

/** POST /game/:id/join_game  →  { status } */
export function joinGame(gameId, player_name, player_type = 'human') {
  return request(`/game/${encodeURIComponent(gameId)}/join_game`, {
    method: 'POST',
    body: JSON.stringify({ player_name, player_type }),
  });
}

/** POST /game/:id/start  →  { status, state: GameStateSummary } */
export function startGame(gameId) {
  return request(`/game/${encodeURIComponent(gameId)}/start`, { method: 'POST' });
}

// ── Game state ────────────────────────────────────────────────────────────────

/**
 * GET /game/:id/state  →  GameStateSummary
 *
 * GameStateSummary shape:
 *   current_player  : string
 *   top_card        : { suit, rank }
 *   active_suit     : string
 *   winner          : string | null
 *   players         : {
 *     [name]: {
 *       type        : "human" | "ai"
 *       hand_count  : number
 *       hand        : CardModel[] | "HIDDEN"
 *     }
 *   }
 *
 * Note: the backend only reveals `hand` for the current human player.
 * We always fetch the global state — the hand for non-current players is "HIDDEN".
 */
export function getState(gameId) {
  return request(`/game/${encodeURIComponent(gameId)}/state`);
}

// ── Moves ─────────────────────────────────────────────────────────────────────

/**
 * POST /game/:id/play
 * body: { player_name, card_index, declared_suit? }
 * →  { message, state: GameStateSummary }
 */
export function playCard(gameId, player_name, card_index, declared_suit = null) {
  return request(`/game/${encodeURIComponent(gameId)}/play`, {
    method: 'POST',
    body: JSON.stringify({ player_name, card_index, declared_suit }),
  });
}

/**
 * POST /game/:id/draw?player_name=…
 * →  { message, drawn_cards, state: GameStateSummary }
 */
export function drawCard(gameId, player_name) {
  const qs = new URLSearchParams({ player_name }).toString();
  return request(`/game/${encodeURIComponent(gameId)}/draw?${qs}`, { method: 'POST' });
}

/**
 * POST /game/:id/ai-turn?ai_player_name=…
 * →  { action, ai_banter, drawn_cards, state: GameStateSummary }
 */
export function aiTurn(gameId, ai_player_name) {
  const qs = new URLSearchParams({ ai_player_name }).toString();
  return request(`/game/${encodeURIComponent(gameId)}/ai-turn?${qs}`, { method: 'POST' });
}
