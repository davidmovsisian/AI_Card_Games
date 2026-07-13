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
let eliminatedPlayers = new Set();

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

function addLog(message) {
  const li = document.createElement('li');
  li.textContent = message;
  gameLog.prepend(li);
}

function formatMoveLog(currentPlayer, targetPlayer, result) {
  const pairs = result.details?.new_pairs_formed || [];
  const summary = pairs.length ? `New pairs: ${pairs.join(', ')}` : 'No new pairs.';
  return `${currentPlayer} drew from ${targetPlayer} | ${summary}`;
}

// ---------------------------------------------------------------------------
// Rendering — driven purely from the state returned by getPlayerState
// ---------------------------------------------------------------------------

function renderState(state) {
  latestState = state;
  turnIndicator.textContent = `Current turn: ${state.current_turn}`;
  playersArea.innerHTML = '';

  // Build a unified card-count map for every known player.
  // The human's own face-up cards are in state.your_hand; everyone else is a count.
  const allPlayers = [humanPlayer, ...aiNames];
  for (const playerName of allPlayers) {
    const section = document.createElement('section');
    section.className = 'player-block';

    const title = document.createElement('h3');
    title.textContent = playerName === humanPlayer ? `${playerName} (You)` : playerName;
    section.appendChild(title);

    const cards = document.createElement('div');
    cards.className = 'cards';

    if (playerName === humanPlayer) {
      if (humanOut) {
        cards.appendChild(makeLabel('(Eliminated)'));
      } else {
        const hand = state.your_hand || [];
        if (hand.length === 0) {
          cards.appendChild(makeLabel('(No cards)'));
        } else {
          for (const card of hand) {
            const cardEl = document.createElement('div');
            cardEl.className = 'card';
            cardEl.textContent = `${card.rank} of ${card.suit}`;
            cards.appendChild(cardEl);
          }
        }
      }
    } else {
      const count = Number(state.opponents_card_counts?.[playerName] || 0);
      if (count === 0) {
        cards.appendChild(makeLabel('(Eliminated)'));
      } else {
        for (let i = 0; i < count; i += 1) {
          const back = document.createElement('div');
          back.className = 'card back';
          back.textContent = 'Hidden';
          cards.appendChild(back);
        }
      }
    }

    section.appendChild(cards);
    playersArea.appendChild(section);
  }

  // Enable draw button only when it is the human's turn and they are still active.
  const isHumanTurn = !humanOut && state.current_turn === humanPlayer;
  drawButton.disabled = !isHumanTurn || gameEnded;

  if (isHumanTurn) {
    // Find the next active opponent the human will draw from.
    // The backend always targets get_next_player(humanPlayer), so we replicate
    // that ordering here only to set the input max — the backend enforces the
    // actual target; this is purely for UX clamping.
    const nextPlayer = findNextActiveOpponent(state);
    if (!nextPlayer) {
      drawButton.disabled = true;
      cardIndexInput.max = '0';
    } else {
      const max = Math.max(0, Number(state.opponents_card_counts?.[nextPlayer] || 0) - 1);
      cardIndexInput.max = String(max);
      if (Number(cardIndexInput.value) > max) {
        cardIndexInput.value = String(max);
      }
    }
  }
}

function makeLabel(text) {
  const el = document.createElement('div');
  el.textContent = text;
  return el;
}

// Returns the first AI opponent that still has cards, in aiNames order.
// This mirrors the backend's get_next_player which iterates insertion order.
function findNextActiveOpponent(state) {
  for (const name of aiNames) {
    if (Number(state.opponents_card_counts?.[name] || 0) > 0) return name;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Game-over / elimination helpers
// ---------------------------------------------------------------------------

function finishGame(message) {
  gameEnded = true;
  drawButton.disabled = true;
  gameError.textContent = '';
  newGameButton.classList.remove('hidden');
  if (message) turnIndicator.textContent = message;
}

// Called after every move with the MoveResponse from the backend.
// Uses player_active and target_player_active to track eliminations directly,
// so fetchState is never called for players that are no longer in the game.
function applyMoveResult(result, actingPlayer, targetPlayer) {
  // Log AI commentary when present.
  if (result.ai_commentary) {
    addLog(`[${actingPlayer}]: ${result.ai_commentary}`);
  }

  // Check acting player elimination.
  if (result.player_active === false) {
    eliminatedPlayers.add(actingPlayer);
    if (actingPlayer === humanPlayer) {
      humanOut = true;
      drawButton.disabled = true;
      addLog(`${humanPlayer}: you have been eliminated.`);
    } else {
      addLog(`${actingPlayer} has been eliminated.`);
    }
  }

  // Check target player elimination.
  if (result.target_player_active === false && targetPlayer) {
    eliminatedPlayers.add(targetPlayer);
    if (targetPlayer === humanPlayer) {
      humanOut = true;
      drawButton.disabled = true;
      addLog(`${humanPlayer}: you have been eliminated.`);
    } else {
      addLog(`${targetPlayer} has been eliminated.`);
    }
  }
}

// ---------------------------------------------------------------------------
// Final-state synthesis — used only on game_over to update the board from the
// move result before the backend game record is gone.
// ---------------------------------------------------------------------------

// Applies the terminal move to latestState so the board reflects the final hand.
// - Target player: count -1 (they lost the drawn card).
// - Acting player: 0 if player_active===false (eliminated), unchanged if still active.
// - Human acting: also pushes the drawn card onto your_hand and strips pairs.
function buildFinalState(result, actingPlayer, targetPlayer) {
  const base = latestState;
  if (!base) return null;

  const nextState = {
    ...base,
    your_hand: [...(base.your_hand || [])],
    opponents_card_counts: { ...(base.opponents_card_counts || {}) },
    current_turn: result.next_turn,
  };

  // Decrement target player's count.
  if (targetPlayer && targetPlayer in nextState.opponents_card_counts) {
    nextState.opponents_card_counts[targetPlayer] = Math.max(
      0,
      nextState.opponents_card_counts[targetPlayer] - 1,
    );
  }

  if (actingPlayer === humanPlayer) {
    // Human drew a card — add it to their visible hand then strip pairs.
    const drawn = result.details?.drawn_card_visible_to_drawer;
    if (drawn?.rank && drawn?.suit) {
      nextState.your_hand.push(drawn);
    }
    nextState.your_hand = removePairs(nextState.your_hand);
  } else if (actingPlayer in nextState.opponents_card_counts) {
    // AI acting player: player_active tells us directly whether they survived.
    nextState.opponents_card_counts[actingPlayer] = result.player_active === false ? 0 : nextState.opponents_card_counts[actingPlayer];
  }

  return nextState;
}

// Removes all fully paired ranks from a hand array, leaving one card when the
// count for a rank is odd. Mirrors engine Player.remove_pairs() exactly.
function removePairs(hand) {
  const groups = new Map();
  for (const card of hand) {
    if (!groups.has(card.rank)) groups.set(card.rank, []);
    groups.get(card.rank).push(card);
  }
  const kept = [];
  for (const cards of groups.values()) {
    if (cards.length % 2 === 1) kept.push(cards[cards.length - 1]);
  }
  return kept;
}

// ---------------------------------------------------------------------------
// State fetch — always from humanPlayer's perspective while they are active.
// Falls back to first available AI once the human is out, to keep the board
// rendering after the human is eliminated.
// ---------------------------------------------------------------------------

async function fetchState() {
  if (!humanOut) {
    return getPlayerState(gameId, humanPlayer);
  }
  // Human is eliminated — query through the first AI we know is still active.
  for (const aiName of aiNames) {
    if (!eliminatedPlayers.has(aiName)) {
      return getPlayerState(gameId, aiName);
    }
  }
  throw new Error('No active players remain to query state.');
}

// ---------------------------------------------------------------------------
// Initial load
// ---------------------------------------------------------------------------

async function loadInitialState() {
  try {
    const state = await fetchState();
    gameError.textContent = '';
    renderState(state);

    if (!humanOut && state.current_turn === humanPlayer) {
      // Human moves first — wait for button click.
    } else {
      void runAiTurns(state);
    }
  } catch (error) {
    gameError.textContent = error.message || 'Failed to load game state.';
  }
}

// ---------------------------------------------------------------------------
// AI turn loop — runs consecutive AI turns until it is the human's turn,
// the human is eliminated (in which case it runs until game over), or the
// game ends.
// ---------------------------------------------------------------------------

async function runAiTurns(initialState) {
  if (aiLoopRunning || gameEnded) return;
  aiLoopRunning = true;

  try {
    let state = initialState;

    while (!gameEnded) {
      const currentTurn = state.current_turn;

      // Hand control back to the human when it is their turn and they are active.
      if (currentTurn === humanPlayer && !humanOut) break;

      const result = await aiMove(gameId, currentTurn);
      const targetPlayer = extractTargetFromAction(result.action);
      addLog(formatMoveLog(currentTurn, targetPlayer ?? '?', result));
      applyMoveResult(result, currentTurn, targetPlayer);

      if (result.game_over) {
        const finalState = buildFinalState(result, currentTurn, targetPlayer);
        if (finalState) renderState(finalState);
        finishGame('Game over.');
        return;
      }

      // Fetch fresh state after the AI move so the board stays accurate.
      state = await fetchState();
      renderState(state);
    }
  } catch (error) {
    gameError.textContent = error.message || 'AI move failed.';
  } finally {
    aiLoopRunning = false;
  }
}

// Parses "X drew a card from Y" → "Y".
function extractTargetFromAction(actionText) {
  const match = String(actionText || '').match(/\bdrew a card from (.+)$/i);
  return match ? match[1].trim() : null;
}

// ---------------------------------------------------------------------------
// Human draw button
// ---------------------------------------------------------------------------

drawButton.addEventListener('click', async () => {
  if (!latestState || latestState.current_turn !== humanPlayer || gameEnded || humanOut) return;

  gameError.textContent = '';
  drawButton.disabled = true;

  try {
    const cardIndex = Number(cardIndexInput.value);
    const result = await humanMove(gameId, humanPlayer, cardIndex);
    const targetPlayer = extractTargetFromAction(result.action);
    addLog(formatMoveLog(humanPlayer, targetPlayer ?? '?', result));
    applyMoveResult(result, humanPlayer, targetPlayer);

    if (result.game_over) {
      const finalState = buildFinalState(result, humanPlayer, targetPlayer);
      if (finalState) renderState(finalState);
      finishGame('Game over.');
      return;
    }

    // Fetch state after the human move and hand off to AI if needed.
    const state = await fetchState();
    renderState(state);

    if (state.current_turn !== humanPlayer) {
      void runAiTurns(state);
    }
  } catch (error) {
    gameError.textContent = error.message || 'Move failed.';
    drawButton.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// New game button
// ---------------------------------------------------------------------------

newGameButton.addEventListener('click', () => {
  if (typeof onNewGame === 'function') onNewGame();
});

// ---------------------------------------------------------------------------
// Session lifecycle
// ---------------------------------------------------------------------------

function resetViewState() {
  latestState = null;
  aiLoopRunning = false;
  gameEnded = false;
  humanOut = false;
  eliminatedPlayers = new Set();
  turnIndicator.textContent = 'Loading...';
  playersArea.innerHTML = '';
  gameLog.innerHTML = '';
  gameError.textContent = '';
  drawButton.disabled = true;
  cardIndexInput.value = '0';
  cardIndexInput.max = '0';
  newGameButton.classList.add('hidden');
}

export function stopGameSession() {
  resetViewState();
  gameId = '';
  humanPlayer = '';
  aiNames = [];
  onNewGame = null;
}

export function startGameSession({
  gameId: initialGameId,
  humanPlayer: initialHumanPlayer,
  aiNames: initialAiNames,
  onNewGame: onNewGameCallback,
}) {
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

  void loadInitialState();
}