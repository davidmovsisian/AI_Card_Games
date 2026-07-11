import { createGame, joinGame, startGame } from './api.js';
import { startGameSession, stopGameSession } from './game.js';

const setupForm = document.getElementById('setup-form');
const errorEl = document.getElementById('setup-error');
const startButton = document.getElementById('start-button');
const setupView = document.getElementById('setup-view');
const gameView = document.getElementById('game-view');

function showSetupView() {
  stopGameSession();
  gameView.classList.add('hidden');
  setupView.classList.remove('hidden');
}

function showGameView() {
  setupView.classList.add('hidden');
  gameView.classList.remove('hidden');
}

setupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorEl.textContent = '';
  startButton.disabled = true;

  const formData = new FormData(setupForm);
  const playerName = String(formData.get('playerName') || '').trim();
  const aiCount = Number(formData.get('aiCount') || 1);
  const houseRules = String(formData.get('houseRules') || '').trim();

  if (!playerName) {
    errorEl.textContent = 'Please enter your player name.';
    startButton.disabled = false;
    return;
  }

  try {
    const game = await createGame(houseRules);
    const gameId = game.game_id;

    await joinGame(gameId, playerName, 'human');

    const aiNames = [];
    for (let i = 1; i <= aiCount; i += 1) {
      const aiName = `AI_${i}`;
      aiNames.push(aiName);
      await joinGame(gameId, aiName, 'ai');
    }

    await startGame(gameId);

    showGameView();
    startGameSession({
      gameId,
      humanPlayer: playerName,
      aiNames,
      onNewGame: showSetupView,
    });
  } catch (error) {
    errorEl.textContent = error.message || 'Unable to start game.';
  } finally {
    startButton.disabled = false;
  }
});