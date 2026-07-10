import { createGame, getApiBaseUrl, joinGame, setApiBaseUrl, startGame } from './api.js';

const setupForm = document.getElementById('setup-form');
const errorEl = document.getElementById('setup-error');
const apiBaseInput = document.getElementById('api-base-url');
const startButton = document.getElementById('start-button');

apiBaseInput.value = getApiBaseUrl();

setupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorEl.textContent = '';
  startButton.disabled = true;

  const formData = new FormData(setupForm);
  const playerName = String(formData.get('playerName') || '').trim();
  const aiCount = Number(formData.get('aiCount') || 1);
  const houseRules = String(formData.get('houseRules') || '').trim();
  const apiBaseUrl = String(formData.get('apiBaseUrl') || '').trim();

  if (!playerName) {
    errorEl.textContent = 'Please enter your player name.';
    startButton.disabled = false;
    return;
  }

  try {
    setApiBaseUrl(apiBaseUrl);

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

    const params = new URLSearchParams({
      game_id: gameId,
      player_name: playerName,
      ai_names: aiNames.join(','),
    });

    const gameUrl = `./game.html?${params.toString()}`;
    const opened = window.open(gameUrl, '_blank');
    if (!opened) {
      window.location.href = gameUrl;
    }
  } catch (error) {
    errorEl.textContent = error.message || 'Unable to start game.';
  } finally {
    startButton.disabled = false;
  }
});
