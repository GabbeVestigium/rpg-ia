// Perfil do jogador: quem você é em todas as histórias.

import { api } from './api.js';
import { buildForm, readForm } from './forms.js';
import { state } from './state.js';
import { $, closeModal, openModal, toast } from './util.js';

const FIELDS = [
  { key: 'name', label: 'Seu nome', type: 'text' },
  { key: 'age', label: 'Idade (mínimo 18)', type: 'number', min: 18, max: 999 },
  { key: 'appearance', label: 'Aparência', type: 'textarea', rows: 3,
    hint: 'Ex: alto, barba por fazer, cicatriz na sobrancelha.' },
  { key: 'about', label: 'Jeito de agir e falar', type: 'textarea', rows: 4,
    hint: 'Ex: fala pouco, desconfia de elogio, rói a unha quando mente. Os personagens usam isso para reagir a você.' },
];

export async function loadProfile() {
  try { state.profile = await api('/api/profile'); } catch { state.profile = null; }
  return state.profile;
}

export async function openProfile() {
  const profile = (await loadProfile()) || { name: '', age: 25, appearance: '', about: '' };
  buildForm($('profile-form'), FIELDS, profile);
  openModal('modal-profile');
}

export async function saveProfile() {
  try {
    state.profile = await api('/api/profile', { method: 'PUT', body: readForm($('profile-form'), FIELDS) });
    closeModal('modal-profile');
    toast('Perfil salvo.', 'success');
  } catch (e) {
    toast(e.message, 'error', 7000);
  }
}
