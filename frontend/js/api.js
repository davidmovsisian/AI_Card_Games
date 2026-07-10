const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
const API_BASE_STORAGE_KEY = 'oldMaidApiBase';

export function getApiBaseUrl() {
  return localStorage.getItem(API_BASE_STORAGE_KEY) || DEFAULT_API_BASE;
}

export function setApiBaseUrl(url) {
  const normalized = (url || '').trim().replace(/\/$/, '');
  if (normalized) {
    let parsed;
    try {
      parsed = new URL(normalized);
    } catch {
      throw new Error('API Base URL must be a valid absolute URL (for example: http://127.0.0.1:8000).');
    }
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      throw new Error('API Base URL must use http or https.');
    }
    localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
  } else {
    localStorage.removeItem(API_BASE_STORAGE_KEY);
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
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
  const params = new URLSearchParams({ player_name: playerName });
  return request(`/game/${encodeURIComponent(gameId)}/move/human?${params.toString()}`, {
    method: 'POST',
    body: JSON.stringify({ card_index: cardIndex }),
  });
}

export function aiMove(gameId, aiPlayerName) {
  const params = new URLSearchParams({ ai_player_name: aiPlayerName });
  return request(`/game/${encodeURIComponent(gameId)}/move/ai?${params.toString()}`, {
    method: 'POST',
  });
}
