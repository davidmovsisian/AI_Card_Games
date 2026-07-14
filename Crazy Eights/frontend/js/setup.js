import { createGame, joinGame, startGame } from './api.js';
import { startGameSession, stopGameSession } from './game.js';

const setupForm   = document.getElementById('setup-form');
const setupError  = document.getElementById('setup-error');
const startButton = document.getElementById('start-button');
const setupView   = document.getElementById('setup-view');
const gameView    = document.getElementById('game-view');

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
  setupError.textContent = '';
  startButton.disabled = true;

  const formData   = new FormData(setupForm);
  const playerName = String(formData.get('playerName') || '').trim();
  const aiCount    = Number(formData.get('aiCount') || 1);
  const houseRules = String(formData.get('houseRules') || '').trim();

  if (!playerName) {
    setupError.textContent = 'Please enter your name.';
    startButton.disabled = false;
    return;
  }

  try {
    // 1. Create game
    const game   = await createGame(houseRules);
    const gameId = game.game_id;

    // 2. Join: human first
    await joinGame(gameId, playerName, 'human');

    // 3. Join: AI players
    const aiNames = [];
    for (let i = 1; i <= aiCount; i++) {
      const aiName = `AI_${i}`;
      aiNames.push(aiName);
      await joinGame(gameId, aiName, 'ai');
    }

    // 4. Start
    await startGame(gameId);

    // 5. Switch views and begin session
    showGameView();
    await startGameSession({
      gameId,
      humanPlayer: playerName,
      aiNames,
      onNewGame: showSetupView,
    });
  } catch (error) {
    setupError.textContent = error.message || 'Unable to start game.';
  } finally {
    startButton.disabled = false;
  }
});
