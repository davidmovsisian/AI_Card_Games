import { getState, playCard, drawCard, declareSuit } from './api.js';

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
let busy         = false;   // true while a request / event replay is in progress

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
  if (state.game_over) {
    if (!gameEnded) {
      finishGame(gameOverMessage(state));
    } else {
      // re-render of the final state: keep the result message, not "X's turn"
      turnIndicator.textContent = gameOverMessage(state);
      turnIndicator.className = 'turn-indicator';
    }
  }
}

function gameOverMessage(state) {
  if (state.end_reason === 'stalemate') {
    return state.winner
      ? `🤝 Stalemate — ${state.winner} has the fewest cards and wins!`
      : '🤝 Stalemate — nobody can move, it\'s a tie.';
  }
  return `🎉 ${state.winner} wins!`;
}

// ── Suit selector modal ───────────────────────────────────────────────────────

function showSuitSelector(message = 'You played an 8 — choose the new suit:') {
  return new Promise((resolve) => {
    const prompt = suitSelector.querySelector('p');
    if (prompt) prompt.textContent = message;
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

// ── Event replay ──────────────────────────────────────────────────────────────
// The backend plays every AI turn in one request and returns the events that happened.
// We replay them one by one so the moves stay readable.

function logEvent(ev) {
  if (ev.type === 'error') return;
  const text = ev.player === humanPlayer && ev.text.startsWith(ev.player)
    ? `You${ev.text.slice(ev.player.length)}`
    : ev.text;
  addLog(text);
  if (ev.banter) addLog(`💬 ${ev.player}: "${ev.banter}"`);
}

async function replayEvents(events, finalState) {
  for (const ev of events || []) {
    logEvent(ev);
    renderState(ev.state);
    if (ev.player !== humanPlayer) await sleep(600);   // small pause after each AI move
  }
  if (finalState) renderState(finalState);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// After drawing a playable 8 the human must choose the new suit.
async function resolvePendingSuit(state) {
  while (!gameEnded && state.pending_suit_player === humanPlayer) {
    const suit = await showSuitSelector('You drew an 8 — choose the new suit:');
    try {
      const result = await declareSuit(gameId, humanPlayer, suit);
      state = result.state;
      await replayEvents(result.events, result.state);
    } catch (err) {
      gameError.textContent = err.message || 'Failed to declare suit.';
    }
  }
}

// ── Human play button ─────────────────────────────────────────────────────────

playButton.addEventListener('click', async () => {
  if (busy || gameEnded || selectedIndex === null || !latestState) return;

  const playerData = latestState.players[humanPlayer];
  if (!playerData || !Array.isArray(playerData.hand)) return;

  const card = playerData.hand[selectedIndex];
  if (!card) return;

  busy = true;
  gameError.textContent = '';
  playButton.disabled = true;
  drawButton.disabled = true;

  try {
    // If it's an 8, prompt for suit choice
    const declaredSuit = card.rank === '8' ? await showSuitSelector() : null;

    const result = await playCard(gameId, humanPlayer, selectedIndex, declaredSuit);
    await replayEvents(result.events, result.state);
  } catch (err) {
    gameError.textContent = err.message || 'Failed to play card.';
    // Re-enable buttons so the player can retry
    playButton.disabled = selectedIndex === null;
    drawButton.disabled = false;
  } finally {
    busy = false;
  }
});

// ── Human draw button ─────────────────────────────────────────────────────────

drawButton.addEventListener('click', async () => {
  if (busy || gameEnded || !latestState) return;
  if (latestState.current_player !== humanPlayer) return;

  busy = true;
  gameError.textContent = '';
  drawButton.disabled = true;
  playButton.disabled = true;

  try {
    const result = await drawCard(gameId, humanPlayer);
    await replayEvents(result.events, result.state);
    await resolvePendingSuit(result.state);
  } catch (err) {
    gameError.textContent = err.message || 'Failed to draw card.';
    drawButton.disabled = false;
    playButton.disabled = selectedIndex === null;
  } finally {
    busy = false;
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
  busy           = false;

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
  initialEvents = null,
  initialState = null,
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

  busy = true;
  try {
    if (initialEvents) {
      // Events from /start: the deal, plus any AI moves made before the human's first turn
      await replayEvents(initialEvents, initialState);
    } else {
      renderState(await getState(gameId));
    }
  } catch (err) {
    gameError.textContent = err.message || 'Failed to load game state.';
  } finally {
    busy = false;
  }
}
