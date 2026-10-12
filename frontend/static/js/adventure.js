// Criar aventura: o jogador escreve uma ideia e o narrador monta a história no servidor.

import { api } from './api.js';
import { loadCharacters, openModeModal } from './screens.js';
import { $, closeModal, escapeHtml, openModal, toast } from './util.js';

const STEPS = [
  'O narrador está pensando no mundo...',
  'Escolhendo quem você vai encontrar...',
  'Dando nome e voz a cada personagem...',
  'Escrevendo a primeira cena...',
  'Quase lá, revisando os detalhes...',
];

let options = null;
let genre = '';
let busy = false;
let stepTimer = null;

function renderGenres() {
  $('adventure-genres').innerHTML = (options?.genres || []).map((g) =>
    `<button class="tag-chip${g === genre ? ' active' : ''}" data-action="pick-genre" data-genre="${escapeHtml(g)}">${escapeHtml(g)}</button>`,
  ).join('');
}

function setBusy(on) {
  busy = on;
  $('adventure-form').style.display = on ? 'none' : '';
  $('adventure-loading').style.display = on ? '' : 'none';
  $('btn-create-adventure').disabled = on;
  clearInterval(stepTimer);
  if (!on) return;
  let i = 0;
  $('adventure-loading-text').textContent = STEPS[0];
  stepTimer = setInterval(() => {
    i = Math.min(i + 1, STEPS.length - 1);
    $('adventure-loading-text').textContent = STEPS[i];
  }, 12000);
}

export async function openAdventure() {
  if (!options) {
    try { options = await api('/api/adventure/options'); } catch { options = { genres: [], surprises: [] }; }
  }
  if (!busy) {
    $('adventure-error').style.display = 'none';
    renderGenres();
  }
  openModal('modal-adventure');
  if (!busy) $('adventure-idea').focus();
}

export function closeAdventure() {
  closeModal('modal-adventure');
}

export function pickGenre(name) {
  genre = genre === name ? '' : name;
  renderGenres();
}

export function surpriseAdventure() {
  const list = options?.surprises || [];
  if (!list.length) return;
  const current = $('adventure-idea').value;
  let idea = current;
  while (list.length > 1 && idea === current) idea = list[Math.floor(Math.random() * list.length)];
  $('adventure-idea').value = idea;
}

export async function createAdventure() {
  if (busy) return;
  const err = $('adventure-error');
  err.style.display = 'none';
  setBusy(true);
  try {
    const res = await api('/api/adventure', { method: 'POST', body: { idea: $('adventure-idea').value, genre } });
    await loadCharacters();
    $('adventure-idea').value = '';
    genre = '';
    const stillOpen = $('modal-adventure').style.display !== 'none';
    closeModal('modal-adventure');
    if (stillOpen) await openModeModal(res.id);
    else toast(`Sua aventura "${res.name}" está pronta na galeria.`, 'success', 8000);
  } catch (e) {
    err.textContent = e.message;
    err.style.display = 'block';
    if ($('modal-adventure').style.display === 'none') toast(`Aventura: ${e.message}`, 'error', 8000);
  } finally {
    setBusy(false);
  }
}
