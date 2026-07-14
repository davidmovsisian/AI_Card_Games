import { getState, playCard, drawCard, aiTurn } from './api.js';

// ── DOM refs ──────────────────────────────────────────────────────────────────

const turnIndicator   = document.getElementById('turn-indicator');
const topCardEl       = document.getElementById('top-card');
const activeSuitBadge = document.getElementById('active-suit-badge');
const playersArea     = document.getElementById('players-area');
const actionBar       = document.getElementById('action-bar');
const humanHandEl     = document.getElementById('human-hand');
const playButton      = document.getElementById('play-button');
const drawButton      = document.getElementById('draw-button');
const suitSelector    = document.getElementById('suit-selector');
const newGameButton   = document.getElementById('new-game-button');
const gameError       = document.getElementById('game-error');
const gameLog         = document.getElementById('game-log');

// ── Session state ─────────────────────────────────────────────────────────────

let gameId       = '';
let humanPlayer  = '';
let aiNames      = [];
let onNewGame    = null;

let latestState  = null;
let selectedIndex = null;   // index into human's hand array
let gameEnded    = false;
let aiLoopActive = false;

// ── Suit symbols ──────────────────────────────────────────────────────────────

const SUIT_SYMBOL = { Hearts: '♥', Diamonds: '♦', Clubs: '♣', Spades: '♠' };
const RED_SUITS   = new Set(['Hearts', 'Diamonds']);

function suitSymbol(suit) {
  return SUIT_SYMBOL[suit] || suit;
}

function cardLabel(card) {
  return `${card.rank}${suitSymbol(card.suit)}`;
}

function isRedSuit(suit) {
  return RED_SUITS.has(suit);
}

// ── Logging ───────────────────────────────────────────────────────────────────

function addLog(message) {
  const li = document.createElement('li');
  li.textContent = message;
  gameLog.prepend(li);
}

// ── Card element factory ──────────────────────────────────────────────────────

function makeCardEl(card, index, playable) {
  const el = document.createElement('div');
  el.className = `card face ${isRedSuit(card.suit) ? 'red' : 'black'}`;
  if (playable)  el.classList.add('playable');
  if (!playable) el.classList.add('unplayable');
  el.textContent = cardLabel(card);
  el.dataset.index = index;
  return el;
}

function makeBackEl() {
  const el = document.createElement('div');
  el.className = 'card back';
  el.textContent = '🂠';
  return el;
}

// ── Top card & active suit display ───────────────────────────────────────────

function renderTopCard(state) {
  const tc = state.top_card;
  topCardEl.className = `card face ${isRedSuit(tc.suit) ? 'red' : 'black'}`;
  topCardEl.textContent = cardLabel(tc);

  const activeSuit = state.active_suit;
  if (activeSuit && activeSuit !== tc.suit) {
    // An 8 was played and the suit was changed
    activeSuitBadge.textContent = `${suitSymbol(activeSuit)} ${activeSuit} (declared)`;
    activeSuitBadge.classList.remove('hidden');
  } else {
    activeSuitBadge.classList.add('hidden');
  }
}

// ── Determine playable cards from the human hand ──────────────────────────────

function isPlayable(card, state) {
  if (card.rank === '8') return true;
  return card.suit === state.active_suit || card.rank === state.top_card.rank;
}

// ── Render all players (AI blocks + human block for opponent view) ─────────────

function renderPlayers(state) {
  playersArea.innerHTML = '';

  const allNames = Object.keys(state.players);
  for (const name of allNames) {
    if (name === humanPlayer) continue;   // human hand handled in action bar

    const p = state.players[name];
    const isCurrent = state.current_player === name;

    const block = document.createElement('section');
    block.className = 'player-block' + (isCurrent ? ' current-player' : '');

    const title = document.createElement('h3');
    title.textContent = name;
    if (isCurrent) {
      const badge = document.createElement('span');
      badge.className = 'current-badge';
      badge.textContent = 'Current Turn';
      title.appendChild(badge);
    }
    block.appendChild(title);

    const cards = document.createElement('div');
    cards.className = 'cards';

    // Render face-down card stubs for AI hand count
    const count = p.hand_count || 0;
    if (count === 0) {
      const label = document.createElement('span');
      label.textContent = 'No cards';
      cards.appendChild(label);
    } else {
      for (let i = 0; i < count; i++) {
        cards.appendChild(makeBackEl());
      }
    }

    block.appendChild(cards);
    playersArea.appendChild(block);
  }
}

// ── Render human's own hand in the action bar ─────────────────────────────────

function renderHumanHand(state) {
  humanHandEl.innerHTML = '';
  selectedIndex = null;
  playButton.disabled = true;
  drawButton.disabled = false;

  const playerData = state.players[humanPlayer];
  if (!playerData || playerData.hand === 'HIDDEN' || !Array.isArray(playerData.hand)) {
    // Not the human's turn — action bar hidden; nothing to render
    return;
  }

  const hand = playerData.hand;
  if (hand.length === 0) {
    const msg = document.createElement('span');
    msg.textContent = '(No cards)';
    humanHandEl.appendChild(msg);
    return;
  }

  for (let i = 0; i < hand.length; i++) {
    const card   = hand[i];
    const ok     = isPlayable(card, state);
    const cardEl = makeCardEl(card, i, ok);

    if (ok) {
      cardEl.addEventListener('click', () => selectCard(i, hand.length));
    }

    humanHandEl.appendChild(cardEl);
  }
}

function selectCard(index, handLength) {
  if (index < 0 || index >= handLength) return;
  selectedIndex = index;

  // Update visual selection
  humanHandEl.querySelectorAll('.card').forEach((el, i) => {
    el.classList.toggle('selected', i === index);
  });

  playButton.disabled = false;
}

// ── Master render ─────────────────────────────────────────────────────────────

function renderState(state) {
  latestState = state;
  const isHumanTurn = state.current_player === humanPlayer;

  // Turn indicator
  turnIndicator.textContent = isHumanTurn
    ? '🟢 Your turn!'
    : `⏳ ${state.current_player}'s turn…`;
  turnIndicator.className = 'turn-indicator' + (isHumanTurn ? ' your-turn' : '');

  renderTopCard(state);
  renderPlayers(state);

  // Human action bar: visible only on the human's turn
  if (isHumanTurn && !gameEnded) {
    actionBar.classList.remove('hidden');
    renderHumanHand(state);
  } else {
    actionBar.classList.add('hidden');
  }

  // Winner / game over
  if (state.winner) {
    finishGame(`🎉 ${state.winner} wins!`);
  }
}

// ── Suit selector modal ───────────────────────────────────────────────────────

function showSuitSelector() {
  return new Promise((resolve) => {
    suitSelector.classList.remove('hidden');
    suitSelector.querySelectorAll('.suit-btn').forEach((btn) => {
      btn.onclick = () => {
        suitSelector.classList.add('hidden');
        resolve(btn.dataset.suit);
      };
    });
  });
}

// ── Game-over helper ──────────────────────────────────────────────────────────

function finishGame(message) {
  gameEnded = true;
  actionBar.classList.add('hidden');
  newGameButton.classList.remove('hidden');
  if (message) turnIndicator.textContent = message;
  turnIndicator.className = 'turn-indicator';
  addLog(message);
}

// ── AI turn loop ──────────────────────────────────────────────────────────────

async function runAiTurns(state) {
  if (aiLoopActive || gameEnded) return;
  aiLoopActive = true;

  try {
    let currentState = state;

    while (!gameEnded) {
      const currentPlayer = currentState.current_player;

      // Stop when it's the human's turn
      if (currentPlayer === humanPlayer) break;

      // Trigger AI move on backend
      let result;
      try {
        result = await aiTurn(gameId, currentPlayer);
      } catch (err) {
        addLog(`⚠️ AI move error for ${currentPlayer}: ${err.message}`);
        break;
      }

      // Log what the AI did
      if (result.action) addLog(`${currentPlayer}: ${result.action}`);
      if (result.ai_banter) addLog(`💬 ${currentPlayer}: "${result.ai_banter}"`);

      // Use state from the move response (avoids extra round-trip)
      if (result.state) {
        currentState = result.state;
        renderState(currentState);
        latestState = currentState;
      } else {
        // Fallback: fetch fresh state
        currentState = await getState(gameId);
        renderState(currentState);
      }

      if (currentState.winner) {
        finishGame(`🎉 ${currentState.winner} wins!`);
        return;
      }

      // Small pause so the moves are readable
      await sleep(600);
    }
  } finally {
    aiLoopActive = false;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Human play button ─────────────────────────────────────────────────────────

playButton.addEventListener('click', async () => {
  if (gameEnded || selectedIndex === null || !latestState) return;

  const playerData = latestState.players[humanPlayer];
  if (!playerData || !Array.isArray(playerData.hand)) return;

  const card = playerData.hand[selectedIndex];
  if (!card) return;

  gameError.textContent = '';
  playButton.disabled = true;
  drawButton.disabled = true;

  let declaredSuit = null;

  // If it's an 8, prompt for suit choice
  if (card.rank === '8') {
    declaredSuit = await showSuitSelector();
  }

  try {
    const result = await playCard(gameId, humanPlayer, selectedIndex, declaredSuit);
    addLog(`You played ${cardLabel(card)}${declaredSuit ? ` → declared ${declaredSuit}` : ''}`);

    const newState = result.state;
    renderState(newState);

    if (newState.winner) {
      finishGame(`🎉 ${newState.winner} wins!`);
      return;
    }

    // If it's now an AI turn, kick off the loop
    if (newState.current_player !== humanPlayer) {
      void runAiTurns(newState);
    }
  } catch (err) {
    gameError.textContent = err.message || 'Failed to play card.';
    // Re-enable buttons so the player can retry
    playButton.disabled = selectedIndex === null;
    drawButton.disabled = false;
  }
});

// ── Human draw button ─────────────────────────────────────────────────────────

drawButton.addEventListener('click', async () => {
  if (gameEnded || !latestState) return;
  if (latestState.current_player !== humanPlayer) return;

  gameError.textContent = '';
  drawButton.disabled = true;
  playButton.disabled = true;

  try {
    const result = await drawCard(gameId, humanPlayer);

    if (result.drawn_cards && result.drawn_cards.length) {
      const labels = result.drawn_cards.map(cardLabel).join(', ');
      addLog(`You drew: ${labels}`);
    } else {
      addLog('You drew a card.');
    }

    const newState = result.state;
    renderState(newState);

    if (newState.winner) {
      finishGame(`🎉 ${newState.winner} wins!`);
      return;
    }

    if (newState.current_player !== humanPlayer) {
      void runAiTurns(newState);
    }
  } catch (err) {
    gameError.textContent = err.message || 'Failed to draw card.';
    // RE-ENABLE BOTH BUTTONS ON FAILURE:
    drawButton.disabled = false;
    playButton.disabled = selectedIndex === null; // Keep disabled unless a card was active
  }
});

// ── New game ──────────────────────────────────────────────────────────────────

newGameButton.addEventListener('click', () => {
  if (typeof onNewGame === 'function') onNewGame();
});

// ── Session lifecycle ─────────────────────────────────────────────────────────

function resetViewState() {
  latestState    = null;
  selectedIndex  = null;
  gameEnded      = false;
  aiLoopActive   = false;

  turnIndicator.textContent = 'Loading…';
  turnIndicator.className   = 'turn-indicator';
  topCardEl.textContent     = '—';
  topCardEl.className       = 'card face';
  activeSuitBadge.classList.add('hidden');
  playersArea.innerHTML     = '';
  humanHandEl.innerHTML     = '';
  gameLog.innerHTML         = '';
  gameError.textContent     = '';
  actionBar.classList.add('hidden');
  suitSelector.classList.add('hidden');
  newGameButton.classList.add('hidden');
  playButton.disabled       = true;
  drawButton.disabled       = false;
}

export function stopGameSession() {
  resetViewState();
  gameId      = '';
  humanPlayer = '';
  aiNames     = [];
  onNewGame   = null;
}

export async function startGameSession({
  gameId: id,
  humanPlayer: human,
  aiNames: ais,
  onNewGame: onNew,
}) {
  stopGameSession();

  gameId      = id      || '';
  humanPlayer = human   || '';
  aiNames     = Array.isArray(ais) ? ais : [];
  onNewGame   = typeof onNew === 'function' ? onNew : null;

  if (!gameId || !humanPlayer) {
    gameError.textContent = 'Missing game context. Start from the setup page.';
    return;
  }

  try {
    const state = await getState(gameId);
    renderState(state);

    if (state.winner) {
      finishGame(`🎉 ${state.winner} wins!`);
      return;
    }

    if (state.current_player !== humanPlayer) {
      void runAiTurns(state);
    }
  } catch (err) {
    gameError.textContent = err.message || 'Failed to load game state.';
  }
}
