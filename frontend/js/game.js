import { aiMove, getPlayerState, humanMove } from './api.js';

const params = new URLSearchParams(window.location.search);
const gameId = params.get('game_id') || '';
const humanPlayer = params.get('player_name') || '';
const aiNames = (params.get('ai_names') || '').split(',').map((v) => v.trim()).filter(Boolean);

const turnIndicator = document.getElementById('turn-indicator');
const playersArea = document.getElementById('players-area');
const cardIndexInput = document.getElementById('card-index');
const drawButton = document.getElementById('draw-button');
const gameError = document.getElementById('game-error');
const gameLog = document.getElementById('game-log');

let latestState = null;
let aiLoopRunning = false;
let gameEnded = false;
let humanOut = false;
let pollIntervalId = null;
let prevActiveAiSet = new Set();

function addLog(message) {
  const li = document.createElement('li');
  li.textContent = message;
  gameLog.prepend(li);
}

// Returns the set of AI players that currently have cards, based on state.
function buildActiveAiSet(state, queriedAs) {
  const active = new Set();
  for (const aiName of aiNames) {
    if (aiName === queriedAs) {
      if ((state.your_hand || []).length > 0) active.add(aiName);
    } else if (Number(state.opponents_card_counts?.[aiName] || 0) > 0) {
      active.add(aiName);
    }
  }
  return active;
}

// Compares active AI set against the previous snapshot and logs any new eliminations.
function checkAiEliminations(state, queriedAs) {
  const currentActiveAis = buildActiveAiSet(state, queriedAs);
  if (prevActiveAiSet.size > 0) {
    for (const name of prevActiveAiSet) {
      if (!currentActiveAis.has(name)) {
        addLog(`${name} is out of the game.`);
      }
    }
  }
  prevActiveAiSet = currentActiveAis;
}

// Returns the next player (with cards) after currentPlayer in turn order.
// queriedAs identifies which player's perspective the state is from (their hand is in state.your_hand).
function getNextPlayerName(currentPlayer, state, queriedAs = humanPlayer) {
  const allPlayers = humanOut ? [...aiNames] : [humanPlayer, ...aiNames];
  const activePlayers = allPlayers.filter((name) => {
    if (name === queriedAs) return (state?.your_hand || []).length > 0;
    return Number(state?.opponents_card_counts?.[name] || 0) > 0;
  });
  const currentIndex = activePlayers.indexOf(currentPlayer);
  if (currentIndex < 0 || activePlayers.length === 0) return null;
  return activePlayers[(currentIndex + 1) % activePlayers.length];
}

function extractTargetFromAction(actionText) {
  const match = String(actionText || '').match(/\bdrew a card from (.+)$/i);
  return match ? match[1].trim() : null;
}

function finishGame(message) {
  gameEnded = true;
  drawButton.disabled = true;
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
  if (message) {
    turnIndicator.textContent = message;
  }
}

// Renders the game board. queriedAs is the player whose perspective the state represents.
function renderState(state, queriedAs = humanPlayer) {
  latestState = state;
  const currentTurn = state.current_turn;
  turnIndicator.textContent = `Current turn: ${currentTurn}`;

  playersArea.innerHTML = '';

  const allPlayers = [humanPlayer, ...aiNames];
  for (const playerName of allPlayers) {
    const section = document.createElement('section');
    section.className = 'player-block';

    const title = document.createElement('h3');
    title.textContent = playerName === humanPlayer ? `${playerName} (You)` : playerName;
    section.appendChild(title);

    const cards = document.createElement('div');
    cards.className = 'cards';

    if (playerName === humanPlayer && humanOut) {
      // Human has been eliminated — always show as eliminated regardless of state perspective.
      const empty = document.createElement('div');
      empty.textContent = '(Eliminated)';
      cards.appendChild(empty);
    } else if (playerName === queriedAs) {
      // This is the player we queried as — their cards are in state.your_hand.
      for (const card of state.your_hand || []) {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        cardEl.textContent = `${card.rank} of ${card.suit}`;
        cards.appendChild(cardEl);
      }
      if ((state.your_hand || []).length === 0) {
        const empty = document.createElement('div');
        empty.textContent = '(No cards)';
        cards.appendChild(empty);
      }
    } else {
      const count = Number(state.opponents_card_counts?.[playerName] || 0);
      for (let i = 0; i < count; i += 1) {
        const back = document.createElement('div');
        back.className = 'card back';
        back.textContent = 'Hidden';
        cards.appendChild(back);
      }
      if (count === 0) {
        const empty = document.createElement('div');
        empty.textContent = '(Eliminated)';
        cards.appendChild(empty);
      }
    }

    section.appendChild(cards);
    playersArea.appendChild(section);
  }

  const isHumanTurn = !humanOut && currentTurn === humanPlayer;
  drawButton.disabled = !isHumanTurn || gameEnded;
  if (isHumanTurn) {
    const nextPlayer = getNextPlayerName(humanPlayer, state, humanPlayer);
    if (!nextPlayer) {
      drawButton.disabled = true;
      cardIndexInput.max = '0';
      return;
    }
    const nextCount = Number(state.opponents_card_counts?.[nextPlayer] || 0);
    const max = Math.max(0, nextCount - 1);
    cardIndexInput.max = String(max);
    if (Number(cardIndexInput.value) > max) {
      cardIndexInput.value = String(max);
    }
  }
}

// Fetches the current game state. Uses humanPlayer when possible; falls back to an active AI
// when the human has been eliminated. Automatically sets humanOut and logs the elimination.
async function fetchGameState() {
  if (!humanOut) {
    try {
      const state = await getPlayerState(gameId, humanPlayer);
      return { state, queriedAs: humanPlayer };
    } catch (e) {
      const msg = (e.message || '').toLowerCase();
      if (msg.includes('player not in this game')) {
        humanOut = true;
        drawButton.disabled = true;
        addLog('You are out of the game.');
        // Fall through to query via an AI player.
      } else {
        throw e;
      }
    }
  }

  // Human is out — find a still-active AI to query as.
  for (const aiName of aiNames) {
    try {
      const state = await getPlayerState(gameId, aiName);
      return { state, queriedAs: aiName };
    } catch (e) {
      const msg = (e.message || '').toLowerCase();
      if (!msg.includes('player not in this game')) throw e;
      // This AI is also out; try the next one.
    }
  }

  throw new Error('No active players remain to query state.');
}

async function refreshState() {
  try {
    const { state, queriedAs } = await fetchGameState();
    gameError.textContent = '';
    checkAiEliminations(state, queriedAs);
    renderState(state, queriedAs);

    if (!humanOut && state.current_turn === humanPlayer) {
      // Human's turn — wait for the player to act.
    } else {
      void maybeRunAiTurns(state, queriedAs);
    }
  } catch (error) {
    gameError.textContent = error.message || 'Failed to load game state.';
  }
}

async function maybeRunAiTurns(initialState, initialQueriedAs = humanPlayer) {
  if (aiLoopRunning || gameEnded) return;

  aiLoopRunning = true;
  try {
    let currentState = initialState;
    let currentQueriedAs = initialQueriedAs;

    while (!gameEnded) {
      // If it is the human's turn and the human is still active, hand control back.
      if (currentState.current_turn === humanPlayer) {
        if (!humanOut) break;
        // Defensive: humanOut is true but we have stale state that still shows the human
        // as the current turn (the backend skips eliminated players, so this is transient).
        // Re-fetch to get the actual next active player before continuing.
        const { state: refreshed, queriedAs: refreshedAs } = await fetchGameState();
        checkAiEliminations(refreshed, refreshedAs);
        renderState(refreshed, refreshedAs);
        currentState = refreshed;
        currentQueriedAs = refreshedAs;
        continue;
      }

      const aiPlayer = currentState.current_turn;
      const computedTargetPlayer = getNextPlayerName(aiPlayer, currentState, currentQueriedAs);
      const result = await aiMove(gameId, aiPlayer);
      const reportedTargetPlayer = extractTargetFromAction(result.action);
      const targetPlayer = reportedTargetPlayer || computedTargetPlayer;
      if (!targetPlayer) {
        throw new Error('Could not determine target player for AI move.');
      }
      const summary = (result.details?.new_pairs_formed || []).length
        ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
        : 'No new pairs.';
      addLog(`Current: ${aiPlayer} | Picked from: ${targetPlayer} | ${summary}`);

      if (result.game_over) {
        // Always render final state before stopping the loop.
        // Errors are ignored here because the backend may tear down game state
        // immediately after reporting game_over, making follow-up queries unreliable.
        try {
          const { state: finalState, queriedAs: finalQueriedAs } = await fetchGameState();
          checkAiEliminations(finalState, finalQueriedAs);
          renderState(finalState, finalQueriedAs);
        } catch (err) {
          // best-effort: backend may have already torn down state after game_over
        }
        finishGame('Game over.');
        break;
      }

      const { state: newState, queriedAs: newQueriedAs } = await fetchGameState();
      checkAiEliminations(newState, newQueriedAs);
      renderState(newState, newQueriedAs);
      currentState = newState;
      currentQueriedAs = newQueriedAs;
    }
  } catch (error) {
    gameError.textContent = error.message || 'AI move failed.';
  } finally {
    aiLoopRunning = false;
  }
}

drawButton.addEventListener('click', async () => {
  if (!latestState || latestState.current_turn !== humanPlayer || gameEnded || humanOut) return;

  gameError.textContent = '';
  drawButton.disabled = true;

  try {
    const drawFromPlayer = getNextPlayerName(humanPlayer, latestState, humanPlayer);
    if (!drawFromPlayer) {
      throw new Error('Could not determine target player for human move.');
    }
    const cardIndex = Number(cardIndexInput.value);

    const result = await humanMove(gameId, humanPlayer, cardIndex);
    const summary = (result.details?.new_pairs_formed || []).length
      ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
      : 'No new pairs.';

    addLog(`Current: ${humanPlayer} | Picked from: ${drawFromPlayer} | ${summary}`);

    if (result.game_over) {
      try {
        const { state: finalState, queriedAs } = await fetchGameState();
        checkAiEliminations(finalState, queriedAs);
        renderState(finalState, queriedAs);
      } catch (err) {
        // best-effort: backend may have already torn down state after game_over
      }
      finishGame('Game over.');
      return;
    }

    await refreshState();
  } catch (error) {
    gameError.textContent = error.message || 'Move failed.';
    drawButton.disabled = false;
  }
});

if (!gameId || !humanPlayer) {
  gameError.textContent = 'Missing game context. Start from setup page.';
  drawButton.disabled = true;
} else {
  void refreshState();
  pollIntervalId = window.setInterval(() => {
    if (!aiLoopRunning && !gameEnded) {
      void refreshState();
    }
  }, 2000);
  window.addEventListener('beforeunload', () => {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
  });
}
