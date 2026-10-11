// Telas: seleção de personagem, escolha de modo, criação do jogador, retomar sessão.

import { api } from './api.js';
import { state } from './state.js';
import { $, avatarHtml, characterHue, closeModal, escapeHtml, openModal, showScreen, toast } from './util.js';
import { renderChat } from './messages.js';
import { loadChoices } from './chat.js';
import { ATTR_LABELS, setupDiceTable, setupSidebar } from './sidebar.js';
import { loadPortrait } from './portrait.js';
import { stopSpeaking } from './tts.js';

let selectedRace = null;
let selectedClass = null;
let attributes = { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 };
let pointsLeft = 12;

// ─── SELEÇÃO ──────────────────────────────────────────────────────────────────

export async function checkStatus() {
  const dot = $('status-dot');
  const txt = $('status-text');
  dot.className = 'dot loading';
  try {
    const d = await api('/api/status');
    if (d.status === 'online') {
      dot.className = 'dot online';
      txt.textContent = `Ollama online · modelo: ${d.active_model}`;
    } else {
      dot.className = 'dot offline';
      txt.textContent = "Ollama offline. Rode 'ollama serve'";
    }
  } catch {
    dot.className = 'dot offline';
    txt.textContent = 'Servidor não encontrado';
  }
}

export async function loadRpgOptions() {
  try { state.rpgOptions = await api('/api/rpg/options'); } catch { /* usa vazio */ }
}

export async function loadCharacters() {
  const grid = $('character-grid');
  try {
    const chars = await api('/api/characters');
    if (!chars.length) {
      grid.innerHTML = '<p class="loading-spinner">Nenhum personagem. Crie o primeiro em "Novo personagem".</p>';
      return;
    }
    // Capa no estilo galeria: retrato quando existe, senão o emoji grande sobre a cor do personagem.
    grid.innerHTML = chars.map((c) => `
      <div class="char-card${c.has_portrait ? ' has-portrait' : ''}" data-action="open-mode" data-id="${escapeHtml(c.id)}"
           data-tags="${escapeHtml((c.tags || []).join('|'))}" style="--hue:${characterHue(c.id)}">
        <button class="char-card-edit" data-action="edit-character" data-id="${escapeHtml(c.id)}" title="Editar">✏️</button>
        <div class="char-card-cover">
          ${c.has_portrait
            ? `<img class="char-card-img" src="/portraits/${encodeURIComponent(c.id)}.png" alt="" loading="lazy" />`
            : `<span class="char-card-avatar">${escapeHtml(c.avatar_emoji)}</span>`}
        </div>
        <div class="char-card-body">
          <div class="char-card-world">${escapeHtml(c.world_id)}</div>
          <div class="char-card-name">${escapeHtml(c.name)} <span class="char-card-age">${Number(c.age)}</span></div>
          <div class="char-card-desc">${escapeHtml(c.summary)}</div>
          <div class="char-card-tags">${(c.tags || []).slice(0, 3).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
        </div>
      </div>`).join('');
    state.characterList = chars;
    renderTagFilter(chars);
  } catch (e) {
    grid.innerHTML = `<p class="loading-spinner">Erro: ${escapeHtml(e.message)}</p>`;
  }
}

/** Filtro por gênero (as tags mais comuns), como as abas de categoria dos apps de história. */
function renderTagFilter(chars) {
  const count = {};
  chars.forEach((c) => (c.tags || []).forEach((t) => { count[t] = (count[t] || 0) + 1; }));
  const tags = Object.keys(count).sort((a, b) => count[b] - count[a] || a.localeCompare(b)).slice(0, 12);
  const active = state.tagFilter && tags.includes(state.tagFilter) ? state.tagFilter : '';
  $('tag-filter').innerHTML = ['', ...tags].map((t) => `<button class="tag-chip${t === active ? ' active' : ''}"
    data-action="filter-tag" data-tag="${escapeHtml(t)}">${t ? escapeHtml(t) : 'Todos'}</button>`).join('');
  filterByTag(active);
}

export function filterByTag(tag) {
  state.tagFilter = tag;
  document.querySelectorAll('#tag-filter .tag-chip').forEach((b) => b.classList.toggle('active', b.dataset.tag === tag));
  document.querySelectorAll('#character-grid .char-card').forEach((card) => {
    card.style.display = !tag || card.dataset.tags.split('|').includes(tag) ? '' : 'none';
  });
}

export async function loadSavedSessions() {
  try {
    const sessions = await api('/api/sessions');
    const section = $('saved-sessions-section');
    if (!sessions.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    const modeIcon = { narrative: '📖', medium: '⚖️', full: '🎲' };
    $('saved-sessions-list').innerHTML = sessions.map((s) => {
      const player = s.player_name ? ` · ${escapeHtml(s.player_name)} Nv${Number(s.player_level)}` : '';
      const c = (state.characterList || []).find((x) => x.id === s.character_id) || {};
      return `<div class="session-card" data-action="continue-session" data-id="${escapeHtml(s.session_id)}"
                   style="--hue:${characterHue(s.character_id)}">
        <span class="session-card-avatar">${c.id ? avatarHtml(c) : escapeHtml(s.character_emoji)}</span>
        <div class="session-card-info">
          <span class="session-card-name">${escapeHtml(s.character_name)}</span>
          <span class="session-card-meta">${modeIcon[s.mode] || '📖'}${player} · ${Number(s.message_count)} msgs</span>
        </div>
        <button class="session-card-del" data-action="delete-session" data-id="${escapeHtml(s.session_id)}" title="Apagar">🗑️</button>
      </div>`;
    }).join('');
  } catch { /* lista fica como estava */ }
}

export function backToSelect() {
  stopSpeaking();
  showScreen('screen-select');
  loadCharacters();
  loadSavedSessions();
}

// ─── MODO ─────────────────────────────────────────────────────────────────────

export function openModeModal(charId) {
  const c = (state.characterList || []).find((x) => x.id === charId);
  if (!c) return;
  state.character = { id: c.id, name: c.name, avatar_emoji: c.avatar_emoji, world_id: c.world_id, group: c.group };
  $('modal-char-avatar').innerHTML = avatarHtml(c);
  $('modal-char-name').textContent = c.name;
  $('modal-char-world').textContent = c.world_id || '';
  $('modal-char-summary').textContent = c.summary || '';
  $('modal-char-scenario').innerHTML = c.scenario ? `<strong>Cenário</strong> ${escapeHtml(c.scenario)}` : '';
  $('modal-char-tags').innerHTML = (c.tags || []).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join('');
  $('modal-mode').style.setProperty('--hue', characterHue(c.id));
  $('prompt-warning').style.display = 'none';
  openModal('modal-mode');
  warnIfHeavy(c.id);
}

/** Avisa quando a ficha fixa do personagem deixa pouco contexto para a conversa. */
async function warnIfHeavy(id) {
  try {
    const p = await api(`/api/characters/${id}/prompt-size`);
    if (p.history_left < 1200) {
      const box = $('prompt-warning');
      box.textContent = `Este personagem ocupa cerca de ${p.tokens} dos ${p.num_ctx} tokens de contexto, e sobra pouco para a conversa. `
        + 'Em ⚙️ Configurações, aumentar o contexto (6144 costuma caber numa placa de 6 GB) deixa a memória mais longa.';
      box.style.display = 'block';
    }
  } catch { /* o aviso é opcional */ }
}

export async function selectMode(mode) {
  state.mode = mode;
  closeModal('modal-mode');
  if (mode === 'narrative') await startNewChat(state.character.id, 'narrative');
  else showCreateScreen(mode);
}

// ─── CRIAÇÃO DO JOGADOR ───────────────────────────────────────────────────────

function showCreateScreen(mode) {
  $('create-mode-badge').textContent = mode === 'full' ? 'Completo' : 'Médio';
  $('attributes-section').style.display = mode === 'full' ? 'block' : 'none';

  $('race-grid').innerHTML = state.rpgOptions.races.map((r) =>
    `<button class="option-btn" data-action="select-race" data-id="${escapeHtml(r.id)}">${escapeHtml(r.name)}</button>`).join('');
  $('class-grid').innerHTML = state.rpgOptions.classes.map((c) =>
    `<button class="option-btn" data-action="select-class" data-id="${escapeHtml(c.id)}">${escapeHtml(c.name)}</button>`).join('');

  const icons = { STR: '💪', DEX: '🏃', CON: '❤️', INT: '🧠', WIS: '🔮', CHA: '✨' };
  const names = { STR: 'Força', DEX: 'Destreza', CON: 'Constituição', INT: 'Inteligência', WIS: 'Sabedoria', CHA: 'Carisma' };
  $('attr-grid').innerHTML = Object.keys(attributes).map((k) => `
    <div class="attr-item">
      <span class="attr-icon">${icons[k]}</span><span class="attr-label">${names[k]}</span>
      <div class="attr-controls">
        <button data-action="attr-change" data-attr="${k}" data-delta="-1">−</button>
        <span id="attr-${k}" class="attr-value">10</span>
        <button data-action="attr-change" data-attr="${k}" data-delta="1">+</button>
      </div>
      <span id="mod-${k}" class="attr-mod">+0</span>
    </div>`).join('');

  selectedRace = null;
  selectedClass = null;
  attributes = { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 };
  pointsLeft = 12;
  $('race-detail').style.display = 'none';
  $('class-detail').style.display = 'none';
  if (mode === 'full') updateAttrUI();
  // Já vem preenchido com o seu perfil (dá para mudar só para esta história).
  const prof = state.profile || {};
  $('input-player-name').value = prof.name || '';
  $('input-player-age').value = prof.age >= 18 ? String(prof.age) : '26';
  $('input-appearance').value = prof.appearance || '';
  showScreen('screen-create');
}

function pill(cls, text) { return `<span class="stat-pill ${cls}">${text}</span>`; }

export function selectRace(id) {
  selectedRace = id;
  document.querySelectorAll('#race-grid .option-btn').forEach((b) => b.classList.toggle('selected', b.dataset.id === id));
  const race = state.rpgOptions.races.find((r) => r.id === id);
  const detail = $('race-detail');
  if (!race) { detail.style.display = 'none'; return; }
  const bonus = Object.entries(race.bonus || {}).map(([k, v]) => pill('bonus', `+${v} ${ATTR_LABELS[k] || k}`)).join('');
  const penalty = Object.entries(race.penalty || {}).map(([k, v]) => pill('penalty', `${v} ${ATTR_LABELS[k] || k}`)).join('');
  detail.style.display = 'block';
  detail.innerHTML = `<div class="detail-title">${escapeHtml(race.name)}</div>
    <div class="detail-desc">${escapeHtml(race.trait)}</div>
    <div class="detail-stats">${bonus}${penalty}${!bonus && !penalty ? pill('info', 'Sem modificadores fixos') : ''}</div>`;
}

export function selectClass(id) {
  selectedClass = id;
  document.querySelectorAll('#class-grid .option-btn').forEach((b) => b.classList.toggle('selected', b.dataset.id === id));
  const cls = state.rpgOptions.classes.find((c) => c.id === id);
  const detail = $('class-detail');
  if (!cls) { detail.style.display = 'none'; return; }
  const primary = cls.primary.map((a) => ATTR_LABELS[a] || a).join(', ');
  const saves = cls.saves.map((a) => ATTR_LABELS[a] || a).join(', ');
  detail.style.display = 'block';
  detail.innerHTML = `<div class="detail-title">${escapeHtml(cls.name)}</div>
    <div class="detail-desc">${escapeHtml(cls.desc)}</div>
    <div class="detail-stats">${pill('info', `❤️ HP base: ${cls.hp_base}`)}${pill('info', `🎲 d${cls.hit_die}`)}
    ${pill('bonus', `⭐ ${primary}`)}${pill('info', `🛡️ Saves: ${saves}`)}</div>`;
}

export function changeAttr(attr, delta) {
  const value = attributes[attr] + delta;
  if (value < 8 || value > 18) return;
  if (delta > 0 && pointsLeft <= 0) return;
  attributes[attr] = value;
  pointsLeft -= delta;
  updateAttrUI();
}

function updateAttrUI() {
  $('points-left').textContent = pointsLeft;
  for (const [attr, val] of Object.entries(attributes)) {
    const mod = Math.floor((val - 10) / 2);
    $(`attr-${attr}`).textContent = val;
    $(`mod-${attr}`).textContent = mod >= 0 ? `+${mod}` : `${mod}`;
  }
}

export async function confirmCreatePlayer() {
  const name = $('input-player-name').value.trim();
  const age = parseInt($('input-player-age').value, 10);
  const appearance = $('input-appearance').value.trim();

  if (!name) return toast('Digite um nome para o personagem.', 'error');
  if (!selectedRace) return toast('Escolha uma raça.', 'error');
  if (!selectedClass) return toast('Escolha uma classe.', 'error');
  if (!(age >= 18)) return toast('O personagem precisa ter 18 anos ou mais.', 'error');

  const btn = $('btn-confirm-create');
  btn.disabled = true;
  btn.textContent = 'Criando...';
  try {
    const sess = await api('/api/session/new', {
      method: 'POST', body: { character_id: state.character.id, game_mode: state.mode },
    });
    state.session = sess.session_id;
    // Valida o jogador antes de abrir o chat; se falhar, a sessão vazia é apagada.
    let playerData;
    try {
      playerData = await api('/api/player/create', {
        method: 'POST',
        body: {
          session_id: state.session, name, race: selectedRace, char_class: selectedClass,
          mode: state.mode, age, appearance,
          attributes: state.mode === 'full' ? attributes : null,
        },
      });
    } catch (e) {
      await api(`/api/session/${state.session}`, { method: 'DELETE' }).catch(() => {});
      throw e;
    }
    state.character = { ...state.character, ...sess.character };
    state.history = [{ role: 'assistant', content: sess.character.first_message }];
    state.images = [];
    state.cast = sess.cast || [];
    state.swipe = { index: 0, count: 0 };
    state.choices = [];
    openChatScreen(playerData.player);
  } catch (e) {
    toast(e.message, 'error', 7000);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Entrar na história';
  }
}

// ─── SESSÕES ──────────────────────────────────────────────────────────────────

export async function startNewChat(characterId, mode) {
  try {
    const data = await api('/api/session/new', { method: 'POST', body: { character_id: characterId, game_mode: mode } });
    state.session = data.session_id;
    state.character = { ...state.character, ...data.character };
    state.history = [{ role: 'assistant', content: data.character.first_message }];
    state.images = [];
    state.cast = data.cast || [];
    state.swipe = { index: 0, count: 0 };
    state.choices = [];
    openChatScreen(null);
  } catch (e) {
    toast(e.message, 'error');
  }
}

export async function continueSession(sessionId) {
  try {
    const data = await api(`/api/session/${sessionId}`);
    state.session = sessionId;
    state.mode = data.game_mode || 'narrative';
    state.character = {
      id: data.character_id, name: data.character_name, avatar_emoji: data.avatar_emoji,
      world_id: data.world_id, scenario: data.scenario, group: data.group,
    };
    state.history = data.history;
    state.images = data.images || [];
    state.cast = data.cast || [];
    state.swipe = data.swipe || { index: 0, count: 0 };
    state.choices = data.choices || [];
    openChatScreen(data.rpg_state?.player || null);
  } catch (e) {
    toast(e.message, 'error');
  }
}

export async function deleteSession(sessionId) {
  if (!confirm('Apagar esta conversa?')) return;
  try {
    await api(`/api/session/${sessionId}`, { method: 'DELETE' });
  } catch (e) {
    toast(e.message, 'error');
  }
  await loadSavedSessions();
}

function openChatScreen(player) {
  const c = state.character;
  showScreen('screen-chat');
  $('portrait-emoji').textContent = c.avatar_emoji || '👤';
  $('panel-char-name').textContent = c.name || '?';
  $('panel-char-world').textContent = c.world_id || '';
  $('topbar-char-name').textContent = c.name || '?';
  const listed = (state.characterList || []).find((x) => x.id === c.id) || c;
  $('topbar-avatar').innerHTML = avatarHtml(listed);
  $('screen-chat').style.setProperty('--hue', characterHue(c.id));
  $('topbar-session').textContent = `sessão: ${state.session}`;
  const labels = { narrative: '📖 Narrativo', medium: '⚖️ Médio', full: '🎲 Completo' };
  $('panel-mode-badge').textContent = labels[state.mode] || state.mode;

  loadPortrait(c.id);
  setupDiceTable(state.mode);
  setupSidebar(state.mode, player, state.cast);
  renderChat();
  loadChoices();
  $('user-input').focus();
}
