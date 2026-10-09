// Envio de mensagens, streaming da resposta, regenerar, desfazer, editar.

import { api, streamSSE } from './api.js';
import { state } from './state.js';
import { $, formatText, toast } from './util.js';
import {
  appendLevelUp, appendMessage, characterLabel, refreshActions, removeTypingIndicator,
  renderChat, scrollToBottom, showTypingIndicator, startEdit,
} from './messages.js';
import { currentLevel, updateCast, updateSidebar } from './sidebar.js';
import { speak, stopSpeaking } from './tts.js';

function setStreaming(on) {
  state.streaming = on;
  $('send-btn').style.display = on ? 'none' : '';
  $('stop-btn').style.display = on ? '' : 'none';
  $('user-input').disabled = on;
  document.querySelectorAll('.msg-actions button').forEach((b) => { b.disabled = on; });
  if (!on) $('user-input').focus();
}

/** Compara com o servidor e redesenha se divergiu (resposta parcial, erro, desconexão). */
async function resync() {
  try {
    const data = await api(`/api/session/${state.session}`);
    state.swipe = data.swipe || { index: 0, count: 0 };
    const same = data.history.length === state.history.length
      && data.history.every((m, i) => m.content === state.history[i].content);
    if (!same) {
      state.history = data.history;
      state.images = data.images || [];
      renderChat();
    }
    if (state.mode !== 'narrative' && data.cast?.length) {
      updateCast(data.cast, state.cast);
      state.cast = data.cast;
    }
    if (state.mode !== 'narrative' && data.rpg_state?.player) {
      const prev = currentLevel();
      if (data.rpg_state.player.level > prev) appendLevelUp(data.rpg_state.player.level);
      updateSidebar(data.rpg_state.player, state.mode);
    }
  } catch { /* o próximo envio tenta de novo */ }
}

/**
 * Roda uma resposta em streaming. `path`/`body` escolhem a rota (chat ou regenerar).
 * Devolve o texto gerado.
 */
async function runReply(path, body) {
  setStreaming(true);
  stopSpeaking();
  showTypingIndicator();
  const controller = new AbortController();
  state.abort = controller;

  let bubble = null;
  let full = '';

  try {
    await streamSSE(path, body, async (evt) => {
      if (evt.type === 'roll') {
        removeTypingIndicator();
        await new Promise((resolve) => window.showDiceRoll(evt.result, resolve));
        showTypingIndicator();
      } else if (evt.type === 'token') {
        if (!bubble) {
          removeTypingIndicator();
          const div = appendMessage('assistant', '', state.history.length);
          bubble = div.querySelector('.bubble');
          bubble.classList.add('typing-cursor');
        }
        full += evt.t;
        bubble.innerHTML = formatText(full);
        scrollToBottom();
      } else if (evt.type === 'error') {
        toast(evt.message, 'error', 8000);
      }
    }, controller.signal);
  } catch (e) {
    if (e.name !== 'AbortError') toast(e.message, 'error', 8000);
  } finally {
    removeTypingIndicator();
    bubble?.classList.remove('typing-cursor');
    state.abort = null;
    setStreaming(false);
  }
  return full.trim();
}

export async function sendMessage() {
  if (state.streaming) return;
  const input = $('user-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';

  state.history.push({ role: 'user', content: text });
  appendMessage('user', text, state.history.length - 1);

  const reply = await runReply('/api/chat', {
    session_id: state.session, character_id: state.character.id, message: text,
  });
  await finishExchange(reply, text);
}

export async function regenerate() {
  if (state.streaming) return;
  const last = state.history[state.history.length - 1];
  if (!last || last.role !== 'assistant') return;
  state.history.pop();
  document.querySelector(`#messages .message[data-index="${state.history.length}"]`)?.remove();
  const reply = await runReply('/api/chat/regenerate', {
    session_id: state.session, character_id: state.character.id,
  });
  await finishExchange(reply, null);
}

async function finishExchange(reply, userText) {
  if (reply) state.history.push({ role: 'assistant', content: reply });
  await resync();
  refreshActions();
  if (!reply && userText && !state.history.some((m) => m.role === 'user' && m.content.startsWith(userText))) {
    // Nada foi gerado e o servidor descartou a mensagem: devolve o texto à caixa.
    $('user-input').value = userText;
  }
  if (reply && state.settings?.tts_auto_play) speak(reply);
}

/** Troca a última resposta por outra versão guardada (delta -1 ou +1). */
export async function swipeVersion(delta) {
  if (state.streaming) return;
  try {
    const res = await api('/api/chat/swipe', { method: 'POST', body: { session_id: state.session, delta } });
    state.history[state.history.length - 1].content = res.content;
    state.swipe = { index: res.index, count: res.count };
    renderChat();
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function stopStreaming() { state.abort?.abort(); }

export async function undoLast() {
  if (state.streaming) return;
  try {
    const { user_text } = await api('/api/chat/undo', {
      method: 'POST', body: { session_id: state.session, character_id: state.character.id },
    });
    await resync();
    $('user-input').value = user_text;
    $('user-input').focus();
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function beginEdit(index) { startEdit(index); }

export async function saveEdit(index) {
  const area = document.querySelector('#messages .edit-area');
  const content = area?.value.trim();
  if (!content) { toast('A mensagem não pode ficar vazia.', 'error'); return; }
  try {
    await api('/api/session/edit', { method: 'POST', body: { session_id: state.session, index, content } });
    state.history[index].content = content;
    renderChat();
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function cancelEdit() { renderChat(); }

export async function manualRoll() {
  if (!state.session) return;
  try {
    const data = await api('/api/roll', { method: 'POST', body: { session_id: state.session } });
    window.showDiceRoll(data, null);
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function speakMessage(index) {
  const msg = state.history[index];
  if (msg) speak(msg.content);
}

export function handleInputKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  } else if (e.key === 'z' && (e.ctrlKey || e.metaKey) && !e.currentTarget.value) {
    e.preventDefault();
    undoLast();
  }
}

export function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
}

