// Ponto de entrada: liga os eventos da página (delegação por data-action) e inicia o app.

import { exportChat, restoreBackup } from './backup.js';
import * as chat from './chat.js';
import { deleteCharacter, editCharacter, newCharacter, saveCharacter } from './editor.js';
import { initLayout } from './layout.js';
import { addLore, deleteLore, openLore, saveLore } from './lorebook.js';
import { openMemory, saveMemory } from './memory.js';
import { loadProfile, openProfile, saveProfile } from './profile.js';
import { generateExpressions, generatePortrait, generateScene, showExpression } from './portrait.js';
import * as screens from './screens.js';
import { openSettings, saveSettings, toggleAutoplay, updateAutoplayButton } from './settings.js';
import { state } from './state.js';
import { refreshSettings } from './tts.js';
import { $, closeModal, showScreen, toast } from './util.js';

const actions = {
  // seleção
  'open-mode': (el) => screens.openModeModal(el.dataset.id),
  'edit-character': (el, e) => { e.stopPropagation(); editCharacter(el.dataset.id); },
  'new-character': () => newCharacter(),
  'continue-session': (el) => screens.continueSession(el.dataset.id),
  'delete-session': (el, e) => { e.stopPropagation(); screens.deleteSession(el.dataset.id); },
  'select-mode': (el) => screens.selectMode(el.dataset.mode),
  'close-mode': () => closeModal('modal-mode'),
  // criação do jogador
  'show-select': () => showScreen('screen-select'),
  'select-race': (el) => screens.selectRace(el.dataset.id),
  'select-class': (el) => screens.selectClass(el.dataset.id),
  'attr-change': (el) => screens.changeAttr(el.dataset.attr, Number(el.dataset.delta)),
  'confirm-create': () => screens.confirmCreatePlayer(),
  // chat
  'go-back': () => screens.backToSelect(),
  'new-chat': () => {
    if (confirm('Iniciar nova conversa com este personagem?')) screens.openModeModal(state.character.id);
  },
  'send': () => chat.sendMessage(),
  'stop': () => chat.stopStreaming(),
  'regenerate': () => chat.regenerate(),
  'swipe-prev': () => chat.swipeVersion(-1),
  'swipe-next': () => chat.swipeVersion(1),
  'undo': () => chat.undoLast(),
  'speak': (el) => chat.speakMessage(Number(el.dataset.index)),
  'edit-message': (el) => chat.beginEdit(Number(el.dataset.index)),
  'save-edit': (el) => chat.saveEdit(Number(el.dataset.index)),
  'cancel-edit': () => chat.cancelEdit(),
  'manual-roll': () => chat.manualRoll(),
  'generate-portrait': () => generatePortrait(),
  'generate-scene': () => generateScene(),
  'generate-expressions': () => generateExpressions(),
  'show-expression': (el) => showExpression(el.dataset.expression),
  'export-chat': () => exportChat(),
  'open-lore': () => openLore(),
  'add-lore': () => addLore(),
  'delete-lore': (el) => deleteLore(Number(el.dataset.row)),
  'save-lore': () => saveLore(),
  'close-lore': () => closeModal('modal-lore'),
  'open-memory': () => openMemory(),
  'save-memory': () => saveMemory(),
  'close-memory': () => closeModal('modal-memory'),
  'toggle-autoplay': () => toggleAutoplay(),
  // configurações e editor
  'open-profile': () => openProfile(),
  'save-profile': () => saveProfile(),
  'close-profile': () => closeModal('modal-profile'),
  'open-settings': () => openSettings(),
  'save-settings': () => saveSettings(),
  'close-settings': () => closeModal('modal-settings'),
  'save-character': () => saveCharacter(),
  'delete-character': () => deleteCharacter(),
  'close-editor': () => closeModal('modal-editor'),
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el || el.disabled) return;
  const handler = actions[el.dataset.action];
  if (handler) handler(el, e);
});

const input = $('user-input');
input.addEventListener('keydown', chat.handleInputKey);
input.addEventListener('input', () => chat.autoResize(input));

$('backup-file').addEventListener('change', (e) => {
  restoreBackup(e.target.files[0]);
  e.target.value = '';
});

// Fecha modais com Esc.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  ['modal-settings', 'modal-editor', 'modal-memory', 'modal-mode', 'modal-lore', 'modal-profile'].forEach(closeModal);
});

async function init() {
  initLayout();
  try {
    state.settings = await refreshSettings();
    updateAutoplayButton();
  } catch { /* usa os padrões do servidor quando voltar */ }
  // Algumas engines de voz do navegador só listam as vozes depois de carregar.
  if ('speechSynthesis' in window) window.speechSynthesis.getVoices();
  await Promise.all([screens.checkStatus(), screens.loadCharacters(), screens.loadRpgOptions(), loadProfile()]);
  await screens.loadSavedSessions();
}

init().catch((e) => toast(`Erro ao iniciar: ${e.message}`, 'error'));
