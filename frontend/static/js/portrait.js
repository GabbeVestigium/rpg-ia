// Retrato do personagem e geração de cenas (Stable Diffusion).

import { api } from './api.js';
import { state } from './state.js';
import { $, toast } from './util.js';
import { appendSceneImage } from './messages.js';

export async function refreshSdStatus() {
  try {
    state.sdAvailable = (await api('/api/sd/status')).available;
  } catch {
    state.sdAvailable = false;
  }
  return state.sdAvailable;
}

export async function loadPortrait(charId) {
  const img = $('char-portrait-img');
  const placeholder = $('char-portrait-placeholder');
  const btn = $('btn-generate-portrait');

  const showPlaceholder = (canGenerate) => {
    img.style.display = 'none';
    placeholder.style.display = 'flex';
    btn.style.display = canGenerate ? 'flex' : 'none';
  };

  try {
    const data = await api(`/api/sd/check-portrait/${charId}`);
    if (data.exists) {
      img.onload = () => {
        img.style.display = 'block';
        placeholder.style.display = 'none';
        btn.style.display = 'none';
      };
      img.onerror = () => showPlaceholder(false);
      img.src = `${data.image_path}?t=${Date.now()}`;
    } else {
      showPlaceholder(await refreshSdStatus());
    }
  } catch {
    showPlaceholder(false);
  }
}

function setBusy(on, text) {
  $('portrait-loading').style.display = on ? 'flex' : 'none';
  if (text) $('portrait-loading-text').textContent = text;
  $('btn-scene').disabled = on;
  $('user-input').disabled = on;
  $('send-btn').disabled = on;
}

export async function generatePortrait() {
  if (!state.character) return;
  if (!(await refreshSdStatus())) {
    toast('Stable Diffusion offline. Inicie o Automatic1111 com --api --medvram --xformers.', 'error', 8000);
    return;
  }
  $('btn-generate-portrait').style.display = 'none';
  setBusy(true, 'Gerando retrato...');
  try {
    await api('/api/sd/generate-portrait', { method: 'POST', body: { character_id: state.character.id } });
    await loadPortrait(state.character.id);
  } catch (e) {
    toast(e.message, 'error', 8000);
    $('btn-generate-portrait').style.display = 'flex';
  } finally {
    setBusy(false);
  }
}

export async function generateScene() {
  if (!state.session || state.streaming) return;
  setBusy(true, 'Gerando cena...');
  try {
    const image = await api('/api/scene/generate', { method: 'POST', body: { session_id: state.session } });
    state.images.push(image);
    appendSceneImage(image);
  } catch (e) {
    toast(e.message, 'error', 8000);
  } finally {
    setBusy(false);
  }
}
