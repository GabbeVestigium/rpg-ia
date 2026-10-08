// Editor de personagens (criar, editar, apagar). O servidor recusa menores de idade.

import { api } from './api.js';
import { buildForm, readForm } from './forms.js';
import { state } from './state.js';
import { $, closeModal, openModal, toast } from './util.js';
import { loadCharacters } from './screens.js';

let editingId = null;
let currentFields = [];

const BLANK = {
  name: '', age: 25, gender: 'female', avatar_emoji: '🧙', group: false, world_id: '', tags: '',
  summary: '', description: '', personality: '', scenario: '', first_message: '',
  example_dialogue: '', appearance_tags: '',
};

function fields(worlds) {
  return [
    { key: 'name', label: 'Nome', type: 'text' },
    { key: 'age', label: 'Idade (mínimo 18)', type: 'number', min: 18, max: 9999 },
    { key: 'gender', label: 'Gênero (usado nas imagens)', type: 'select',
      options: [['female', 'Feminino'], ['male', 'Masculino'], ['other', 'Outro']] },
    { key: 'avatar_emoji', label: 'Emoji', type: 'text' },
    { key: 'group', label: 'Personagem de grupo (o narrador interpreta um elenco)', type: 'checkbox' },
    { key: 'world_id', label: 'Mundo', type: 'select', options: [['', 'Nenhum'], ...worlds.map((w) => [w.id, w.name])] },
    { key: 'tags', label: 'Tags (separadas por vírgula)', type: 'text' },
    { key: 'summary', label: 'Resumo para o card (1 ou 2 frases, opcional)', type: 'text' },
    { key: 'description', label: 'Aparência e história', type: 'textarea', rows: 5 },
    { key: 'personality', label: 'Personalidade e jeito de falar', type: 'textarea', rows: 5 },
    { key: 'scenario', label: 'Cenário inicial', type: 'textarea', rows: 3 },
    { key: 'first_message', label: 'Primeira mensagem do personagem', type: 'textarea', rows: 4,
      hint: 'Use *asteriscos* para ações e "aspas" para falas.' },
    { key: 'example_dialogue', label: 'Falas de exemplo (opcional)', type: 'textarea', rows: 4,
      hint: 'Duas ou três falas no estilo certo ensinam o modelo a soar como o personagem.' },
    { key: 'appearance_tags', label: 'Tags de aparência para o Stable Diffusion (inglês)', type: 'text',
      hint: 'Ex: 1girl, long black hair, violet eyes, scar on forearm. Mantém o rosto igual em todas as imagens.' },
  ];
}

async function open(values, title, canDelete) {
  let worlds = [];
  try { worlds = await api('/api/worlds'); } catch { /* sem mundos */ }
  currentFields = fields(worlds);
  buildForm($('editor-form'), currentFields, values);
  $('editor-title').textContent = title;
  $('btn-delete-character').style.display = canDelete ? '' : 'none';
  $('editor-error').style.display = 'none';
  openModal('modal-editor');
}

export async function newCharacter() {
  editingId = null;
  await open(BLANK, 'Novo personagem', false);
}

export async function editCharacter(id) {
  try {
    const c = await api(`/api/characters/${id}`);
    editingId = id;
    await open({ ...c, tags: (c.tags || []).join(', ') }, `Editar ${c.name}`, true);
  } catch (e) {
    toast(e.message, 'error');
  }
}

export async function saveCharacter() {
  const v = readForm($('editor-form'), currentFields);
  v.tags = v.tags.split(',').map((t) => t.trim()).filter(Boolean);
  v.id = editingId || 'novo';
  const err = $('editor-error');
  try {
    if (editingId) await api(`/api/characters/${editingId}`, { method: 'PUT', body: v });
    else await api('/api/characters', { method: 'POST', body: v });
    closeModal('modal-editor');
    toast('Personagem salvo.', 'success');
    await loadCharacters();
  } catch (e) {
    err.textContent = e.message;
    err.style.display = 'block';
  }
}

export async function deleteCharacter() {
  if (!editingId || !confirm('Apagar este personagem? As conversas já salvas continuam no disco.')) return;
  try {
    await api(`/api/characters/${editingId}`, { method: 'DELETE' });
    closeModal('modal-editor');
    await loadCharacters();
  } catch (e) {
    toast(e.message, 'error');
  }
}

