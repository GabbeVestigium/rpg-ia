// Envio de mensagens, streaming da resposta, regenerar, desfazer, editar.

import { api, streamSSE } from './api.js';
import { state } from './state.js';
import { $, formatText, toast } from './util.js';
import {
  appendLevelUp, appendMessage, characterLabel, clearChoices, dropChoicesLoading, refreshActions,
  removeTypingIndicator, renderChat, renderChoices, scrollToBottom, showTypingIndicator, startEdit,
} from './messages.js';
import { currentLevel, updateCast, updateSidebar } from './sidebar.js';
import { setMood } from './portrait.js';
import { checkStatus } from './screens.js';
import { speak, stopSpeaking } from './tts.js';

function setStreaming(on) {
  state.streaming = on;
  $('send-btn').style.display = on ? 'none' : '';
  $('stop-btn').style.display = on ? '' : 'none';
  $('user-input').disabled = on;
  document.querySelectorAll('.msg-actions button').forEach((b) => { b.disabled = on; });
  if (!on) focusInput();
}

/** Foca a caixa de texto só com mouse: no celular isso abriria o teclado sozinho. */
export function focusInput() {
  if (matchMedia('(hover: hover)').matches) $('user-input').focus();
}

/** Compara com o servidor e redesenha se divergiu (resposta parcial, erro, desconexão). False se não conseguiu. */
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
    return true;
  } catch { return false; /* o próximo envio tenta de novo */ }
}

/**
 * Roda uma resposta em streaming. `path`/`body` escolhem a rota (chat ou regenerar).
 * Devolve o texto gerado.
 */
let lastOffline = false;   // a última resposta falhou porque o servidor nem foi alcançado

async function runReply(path, body) {
  lastOffline = false;
  clearChoices();
  setStreaming(true);
  stopSpeaking();
  showTypingIndicator();
  const controller = new AbortController();
  state.abort = controller;
  const session = state.session;

  let bubble = null;
  let full = '';
  let finish;
  const finished = new Promise((resolve) => { finish = resolve; });

  // A conexão fica aberta um pouco depois do "done" (resumo da memória, inventário), então o chat
  // é liberado no "done" e o resto chega em segundo plano.
  streamSSE(path, body, async (evt) => {
    // Trocou de conversa: o resto deste stream (escolhas, inventário...) não é desta tela.
    if (state.session !== session) { finish(); return; }
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
      // Só acompanha o fim se o jogador não subiu para reler (mede antes do texto crescer).
      const box = $('messages');
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < box.clientHeight;
      bubble.innerHTML = formatText(full);
      if (atBottom) scrollToBottom();
    } else if (evt.type === 'replace') {
      // A resposta entrou em loop: o servidor cortou a repetição e manda o texto certo.
      full = evt.text;
      if (bubble) bubble.innerHTML = formatText(full);
    } else if (evt.type === 'error') {
      toast(evt.message, 'error', 8000);
    } else if (evt.type === 'mood') {
      setMood(evt.mood);
    } else if (evt.type === 'inventory') {
      onInventory(evt.changes);
    } else if (evt.type === 'choices') {
      state.choices = evt.options;
      renderChoices(evt.options);
    } else if (evt.type === 'done') {
      finish();
      if (bubble && state.settings?.auto_choices !== false) renderChoices(null);
    }
  }, controller.signal)
    .catch((e) => {
      if (e.name === 'AbortError') return;
      lastOffline = !!e.offline;
      toast(e.message, 'error', 8000);
      checkStatus();   // o ponto de status mostra na hora se o servidor ou o Ollama caiu
    })
    .finally(() => { finish(); if (state.session === session) dropChoicesLoading(); });

  await finished;
  removeTypingIndicator();
  bubble?.classList.remove('typing-cursor');
  if (state.abort === controller) state.abort = null;
  setStreaming(false);
  return state.session === session ? full.trim() : null;
}

/** Escolhas da resposta que já está na tela (abrir a conversa: a primeira fala também ganha botões). */
export async function loadChoices() {
  const last = state.history[state.history.length - 1];
  if (state.choices.length || state.settings?.auto_choices === false || last?.role !== 'assistant') return;
  const session = state.session;
  renderChoices(null);
  try {
    const res = await api('/api/chat/choices', {
      method: 'POST', body: { session_id: session, character_id: state.character.id },
    });
    // Só mostra se o jogador ainda está na mesma conversa e não respondeu enquanto isso.
    if (session !== state.session || state.streaming || state.history[state.history.length - 1] !== last) return;
    state.choices = res.options || [];
    if (state.choices.length) renderChoices(state.choices);
  } catch { /* sem escolhas: o jogador escreve */ }
  dropChoicesLoading();
}

/** O jogador tocou numa escolha: ela vira a mensagem dele. */
export function pickChoice(text) {
  if (state.streaming) return;
  $('user-input').value = text;
  sendMessage();
}

/** Itens que a história deu ou tirou: avisa e atualiza a lateral. */
async function onInventory(changes) {
  toast(`Inventário: ${changes.join(', ')}`, 'info', 6000);
  try {
    const data = await api(`/api/player/${state.session}`);
    if (data.player) updateSidebar(data.player, state.mode);
  } catch { /* a próxima atualização corrige */ }
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
  if (reply === null) return;   // a conversa mudou no meio da resposta
  const session = state.session;
  if (reply) state.history.push({ role: 'assistant', content: reply });
  const synced = await resync();
  if (session !== state.session) return;   // saiu enquanto sincronizava: não fala na outra tela
  if (!reply && userText && lastOffline && !synced && state.history.at(-1)?.role === 'user') {
    // O pedido nem chegou ao servidor: a mensagem só existe aqui. Tira da tela e devolve à caixa.
    // Se a conexão caiu depois, o servidor pode ter guardado a mensagem: fica na tela até sincronizar.
    state.history.pop();
    renderChat();
    $('user-input').value = userText;
  }
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
  clearChoices();
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

/** Saindo da conversa: corta a resposta que ainda está chegando e a voz. */
export function leaveChat() {
  if (state.streaming) stopStreaming();
  stopSpeaking();
}

export async function undoLast() {
  if (state.streaming) return;
  clearChoices();
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

export function beginEdit(index) { clearChoices(); startEdit(index); }

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

