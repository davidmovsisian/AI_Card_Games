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
const CARDS_DRAWN_PER_MOVE = 1;
const CARDS_PER_PAIR = 2;

function addLog(message) {
  const li = document.createElement('li');
  li.textContent = message;
  gameLog.prepend(li);
}

function getPlayerCounts(state, perspectivePlayer = humanPlayer) {
  const counts = {};
  for (const playerName of [humanPlayer, ...aiNames]) {
    if (!playerName) continue;
    if (playerName === humanPlayer && humanOut) {
      counts[playerName] = 0;
    } else if (playerName === perspectivePlayer) {
      counts[playerName] = (state?.your_hand || []).length;
    } else {
      counts[playerName] = Number(state?.opponents_card_counts?.[playerName] || 0);
    }
  }
  return counts;
}

// Derives post-move card counts from the pre-move state by applying the draw transfer
// and removing two cards for each newly formed pair in the current player's hand.
function buildPostMoveCounts(state, perspectivePlayer, currentPlayer, targetPlayer, newPairsFormed = []) {
  const counts = getPlayerCounts(state, perspectivePlayer);
  const pairCount = Array.isArray(newPairsFormed) ? newPairsFormed.length : 0;
  const cardsRemovedByPairs = pairCount * CARDS_PER_PAIR;

  counts[targetPlayer] = Math.max(0, Number(counts[targetPlayer] || 0) - 1);
  counts[currentPlayer] = Math.max(
    0,
    Number(counts[currentPlayer] || 0) + CARDS_DRAWN_PER_MOVE - cardsRemovedByPairs,
  );

  return counts;
}

// Mirrors backend pair-removal behavior for a visible hand snapshot by rank:
// every full pair is removed, and one card remains when a rank count is odd.
function removePairsFromVisibleHand(hand = []) {
  const rankGroups = new Map();
  for (const card of hand) {
    if (!rankGroups.has(card.rank)) {
      rankGroups.set(card.rank, []);
    }
    rankGroups.get(card.rank).push(card);
  }

  const nextHand = [];
  for (const cards of rankGroups.values()) {
    if (cards.length % 2 === 1) {
      nextHand.push(cards[cards.length - 1]);
    }
  }

  return nextHand;
}

// Builds a best-effort post-move state when terminal cleanup removes backend state
// before the frontend can re-fetch it. Uses move details to reflect hand/count changes
// first, then callers finalize game-over UI.
function buildFallbackPostMoveState(previousState, previousPerspectivePlayer, result, currentPlayer, targetPlayer) {
  const nextState = {
    ...previousState,
    your_hand: Array.isArray(previousState?.your_hand) ? [...previousState.your_hand] : [],
    opponents_card_counts: { ...(previousState?.opponents_card_counts || {}) },
    current_turn: result.next_turn,
  };

  if (previousPerspectivePlayer === currentPlayer) {
    const drawnCard = result.details?.drawn_card_visible_to_drawer;
    if (drawnCard?.rank && drawnCard?.suit) {
      nextState.your_hand.push(drawnCard);
    }
    nextState.your_hand = removePairsFromVisibleHand(nextState.your_hand);
  } else if (previousPerspectivePlayer === targetPlayer && nextState.your_hand.length > 0) {
    // Backend does not reveal which specific index was drawn to the target player,
    // so remove one card to reflect count change while preserving hidden-card rules.
    nextState.your_hand = nextState.your_hand.slice(0, -1);
  }

  return nextState;
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
// perspectivePlayer identifies which player's perspective the state is from (their hand is in state.your_hand).
function getNextPlayerName(currentPlayer, state, perspectivePlayer = humanPlayer) {
  const allPlayers = humanOut ? [...aiNames] : [humanPlayer, ...aiNames];
  const activePlayers = allPlayers.filter((name) => {
    if (name === perspectivePlayer) return (state?.your_hand || []).length > 0;
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

// Renders the game board. perspectivePlayer is the player whose perspective the state represents.
function renderState(state, perspectivePlayer = humanPlayer, options = {}) {
  latestState = state;
  const playerCounts = options.playerCounts || getPlayerCounts(state, perspectivePlayer);
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
    } else if (playerName === humanPlayer && perspectivePlayer === humanPlayer) {
      // Only the human player's own perspective should ever reveal face-up cards.
      // If perspectivePlayer is an AI, that AI hand also lives in state.your_hand but must stay hidden.
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
      return { state, perspectivePlayer: humanPlayer };
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
      return { state, perspectivePlayer: aiName };
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
    const { state, perspectivePlayer } = await fetchGameState();
    gameError.textContent = '';
    checkAiEliminations(getPlayerCounts(state, perspectivePlayer));
    renderState(state, perspectivePlayer);

    if (!humanOut && state.current_turn === humanPlayer) {
      // Human's turn — wait for the player to act.
    } else {
      void maybeRunAiTurns(state, perspectivePlayer);
    }
  } catch (error) {
    gameError.textContent = error.message || 'Failed to load game state.';
  }
}

// Fetches the authoritative post-move state when available, but falls back to a
// counts-derived render if a terminal move caused the backend to remove the game
// before the frontend could re-fetch it.
async function syncMoveOutcome(previousState, previousPerspectivePlayer, result, currentPlayer, targetPlayer) {
  const summary = (result.details?.new_pairs_formed || []).length
    ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
    : 'No new pairs.';

  try {
    const { state, perspectivePlayer } = await fetchGameState();
    const playerCounts = getPlayerCounts(state, perspectivePlayer);
    checkAiEliminations(playerCounts);
    renderState(state, perspectivePlayer);
    addLog(formatMoveLog(currentPlayer, targetPlayer, summary, playerCounts));
    return { state, perspectivePlayer, gameOver: Boolean(result.game_over) };
  } catch (error) {
    // A non-terminal move should always be re-fetchable. If the backend state is gone,
    // only tolerate that on a terminal move and render the last known board from counts.
    if (!result.game_over) {
      throw new Error(`Expected backend state to persist for non-terminal move, but post-move fetch failed: ${error.message || String(error)}`);
    }

    const playerCounts = buildPostMoveCounts(
      previousState,
      previousPerspectivePlayer,
      currentPlayer,
      targetPlayer,
      result.details?.new_pairs_formed || [],
    );

    const fallbackState = buildFallbackPostMoveState(
      previousState,
      previousPerspectivePlayer,
      result,
      currentPlayer,
      targetPlayer,
    );

    checkAiEliminations(playerCounts);
    // Only the count-based visuals matter in this terminal fallback render. The underlying
    // state is synthesized from move details so pair removal/count changes are visible first.
    renderState(fallbackState, previousPerspectivePlayer, {
      playerCounts,
      currentTurn: result.next_turn,
    });
    addLog(formatMoveLog(currentPlayer, targetPlayer, summary, playerCounts));
    return { state: fallbackState, perspectivePlayer: previousPerspectivePlayer, gameOver: Boolean(result.game_over) };
  }
}

async function maybeRunAiTurns(initialState, initialPerspectivePlayer = humanPlayer) {
  if (aiLoopRunning || gameEnded) return;

  aiLoopRunning = true;
  try {
    let currentState = initialState;
    let currentPerspectivePlayer = initialPerspectivePlayer;

    while (!gameEnded) {
      // If it is the human's turn and the human is still active, hand control back.
      if (currentState.current_turn === humanPlayer) {
        if (!humanOut) break;
        // Defensive: humanOut is true but we have stale state that still shows the human
        // as the current turn (the backend skips eliminated players, so this is transient).
        // Re-fetch to get the actual next active player before continuing.
        const { state: refreshed, perspectivePlayer: refreshedPerspectivePlayer } = await fetchGameState();
        checkAiEliminations(getPlayerCounts(refreshed, refreshedPerspectivePlayer));
        renderState(refreshed, refreshedPerspectivePlayer);
        currentState = refreshed;
        currentPerspectivePlayer = refreshedPerspectivePlayer;
        continue;
      }

      const aiPlayer = currentState.current_turn;
      const computedTargetPlayer = getNextPlayerName(aiPlayer, currentState, currentPerspectivePlayer);
      const result = await aiMove(gameId, aiPlayer);
      const reportedTargetPlayer = extractTargetFromAction(result.action);
      const targetPlayer = reportedTargetPlayer || computedTargetPlayer;
      if (!targetPlayer) {
        throw new Error('Could not determine target player for AI move.');
      }
      const { state: newState, perspectivePlayer: newPerspectivePlayer, gameOver } = await syncMoveOutcome(
        currentState,
        currentPerspectivePlayer,
        result,
        aiPlayer,
        targetPlayer,
      );

      if (gameOver) {
        finishGame('Game over.');
        break;
      }

      currentState = newState;
      currentPerspectivePlayer = newPerspectivePlayer;
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
    const { gameOver } = await syncMoveOutcome(
      latestState,
      humanPlayer,
      result,
      humanPlayer,
      drawFromPlayer,
    );

    if (gameOver) {
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
