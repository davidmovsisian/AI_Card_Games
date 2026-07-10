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

function addLog(message) {
  const li = document.createElement('li');
  li.textContent = message;
  gameLog.prepend(li);
}

function getActivePlayers(state) {
  if (!state) return [humanPlayer, ...aiNames];

  const opponentNames = Object.keys(state.opponents_card_counts || {});
  const names = [humanPlayer, ...opponentNames.filter((name) => name !== humanPlayer)];

  for (const aiName of aiNames) {
    if (!names.includes(aiName) && opponentNames.includes(aiName)) {
      names.push(aiName);
    }
  }

  return names;
}

function getNextPlayerName(currentPlayer, state) {
  const activePlayers = getActivePlayers(state);
  const currentIndex = activePlayers.indexOf(currentPlayer);
  if (currentIndex < 0 || activePlayers.length === 0) return null;
  return activePlayers[(currentIndex + 1) % activePlayers.length];
}

function renderState(state) {
  latestState = state;
  const currentTurn = state.current_turn;
  turnIndicator.textContent = `Current turn: ${currentTurn}`;

  playersArea.innerHTML = '';

  const activePlayers = getActivePlayers(state);
  for (const playerName of activePlayers) {
    const section = document.createElement('section');
    section.className = 'player-block';

    const title = document.createElement('h3');
    title.textContent = playerName === humanPlayer ? `${playerName} (You)` : playerName;
    section.appendChild(title);

    const cards = document.createElement('div');
    cards.className = 'cards';

    if (playerName === humanPlayer) {
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

  drawButton.disabled = currentTurn !== humanPlayer || gameEnded;
  if (currentTurn === humanPlayer) {
    const nextPlayer = getNextPlayerName(humanPlayer, state);
    const nextCount = Number(state.opponents_card_counts?.[nextPlayer] || 0);
    const max = Math.max(0, nextCount - 1);
    cardIndexInput.max = String(max);
    if (Number(cardIndexInput.value) > max) {
      cardIndexInput.value = String(max);
    }
  }
}

async function refreshState() {
  try {
    const state = await getPlayerState(gameId, humanPlayer);
    gameError.textContent = '';
    renderState(state);

    if (state.current_turn !== humanPlayer) {
      void maybeRunAiTurns(state);
    }
  } catch (error) {
    const message = error.message || '';
    if (message.toLowerCase().includes('player not in this game')) {
      gameEnded = true;
      drawButton.disabled = true;
      turnIndicator.textContent = 'Game over for you.';
      addLog('You are out of the game.');
      return;
    }

    gameError.textContent = message || 'Failed to load game state.';
  }
}

async function maybeRunAiTurns(state) {
  if (aiLoopRunning || gameEnded) return;

  aiLoopRunning = true;
  try {
    let currentState = state;
    while (!gameEnded && currentState.current_turn !== humanPlayer) {
      const aiPlayer = currentState.current_turn;
      const fromPlayer = getNextPlayerName(aiPlayer, currentState) || 'unknown player';
      const result = await aiMove(gameId, aiPlayer);
      const summary = (result.details?.new_pairs_formed || []).length
        ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
        : 'No new pairs.';
      addLog(`Current: ${aiPlayer} | Picked from: ${fromPlayer} | ${summary}`);

      if (result.game_over) {
        gameEnded = true;
        turnIndicator.textContent = 'Game over.';
        drawButton.disabled = true;
        break;
      }

      currentState = await getPlayerState(gameId, humanPlayer);
      renderState(currentState);
    }
  } catch (error) {
    gameError.textContent = error.message || 'AI move failed.';
  } finally {
    aiLoopRunning = false;
  }
}

drawButton.addEventListener('click', async () => {
  if (!latestState || latestState.current_turn !== humanPlayer || gameEnded) return;

  gameError.textContent = '';
  drawButton.disabled = true;

  try {
    const nextPlayer = getNextPlayerName(humanPlayer, latestState) || 'unknown player';
    const cardIndex = Number(cardIndexInput.value);

    const result = await humanMove(gameId, humanPlayer, cardIndex);
    const summary = (result.details?.new_pairs_formed || []).length
      ? `New pairs: ${result.details.new_pairs_formed.join(', ')}`
      : 'No new pairs.';

    addLog(`Current: ${humanPlayer} | Picked from: ${nextPlayer} | ${summary}`);

    if (result.game_over) {
      gameEnded = true;
      turnIndicator.textContent = 'Game over.';
      drawButton.disabled = true;
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
  window.setInterval(() => {
    if (!aiLoopRunning && !gameEnded) {
      void refreshState();
    }
  }, 2000);
}
