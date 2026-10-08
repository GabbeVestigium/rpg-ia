// Renderização das mensagens do chat.

import { state } from './state.js';
import { $, escapeHtml, formatText } from './util.js';

export function scrollToBottom() {
  const box = $('messages');
  box.scrollTop = box.scrollHeight;
}

export function clearMessages() { $('messages').innerHTML = ''; }

export function appendScenario(scenario) {
  const div = document.createElement('div');
  div.className = 'scenario-card';
  div.innerHTML = `<div class="scenario-label">📖 Cenário</div><div class="scenario-text">${formatText(scenario)}</div>`;
  $('messages').appendChild(div);
}

export function characterLabel() { return state.character?.name || 'Personagem'; }

/** Cria o balão de uma mensagem. `index` é a posição no histórico (para editar/regenerar). */
export function appendMessage(role, content, index) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (index !== undefined) div.dataset.index = String(index);
  const label = role === 'user' ? 'Você' : characterLabel();
  div.innerHTML = `<div class="message-header">${escapeHtml(label)}</div><div class="bubble">${formatText(content)}</div>`;
  $('messages').appendChild(div);
  scrollToBottom();
  return div;
}

export function appendSystemNote(text) {
  const div = document.createElement('div');
  div.className = 'message assistant system-note';
  div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  $('messages').appendChild(div);
  scrollToBottom();
}

export function appendSceneImage(image) {
  const div = document.createElement('div');
  div.className = 'scene-card';
  const img = document.createElement('img');
  img.src = image.url;
  img.alt = 'Cena';
  img.loading = 'lazy';
  img.addEventListener('click', () => window.open(image.url, '_blank'));
  div.appendChild(img);
  $('messages').appendChild(div);
  scrollToBottom();
  return div;
}

export function appendLevelUp(level) {
  const div = document.createElement('div');
  div.className = 'levelup-card';
  div.innerHTML = `<div class="levelup-title">⬆️ LEVEL UP!</div><div class="levelup-sub">Você alcançou o Nível ${Number(level)}!</div>`;
  $('messages').appendChild(div);
  scrollToBottom();
}

export function showTypingIndicator() {
  const div = document.createElement('div');
  div.className = 'message assistant typing-indicator';
  div.id = 'typing-indicator';
  div.innerHTML = `<div class="message-header">${escapeHtml(characterLabel())}</div><div class="bubble"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
  $('messages').appendChild(div);
  scrollToBottom();
}

export function removeTypingIndicator() { $('typing-indicator')?.remove(); }

/** Redesenha o chat inteiro a partir do estado (abertura, retomada, após desfazer/editar). */
export function renderChat() {
  clearMessages();
  const scenario = state.character?.scenario;
  if (scenario) appendScenario(scenario);
  state.history.forEach((m, i) => {
    appendMessage(m.role, m.content, i);
    state.images.filter((img) => img.at === i + 1).forEach(appendSceneImage);
  });
  refreshActions();
}

/** Recoloca as ações (ouvir, editar, regenerar, desfazer) conforme o estado atual. */
export function refreshActions() {
  document.querySelectorAll('.msg-actions').forEach((el) => el.remove());
  const lastAssistant = state.history.length - 1;
  document.querySelectorAll('#messages .message[data-index]').forEach((div) => {
    const index = Number(div.dataset.index);
    const msg = state.history[index];
    if (!msg || div.classList.contains('editing')) return;

    const bar = document.createElement('div');
    bar.className = 'msg-actions';
    const add = (action, label, title) => {
      const b = document.createElement('button');
      b.className = 'msg-action';
      b.dataset.action = action;
      b.dataset.index = String(index);
      b.title = title;
      b.textContent = label;
      bar.appendChild(b);
    };
    if (msg.role === 'assistant') add('speak', '🔊', 'Ouvir');
    add('edit-message', '✏️', 'Editar');
    if (index === lastAssistant && msg.role === 'assistant' && index > 0) {
      add('regenerate', '🔄', 'Gerar outra resposta');
      add('undo', '↩', 'Desfazer esta troca');
    }
    div.appendChild(bar);
  });
}

export function startEdit(index) {
  const div = document.querySelector(`#messages .message[data-index="${index}"]`);
  if (!div) return;
  div.classList.add('editing');
  div.querySelector('.msg-actions')?.remove();
  const bubble = div.querySelector('.bubble');
  const area = document.createElement('textarea');
  area.className = 'edit-area';
  area.value = state.history[index].content;
  area.rows = Math.min(14, Math.max(3, area.value.split('\n').length + 1));
  bubble.replaceWith(area);
  const bar = document.createElement('div');
  bar.className = 'msg-actions editing-actions';
  bar.innerHTML = `<button class="msg-action" data-action="save-edit" data-index="${index}">💾 Salvar</button>
    <button class="msg-action" data-action="cancel-edit">Cancelar</button>`;
  div.appendChild(bar);
  area.focus();
}
