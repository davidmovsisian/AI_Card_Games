import { aiMove, getPlayerState, humanMove } from './api.js';

const turnIndicator = document.getElementById('turn-indicator');
const playersArea = document.getElementById('players-area');
const cardIndexInput = document.getElementById('card-index');
const drawButton = document.getElementById('draw-button');
const newGameButton = document.getElementById('new-game-button');
const gameError = document.getElementById('game-error');
const gameLog = document.getElementById('game-log');

let gameId = '';
let humanPlayer = '';
let aiNames = [];
let onNewGame = null;
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

function getPlayerCounts(state, queriedAs = humanPlayer) {
  const counts = {};
  for (const playerName of [humanPlayer, ...aiNames]) {
    if (!playerName) continue;
    if (playerName === humanPlayer && humanOut) {
      counts[playerName] = 0;
    } else if (playerName === queriedAs) {
      counts[playerName] = (state?.your_hand || []).length;
    } else {
      counts[playerName] = Number(state?.opponents_card_counts?.[playerName] || 0);
    }
  }
  return counts;
}

// Derives post-move card counts from the pre-move state by applying the draw transfer
// and removing two cards for each newly formed pair in the current player's hand.
function buildPostMoveCounts(state, queriedAs, currentPlayer, targetPlayer, newPairsFormed = []) {
  const counts = getPlayerCounts(state, queriedAs);
  const pairCount = Array.isArray(newPairsFormed) ? newPairsFormed.length : 0;
  const cardsDrawn = 1;
  const cardsRemovedByPairs = pairCount * 2;

  counts[targetPlayer] = Math.max(0, Number(counts[targetPlayer] || 0) - 1);
  counts[currentPlayer] = Math.max(
    0,
    Number(counts[currentPlayer] || 0) + cardsDrawn - cardsRemovedByPairs,
  );

  return counts;
}

function hasCards(playerCounts, playerName) {
  return Number(playerCounts?.[playerName] || 0) > 0;
}

function countActivePlayers(playerCounts) {
  return Object.keys(playerCounts).filter((playerName) => hasCards(playerCounts, playerName)).length;
}

function isTerminalCounts(playerCounts) {
  return countActivePlayers(playerCounts) === 1;
}

function formatMoveLog(currentPlayer, targetPlayer, summary, playerCounts) {
  return [
    `Current: ${currentPlayer}`,
    `Picked from: ${targetPlayer}`,
    summary,
    `Cards after move: ${currentPlayer}=${playerCounts[currentPlayer] || 0}, ${targetPlayer}=${playerCounts[targetPlayer] || 0}`,
  ].join(' | ');
}

// Returns the set of AI players that currently have cards, based on player counts.
function buildActiveAiSet(playerCounts) {
  const active = new Set();
  for (const aiName of aiNames) {
    if (hasCards(playerCounts, aiName)) {
      active.add(aiName);
    }
  }
  return active;
}

// Compares active AI set against the previous snapshot and logs any new eliminations.
function checkAiEliminations(playerCounts) {
  const currentActiveAis = buildActiveAiSet(playerCounts);
  if (prevActiveAiSet.size > 0) {
    for (const name of prevActiveAiSet) {
      if (!currentActiveAis.has(name)) {
        addLog(`${name} is out of the game. (0 cards left)`);
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
  gameError.textContent = '';
  newGameButton.classList.remove('hidden');
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
  if (message) {
    turnIndicator.textContent = message;
  }
}

// Renders the game board. queriedAs is the player whose perspective the state represents.
function renderState(state, queriedAs = humanPlayer, options = {}) {
  latestState = state;
  const playerCounts = options.playerCounts || getPlayerCounts(state, queriedAs);
  const currentTurn = options.currentTurn || state.current_turn;
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
    } else if (playerName === humanPlayer && queriedAs === humanPlayer) {
      // Only the human player's own perspective should ever reveal face-up cards.
      // If queriedAs is an AI, that AI hand also lives in state.your_hand but must stay hidden.
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
      const count = Number(playerCounts[playerName] || 0);
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
        addLog('You are out of the game. (0 cards left)');
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
  if (!gameId || !humanPlayer || gameEnded) return;
  try {
    const { state, queriedAs } = await fetchGameState();
    gameError.textContent = '';
    checkAiEliminations(getPlayerCounts(state, queriedAs));
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

// Fetches the authoritative post-move state when available, but falls back to a
// counts-derived render if a terminal move caused the backend to remove the game
// before the frontend could re-fetch it.
async function syncMoveOutcome(previousState, previousQueriedAs, result, currentPlayer, targetPlayer) {
  const summary = (result.details?.new_pairs_formed || []).length
    ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
    : 'No new pairs.';

  try {
    const { state, queriedAs } = await fetchGameState();
    const playerCounts = getPlayerCounts(state, queriedAs);
    checkAiEliminations(playerCounts);
    renderState(state, queriedAs);
    addLog(formatMoveLog(currentPlayer, targetPlayer, summary, playerCounts));
    return { state, queriedAs, terminal: isTerminalCounts(playerCounts) };
  } catch (error) {
    // A non-terminal move should always be re-fetchable. If the backend state is gone,
    // only tolerate that on a terminal move and render the last known board from counts.
    if (!result.game_over) {
      throw new Error(`Failed to fetch post-move state for non-terminal move: ${error.message || error}`);
    }

    const playerCounts = buildPostMoveCounts(
      previousState,
      previousQueriedAs,
      currentPlayer,
      targetPlayer,
      result.details?.new_pairs_formed || [],
    );

    checkAiEliminations(playerCounts);
    // Only the count-based visuals matter in this terminal fallback render. The underlying
    // state object is pre-move, but the game ends immediately after this repaint.
    renderState(previousState, previousQueriedAs, {
      playerCounts,
      currentTurn: result.next_turn,
    });
    addLog(formatMoveLog(currentPlayer, targetPlayer, summary, playerCounts));
    return { state: previousState, queriedAs: previousQueriedAs, terminal: isTerminalCounts(playerCounts) };
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
        checkAiEliminations(getPlayerCounts(refreshed, refreshedAs));
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
      const { state: newState, queriedAs: newQueriedAs, terminal } = await syncMoveOutcome(
        currentState,
        currentQueriedAs,
        result,
        aiPlayer,
        targetPlayer,
      );

      if (terminal) {
        finishGame('Game over.');
        break;
      }

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
    const { terminal } = await syncMoveOutcome(
      latestState,
      humanPlayer,
      result,
      humanPlayer,
      drawFromPlayer,
    );

    if (terminal) {
      finishGame('Game over.');
      return;
    }

    await refreshState();
  } catch (error) {
    gameError.textContent = error.message || 'Move failed.';
    drawButton.disabled = false;
  }
});

newGameButton.addEventListener('click', () => {
  if (typeof onNewGame === 'function') {
    onNewGame();
  }
});

function resetViewState() {
  latestState = null;
  aiLoopRunning = false;
  gameEnded = false;
  humanOut = false;
  prevActiveAiSet = new Set();
  turnIndicator.textContent = 'Loading...';
  playersArea.innerHTML = '';
  gameLog.innerHTML = '';
  gameError.textContent = '';
  drawButton.disabled = true;
  cardIndexInput.value = '0';
  cardIndexInput.max = '0';
  newGameButton.classList.add('hidden');
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
}

export function stopGameSession() {
  resetViewState();
  gameId = '';
  humanPlayer = '';
  aiNames = [];
  onNewGame = null;
}

export function startGameSession({ gameId: initialGameId, humanPlayer: initialHumanPlayer, aiNames: initialAiNames, onNewGame: onNewGameCallback }) {
  stopGameSession();

  gameId = initialGameId || '';
  humanPlayer = initialHumanPlayer || '';
  aiNames = Array.isArray(initialAiNames) ? initialAiNames : [];
  onNewGame = typeof onNewGameCallback === 'function' ? onNewGameCallback : null;

  if (!gameId || !humanPlayer) {
    gameError.textContent = 'Missing game context. Start from setup page.';
    drawButton.disabled = true;
    return;
  }

  void refreshState();
  pollIntervalId = window.setInterval(() => {
    if (!aiLoopRunning && !gameEnded) {
      void refreshState();
    }
  }, 2000);
}

window.addEventListener('beforeunload', () => {
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
});
