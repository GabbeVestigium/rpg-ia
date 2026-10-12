// Retrato do personagem e geração de cenas (Stable Diffusion).

import { api } from './api.js';
import { state } from './state.js';
import { $, toast } from './util.js';
import { appendSceneImage } from './messages.js';

const SD_HINT = 'Imagens precisam do Stable Diffusion (Automatic1111) rodando com --api. É opcional: veja INSTALL_SD.md.';

export async function refreshSdStatus() {
  try {
    state.sdAvailable = (await api('/api/sd/status')).available;
  } catch {
    state.sdAvailable = false;
  }
  // Sem SD os botões de imagem ficam apagados, com a dica no lugar do erro.
  Object.entries({ 'btn-scene': 'Gerar imagem da cena atual', 'btn-generate-portrait': '' }).forEach(([id, title]) => {
    $(id).classList.toggle('sd-off', !state.sdAvailable);
    $(id).title = state.sdAvailable ? title : SD_HINT;
  });
  return state.sdAvailable;
}

/** Confere o SD na hora do clique; offline, explica em vez de dar erro. */
async function sdReady() {
  if (await refreshSdStatus()) return true;
  toast(SD_HINT, 'info', 8000);
  return false;
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

  setBusy(false);   // geração de outra conversa não deixa a tela travada
  state.portraitUrl = null;   // não herda o retrato do personagem anterior se a consulta falhar
  state.expressions = [];
  try {
    const data = await api(`/api/sd/check-portrait/${charId}`);
    state.expressions = data.expressions || [];
    state.allExpressions = data.all_expressions || [];
    state.portraitUrl = data.image_path;
    if (data.exists) {
      img.onload = () => {
        img.style.display = 'block';
        placeholder.style.display = 'none';
        btn.style.display = 'none';
      };
      img.onerror = () => showPlaceholder(false);
      img.src = `${data.image_path}?t=${Date.now()}`;
      await refreshSdStatus();
    } else {
      await refreshSdStatus();
      showPlaceholder(true);   // offline, o botão aparece apagado com a dica
    }
  } catch {
    showPlaceholder(false);
  }
  renderExpressionChips();
}

// ─── EXPRESSÕES ───────────────────────────────────────────────────────────────

const EXPRESSION_LABELS = {
  neutral: ['😐', 'normal'], happy: ['😊', 'feliz'], angry: ['😠', 'brava'],
  sad: ['😢', 'triste'], surprised: ['😮', 'surpresa'], shy: ['😳', 'envergonhada'],
};

function expressionUrl(expression) {
  const base = state.portraitUrl;                      // /portraits/<id>.png
  return expression === 'neutral' ? base : base.replace(/\.png$/, `__${expression}.png`);
}

/** Mostra uma expressão no retrato; sem a imagem dela, fica o retrato normal. */
export function showExpression(expression) {
  const img = $('char-portrait-img');
  if (!state.portraitUrl || img.style.display === 'none') return;
  const wanted = expression === 'neutral' || state.expressions.includes(expression) ? expression : 'neutral';
  img.src = `${expressionUrl(wanted)}?t=${Date.now()}`;
  document.querySelectorAll('#char-expressions .expr-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.expression === wanted);
  });
}

/** Chamada a cada resposta: o clima do texto escolhe a expressão (só personagens com um rosto). */
export function setMood(mood) {
  if (state.character?.group) return;
  showExpression(mood);
}

function renderExpressionChips() {
  const box = $('char-expressions');
  if (state.character?.group || !state.portraitUrl) { box.style.display = 'none'; box.innerHTML = ''; return; }

  const missing = state.allExpressions.filter((e) => !state.expressions.includes(e));
  const chips = ['neutral', ...state.expressions].map((e) => {
    const [emoji, label] = EXPRESSION_LABELS[e] || ['🙂', e];
    return `<button class="expr-btn" data-action="show-expression" data-expression="${e}" title="${label}">
      <span class="expr-emoji">${emoji}</span></button>`;
  }).join('');
  const more = missing.length && state.sdAvailable
    ? `<button class="expr-btn expr-add" data-action="generate-expressions" title="Gerar as ${missing.length} expressões que faltam">✨</button>` : '';
  box.innerHTML = chips + more;
  box.style.display = 'flex';
}

/** Gera as expressões que faltam, uma por vez (cada uma leva de 30 a 90s na GTX 1660). */
export async function generateExpressions() {
  if (!state.character || state.character.group) return;
  const missing = state.allExpressions.filter((e) => !state.expressions.includes(e));
  if (!missing.length || !(await sdReady())) return;
  const id = state.character.id;
  const session = state.session;
  const stale = () => state.session !== session;
  try {
    for (const [i, expression] of missing.entries()) {
      if (stale()) return;
      setBusy(true, `Expressão ${i + 1} de ${missing.length}: ${EXPRESSION_LABELS[expression]?.[1] || expression}...`);
      await api('/api/sd/generate-expression', {
        method: 'POST', body: { character_id: id, expression },
      });
      if (stale()) return;
      state.expressions.push(expression);
      renderExpressionChips();
    }
    toast('Expressões prontas. O retrato muda conforme o clima da conversa.', 'success');
  } catch (e) {
    if (!stale()) toast(e.message, 'error', 8000);
  } finally {
    if (!stale()) { setBusy(false); renderExpressionChips(); }
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
  if (!state.character || !(await sdReady())) return;
  const id = state.character.id;
  const session = state.session;
  const stale = () => state.session !== session;
  $('btn-generate-portrait').style.display = 'none';
  setBusy(true, 'Gerando retrato...');
  try {
    await api('/api/sd/generate-portrait', { method: 'POST', body: { character_id: id } });
    if (!stale()) await loadPortrait(id);
  } catch (e) {
    if (!stale()) {
      toast(e.message, 'error', 8000);
      $('btn-generate-portrait').style.display = 'flex';
    }
  } finally {
    if (!stale()) setBusy(false);
  }
}

export async function generateScene() {
  if (!state.session || state.streaming || !(await sdReady())) return;
  const session = state.session;
  setBusy(true, 'Gerando cena...');
  try {
    const image = await api('/api/scene/generate', { method: 'POST', body: { session_id: session } });
    if (session !== state.session) return;   // a cena fica salva na conversa de origem
    state.images.push(image);
    appendSceneImage(image);
  } catch (e) {
    if (session === state.session) toast(e.message, 'error', 8000);
  } finally {
    if (session === state.session) setBusy(false);
  }
}
