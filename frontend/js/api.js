const API_BASE = 'http://127.0.0.1:8000';

function buildUrl(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return qs ? `${path}?${qs}` : path;
}

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

export function createGame(house_rules) {
  return request('/game/create', {
    method: 'POST',
    body: JSON.stringify({ house_rules }),
  });
}

export function joinGame(gameId, player_name, player_type) {
  return request(`/game/${encodeURIComponent(gameId)}/join_game`, {
    method: 'POST',
    body: JSON.stringify({ player_name, player_type }),
  });
}

export function startGame(gameId) {
  return request(`/game/${encodeURIComponent(gameId)}/start`, { method: 'POST' });
}

export function getPlayerState(gameId, playerName) {
  return request(`/game/${encodeURIComponent(gameId)}/state/${encodeURIComponent(playerName)}`);
}

export function humanMove(gameId, playerName, cardIndex) {
  return request(
    buildUrl(`/game/${encodeURIComponent(gameId)}/move/human`, { player_name: playerName }),
    { method: 'POST', body: JSON.stringify({ card_index: cardIndex }) },
  );
}

export function aiMove(gameId, aiPlayerName) {
  return request(
    buildUrl(`/game/${encodeURIComponent(gameId)}/move/ai`, { ai_player_name: aiPlayerName }),
    { method: 'POST' },
  );
}