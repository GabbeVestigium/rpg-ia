/**
 * RPG IA — Frontend v3
 * Layout 3 colunas: painel personagem | chat | sidebar RPG
 */

const API = '';

let currentSession   = null;
let currentCharacter = null;
let currentMode      = 'narrative';
let isStreaming      = false;
let rpgOptions       = { races: [], classes: [], modes: [] };

// Estado temporário de criação
let selectedRace  = null;
let selectedClass = null;
let attributes    = { STR:10, DEX:10, CON:10, INT:10, WIS:10, CHA:10 };
let pointsLeft    = 12;

const ATTR_LABELS = { STR:'FOR', DEX:'DES', CON:'CON', INT:'INT', WIS:'SAB', CHA:'CAR' };

// ─── INIT ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await Promise.all([checkStatus(), loadCharacters(), loadRpgOptions()]);
  await loadSavedSessions();
});

async function checkStatus() {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  dot.className = 'dot loading';
  try {
    const r = await fetch(`${API}/api/status`);
    const d = await r.json();
    if (d.status === 'online') {
      dot.className = 'dot online';
      txt.textContent = `Ollama online · ${d.models.join(', ')}`;
    } else {
      dot.className = 'dot offline';
      txt.textContent = "Ollama offline — rode 'ollama serve'";
    }
  } catch {
    dot.className = 'dot offline';
    txt.textContent = 'Ollama não encontrado';
  }
}

async function loadRpgOptions() {
  try {
    const r = await fetch(`${API}/api/rpg/options`);
    rpgOptions = await r.json();
  } catch { /* silencioso */ }
}

async function loadCharacters() {
  const grid = document.getElementById('character-grid');
  try {
    const r     = await fetch(`${API}/api/characters`);
    const chars = await r.json();
    if (!chars.length) { grid.innerHTML = '<p class="loading-spinner">Nenhum personagem encontrado.</p>'; return; }
    grid.innerHTML = chars.map(c => `
      <div class="char-card" onclick="openModeModal('${c.id}','${c.avatar_emoji}','${c.name.replace(/'/g,"\\'")}')">
        <span class="char-card-avatar">${c.avatar_emoji}</span>
        <div class="char-card-name">${c.name}</div>
        <div class="char-card-world">${c.world_id}</div>
        <div class="char-card-desc">${c.description}</div>
        <div class="char-card-scenario"><strong>Cenário:</strong> ${c.scenario}</div>
        <div class="char-card-tags">${(c.tags||[]).map(t=>`<span class="tag">${t}</span>`).join('')}</div>
      </div>`).join('');
  } catch (e) {
    grid.innerHTML = `<p class="loading-spinner">Erro: ${e.message}</p>`;
  }
}

async function loadSavedSessions() {
  try {
    const r        = await fetch(`${API}/api/sessions`);
    const sessions = await r.json();
    const section  = document.getElementById('saved-sessions-section');
    const list     = document.getElementById('saved-sessions-list');
    if (!sessions.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    list.innerHTML = sessions.map(s => {
      const modeLabel  = { narrative:'📖', medium:'⚖️', full:'🎲' }[s.mode] || '📖';
      const charName   = s.character_name  || s.character_id;
      const charEmoji  = s.character_emoji || '👤';
      const playerInfo = s.player_name ? ` · ${s.player_name} Nv${s.player_level}` : '';
      return `<div class="session-card" onclick="continueSession('${s.session_id}','${s.character_id}')">
        <div class="session-card-info">
          <span class="session-card-name">${charEmoji} ${modeLabel} ${charName}${playerInfo}</span>
          <span class="session-card-meta">Sessão ${s.session_id} · ${s.message_count} msgs</span>
        </div>
        <button class="session-card-del" onclick="deleteSession(event,'${s.session_id}')">🗑️</button>
      </div>`;
    }).join('');
  } catch { /* silencioso */ }
}

// ─── MODAL MODO ───────────────────────────────────────────────────────────────

function openModeModal(charId, avatar, name) {
  currentCharacter = { id: charId, avatar_emoji: avatar, name };
  document.getElementById('modal-char-avatar').textContent = avatar;
  document.getElementById('modal-char-name').textContent   = name;
  document.getElementById('modal-mode').style.display      = 'flex';
}

function closeModalMode() {
  document.getElementById('modal-mode').style.display = 'none';
}

async function selectMode(mode) {
  currentMode = mode;
  closeModalMode();
  if (mode === 'narrative') {
    await startNewChat(currentCharacter.id, 'narrative');
  } else {
    showCreateScreen(mode);
  }
}

// ─── TELA CRIAÇÃO ─────────────────────────────────────────────────────────────

function showCreateScreen(mode) {
  document.getElementById('create-mode-badge').textContent = mode === 'full' ? 'Completo' : 'Médio';
  document.getElementById('attributes-section').style.display = mode === 'full' ? 'block' : 'none';
  document.getElementById('appearance-section').style.display = 'block';

  // Raças com bônus/ônus
  const raceGrid = document.getElementById('race-grid');
  raceGrid.innerHTML = rpgOptions.races.map(r =>
    `<button class="option-btn" data-id="${r.id}" onclick="selectRace('${r.id}',this)">${r.name}</button>`
  ).join('');

  // Classes com descrição
  const classGrid = document.getElementById('class-grid');
  classGrid.innerHTML = rpgOptions.classes.map(c =>
    `<button class="option-btn" data-id="${c.id}" onclick="selectClass('${c.id}',this)">${c.name}</button>`
  ).join('');

  // Reset
  selectedRace = null; selectedClass = null;
  document.getElementById('race-detail').style.display  = 'none';
  document.getElementById('class-detail').style.display = 'none';
  attributes = { STR:10, DEX:10, CON:10, INT:10, WIS:10, CHA:10 };
  pointsLeft = 12;
  if (mode === 'full') updateAttrUI();
  document.getElementById('input-player-name').value   = '';
  document.getElementById('input-player-age').value    = '26';
  document.getElementById('input-appearance').value    = '';

  showScreen('screen-create');
}

function selectRace(id, btn) {
  selectedRace = id;
  document.querySelectorAll('#race-grid .option-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');

  // Mostra detalhes da raça
  const race   = rpgOptions.races.find(r => r.id === id);
  const detail = document.getElementById('race-detail');
  if (!race) { detail.style.display = 'none'; return; }

  const bonusPills  = Object.entries(race.bonus  || {}).map(([k,v]) => `<span class="stat-pill bonus">+${v} ${ATTR_LABELS[k]||k}</span>`).join('');
  const penaltyPills = Object.entries(race.penalty || {}).map(([k,v]) => `<span class="stat-pill penalty">${v} ${ATTR_LABELS[k]||k}</span>`).join('');

  detail.style.display = 'block';
  detail.innerHTML = `
    <div class="detail-title">${race.name}</div>
    <div class="detail-desc">${race.trait}</div>
    <div class="detail-stats">
      ${bonusPills}${penaltyPills}
      ${!bonusPills && !penaltyPills ? '<span class="stat-pill info">Sem modificadores fixos</span>' : ''}
    </div>`;
}

function selectClass(id, btn) {
  selectedClass = id;
  document.querySelectorAll('#class-grid .option-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');

  const cls    = rpgOptions.classes.find(c => c.id === id);
  const detail = document.getElementById('class-detail');
  if (!cls) { detail.style.display = 'none'; return; }

  const primaryLabels = cls.primary.map(a => ATTR_LABELS[a]||a).join(', ');
  const savesLabels   = cls.saves.map(a => ATTR_LABELS[a]||a).join(', ');

  detail.style.display = 'block';
  detail.innerHTML = `
    <div class="detail-title">${cls.name}</div>
    <div class="detail-desc">${cls.desc}</div>
    <div class="detail-stats">
      <span class="stat-pill info">❤️ HP base: ${cls.hp_base}</span>
      <span class="stat-pill info">🎲 d${cls.hit_die}</span>
      <span class="stat-pill bonus">⭐ ${primaryLabels}</span>
      <span class="stat-pill info">🛡️ Saves: ${savesLabels}</span>
    </div>`;
}

function changeAttr(attr, delta) {
  const newVal = attributes[attr] + delta;
  if (newVal < 8 || newVal > 18) return;
  if (delta > 0 && pointsLeft <= 0) return;
  attributes[attr] = newVal;
  pointsLeft -= delta;
  updateAttrUI();
}

function updateAttrUI() {
  document.getElementById('points-left').textContent = pointsLeft;
  for (const [attr, val] of Object.entries(attributes)) {
    const mod = Math.floor((val - 10) / 2);
    document.getElementById(`attr-${attr}`).textContent = val;
    document.getElementById(`mod-${attr}`).textContent  = mod >= 0 ? `+${mod}` : `${mod}`;
  }
}

async function confirmCreatePlayer() {
  const name       = document.getElementById('input-player-name').value.trim();
  const age        = parseInt(document.getElementById('input-player-age').value) || 26;
  const appearance = document.getElementById('input-appearance').value.trim();

  if (!name)          { alert('Digite um nome para o personagem.'); return; }
  if (!selectedRace)  { alert('Escolha uma raça.'); return; }
  if (!selectedClass) { alert('Escolha uma classe.'); return; }

  const btn = document.querySelector('.btn-primary');
  btn.disabled    = true;
  btn.textContent = 'Criando...';

  try {
    const sessRes = await fetch(`${API}/api/session/new`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ character_id: currentCharacter.id, game_mode: currentMode })
    });
    if (!sessRes.ok) throw new Error(`Erro ao criar sessão: ${await sessRes.text()}`);
    const sessData = await sessRes.json();
    currentSession   = sessData.session_id;
    currentCharacter = { ...currentCharacter, ...sessData.character };

    const playerRes = await fetch(`${API}/api/player/create`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        session_id: currentSession,
        name, race: selectedRace, char_class: selectedClass,
        mode: currentMode, age, appearance,
        attributes: currentMode === 'full' ? attributes : null
      })
    });
    if (!playerRes.ok) throw new Error(`Erro ao criar personagem: ${await playerRes.text()}`);
    const playerData = await playerRes.json();

    openChatScreen(sessData.character, currentMode, playerData.player);
    clearMessages();
    if (sessData.character.scenario) appendScenario(sessData.character.scenario);
    appendMessage('assistant', sessData.character.first_message, sessData.character.name);

  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Entrar no mundo ⚔️';
  }
}

// ─── SESSÕES ──────────────────────────────────────────────────────────────────

async function startNewChat(characterId, mode) {
  try {
    const r = await fetch(`${API}/api/session/new`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ character_id: characterId, game_mode: mode })
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    currentSession   = data.session_id;
    currentCharacter = { ...currentCharacter, ...data.character };
    openChatScreen(data.character, mode, null);
    clearMessages();
    if (data.character.scenario) appendScenario(data.character.scenario);
    appendMessage('assistant', data.character.first_message, data.character.name);
  } catch (e) { alert(`Erro: ${e.message}`); }
}

async function continueSession(sessionId, characterId) {
  try {
    const r    = await fetch(`${API}/api/session/${sessionId}`);
    if (!r.ok) throw new Error('Sessão não encontrada');
    const data = await r.json();
    currentSession   = sessionId;
    currentMode      = data.game_mode || 'narrative';
    currentCharacter = { id: characterId, name: data.character_name, avatar_emoji: data.avatar_emoji };
    const player     = data.rpg_state?.player || null;
    openChatScreen(currentCharacter, currentMode, player);
    clearMessages();
    for (const msg of data.history) {
      if (msg.role === 'user')           appendMessage('user',      msg.content, 'Você');
      else if (msg.role === 'assistant') appendMessage('assistant', msg.content, data.character_name);
    }
  } catch (e) { alert(`Erro: ${e.message}`); }
}

async function deleteSession(event, sessionId) {
  event.stopPropagation();
  await fetch(`${API}/api/session/${sessionId}`, { method:'DELETE' });
  await loadSavedSessions();
}

// ─── NAVEGAÇÃO ────────────────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function openChatScreen(character, mode, player) {
  showScreen('screen-chat');

  // Painel do personagem (coluna 1)
  setupCharPanel(character, mode);

  // Topbar
  document.getElementById('topbar-char-name').textContent  = character.name || '?';
  document.getElementById('topbar-session').textContent    = `sessão: ${currentSession}`;

  // Sidebar (coluna 3)
  setupSidebar(mode, player);

  document.getElementById('user-input').focus();
}

function setupCharPanel(character, mode) {
  // Emoji placeholder
  document.getElementById('portrait-emoji').textContent   = character.avatar_emoji || '👤';
  document.getElementById('panel-char-name').textContent  = character.name || '?';
  document.getElementById('panel-char-world').textContent = character.world_id || '';

  const modeLabels = { narrative:'📖 Narrativo', medium:'⚖️ Médio', full:'🎲 Completo' };
  document.getElementById('panel-mode-badge').textContent = modeLabels[mode] || mode;

  // Tenta carregar imagem principal
  tryLoadPortrait(character.id, 'default');

  // Expressões disponíveis
  loadExpressions(character.id);

  // Mesa do dado
  const btnRoll    = document.getElementById('btn-roll-table');
  const idleMsg    = document.getElementById('dice-table-idle');
  if (mode === 'full') {
    btnRoll.style.display  = 'flex';
    idleMsg.style.display  = 'none';
  } else {
    btnRoll.style.display  = 'none';
    idleMsg.style.display  = 'flex';
    idleMsg.querySelector('small').textContent = mode === 'narrative' ? 'modo narrativo' : 'modo médio';
  }
}

function tryLoadPortrait(charId, variant) {
  const img         = document.getElementById('char-portrait-img');
  const placeholder = document.getElementById('char-portrait-placeholder');
  const btnGenerate = document.getElementById('btn-generate-portrait');
  
  // Verificar se imagem já existe no servidor
  fetch(`/api/sd/check-portrait/${charId}`)
    .then(res => res.json())
    .then(data => {
      if (data.exists && data.image_path) {
        // Imagem existe, carregar
        img.onload = () => {
          img.style.display = 'block';
          placeholder.style.display = 'none';
          btnGenerate.style.display = 'none';
        };
        
        img.onerror = () => {
          // Erro ao carregar, mostrar placeholder + botão
          img.style.display = 'none';
          placeholder.style.display = 'flex';
          btnGenerate.style.display = 'flex';
        };
        
        // Adicionar timestamp para evitar cache do browser
        img.src = data.image_path + '?t=' + Date.now();
      } else {
        // Imagem não existe, mostrar placeholder + botão gerar
        img.style.display = 'none';
        placeholder.style.display = 'flex';
        
        // Verificar se SD está disponível
        fetch('/api/sd/status')
          .then(res => res.json())
          .then(status => {
            if (status.available) {
              btnGenerate.style.display = 'flex';
              btnGenerate.disabled = false;
            } else {
              btnGenerate.style.display = 'none';
            }
          })
          .catch(() => {
            btnGenerate.style.display = 'none';
          });
      }
    })
    .catch(err => {
      console.error('Erro ao verificar retrato:', err);
      img.style.display = 'none';
      placeholder.style.display = 'flex';
      btnGenerate.style.display = 'none';
    });
}

function loadExpressions(charId) {
  const container  = document.getElementById('char-expressions');
  // Não carrega expressões por enquanto
  container.innerHTML = '';
}

function switchExpression(charId, variant, btn) {
  document.querySelectorAll('.expr-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  tryLoadPortrait(charId, variant);
}

function setupSidebar(mode, player) {
  const rpgFull = document.getElementById('rpg-panel-full');
  const rpgNarr = document.getElementById('rpg-panel-narrative');

  if (mode === 'narrative') {
    rpgFull.style.display = 'none';
    rpgNarr.style.display = 'block';
  } else {
    rpgFull.style.display = 'block';
    rpgNarr.style.display = 'none';
    document.getElementById('stats-section').style.display  = mode === 'full' ? 'block' : 'none';
    document.getElementById('quests-section').style.display = mode === 'full' ? 'block' : 'none';
    if (player) updateSidebar(player, mode);
  }
}

function goBack() {
  showScreen('screen-select');
  loadSavedSessions();
}

function clearChat() {
  if (!confirm('Iniciar nova conversa com este personagem?')) return;
  openModeModal(currentCharacter.id, currentCharacter.avatar_emoji, currentCharacter.name);
}

// ─── SIDEBAR UPDATE ───────────────────────────────────────────────────────────

function updateSidebar(player, mode) {
  if (!player) return;

  // Player title
  document.getElementById('player-title').textContent = player.name || 'Personagem';
  const capitalize = (str) => str ? str.charAt(0).toUpperCase() + str.slice(1).toLowerCase() : '';
  document.getElementById('player-race-class').textContent =
    `${capitalize(player.race)} · ${capitalize(player.char_class)}${player.age ? ` · ${player.age} anos` : ''}`;

  // Relacionamento
  const score = player.relationship?.score ?? 50;
  const relColors = [[0,'#e05555'],[21,'#e09055'],[41,'#9090a8'],[61,'#4caf82'],[81,'#9b7de0']];
  let color = '#9090a8';
  for (const [t,c] of relColors) { if (score >= t) color = c; }
  document.getElementById('rel-bar').style.width      = `${score}%`;
  document.getElementById('rel-bar').style.background = color;
  document.getElementById('rel-score').textContent    = score;
  document.getElementById('rel-label').textContent    = player.relationship?.label || 'Neutro';

  if (mode === 'full') {
    const hpPct = Math.max(0, Math.round((player.hp_current / player.hp_max) * 100));
    document.getElementById('hp-bar').style.width  = `${hpPct}%`;
    document.getElementById('hp-text').textContent = `${player.hp_current}/${player.hp_max}`;
    const xpPct = player.xp_next > 0 ? Math.round((player.xp / player.xp_next) * 100) : 0;
    document.getElementById('xp-bar').style.width  = `${xpPct}%`;
    document.getElementById('xp-text').textContent = `${player.xp}/${player.xp_next}`;
    document.getElementById('level-text').textContent = `Nível ${player.level}`;

    if (player.attributes) {
      document.getElementById('attrs-mini').innerHTML =
        Object.entries(player.attributes).map(([k,v]) => {
          const mod = Math.floor((v-10)/2);
          return `<div class="attr-mini">
            <span class="attr-mini-name">${ATTR_LABELS[k]||k}</span>
            <span class="attr-mini-val">${v}</span>
            <span class="attr-mini-mod">${mod>=0?'+'+mod:mod}</span>
          </div>`;
        }).join('');
    }

    const active = (player.quests||[]).filter(q=>q.status==='active');
    document.getElementById('quests-list').innerHTML = active.length
      ? active.map(q=>`<div class="quest-item"><div class="quest-title">${q.title}</div><div class="quest-desc">${q.description.substring(0,60)}...</div></div>`).join('')
      : '<span class="empty-hint">Nenhuma missão ativa</span>';
  }

  // Inventário
  const items = player.inventory?.items || [];
  const gold  = player.inventory?.gold  || 0;
  const goldBadge = document.getElementById('gold-badge');
  goldBadge.textContent = gold > 0 ? `🪙 ${gold}` : '';
  document.getElementById('inventory-list').innerHTML = items.length
    ? items.map(i=>`<div class="inventory-item"><span>${i.name}</span><span class="inventory-item-qty">x${i.quantity}</span></div>`).join('')
    : '<span class="empty-hint">Vazio</span>';
}

// ─── MENSAGENS ────────────────────────────────────────────────────────────────

function clearMessages() { document.getElementById('messages').innerHTML = ''; }

/**
 * Sanitiza texto do LLM e formata markdown básico.
 * Nunca insere HTML diretamente — escapa primeiro, depois aplica formatação.
 * Isso previne XSS caso o modelo retorne tags HTML maliciosas.
 */
function sanitize(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatText(text) {
  return sanitize(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')  // **negrito**
    .replace(/\*([^*]+)\*/g,     '<em>$1</em>');          // *itálico*
}

function appendScenario(scenario) {
  const msgs = document.getElementById('messages');
  const div  = document.createElement('div');
  div.className = 'scenario-card';
  div.innerHTML = `<div class="scenario-label">📖 Cenário</div><div class="scenario-text">${formatText(scenario)}</div>`;
  msgs.appendChild(div);
}

function appendMessage(role, content, label) {
  const msgs = document.getElementById('messages');
  const div  = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `<div class="message-header">${label}</div><div class="bubble">${formatText(content)}</div>`;
  msgs.appendChild(div);
  scrollToBottom();
  return div;
}

function appendLevelUp(level) {
  const msgs = document.getElementById('messages');
  const div  = document.createElement('div');
  div.className = 'levelup-card';
  div.innerHTML = `<div class="levelup-title">⬆️ LEVEL UP!</div><div class="levelup-sub">Você alcançou o Nível ${level}!</div>`;
  msgs.appendChild(div);
  scrollToBottom();
}

function showTypingIndicator(label) {
  const msgs = document.getElementById('messages');
  const div  = document.createElement('div');
  div.className = 'message assistant typing-indicator';
  div.id = 'typing-indicator';
  div.innerHTML = `<div class="message-header">${label}</div><div class="bubble"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
  msgs.appendChild(div);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function scrollToBottom() {
  const msgs = document.getElementById('messages');
  msgs.scrollTop = msgs.scrollHeight;
}

// ─── CHAT ─────────────────────────────────────────────────────────────────────

async function sendMessage() {
  if (isStreaming) return;
  const input = document.getElementById('user-input');
  const text  = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';

  appendMessage('user', text, 'Você');
  setStreaming(true);

  const charName = currentCharacter?.name || 'Personagem';
  showTypingIndicator(charName);

  try {
    const res = await fetch(`${API}/api/chat`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: currentSession, character_id: currentCharacter.id, message: text })
    });
    if (!res.ok) throw new Error(await res.text());

    removeTypingIndicator();

    const msgs   = document.getElementById('messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant';
    const bubble = document.createElement('div');
    bubble.className = 'bubble typing-cursor';
    msgDiv.innerHTML = `<div class="message-header">${charName}</div>`;
    msgDiv.appendChild(bubble);
    msgs.appendChild(msgDiv);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6);
        if (raw === '[DONE]') break;

        if (raw.startsWith('__ROLL__')) {
          try {
            const rollData = JSON.parse(raw.slice(8));
            await new Promise(resolve => showDiceRoll(rollData.result, resolve));
            msgs.appendChild(msgDiv);
          } catch { /* silencioso */ }
          continue;
        }

        fullText += raw.replace(/\\n/g, '\n');
        bubble.innerHTML = formatText(fullText);
        scrollToBottom();
      }
    }

    bubble.classList.remove('typing-cursor');

    // Atualiza sidebar
    if (currentMode !== 'narrative') {
      try {
        const stateRes = await fetch(`${API}/api/player/${currentSession}`);
        if (stateRes.ok) {
          const sd = await stateRes.json();
          if (sd.player) {
            const prevLevel = parseInt(document.getElementById('level-text')?.textContent?.replace('Nível ','')) || 1;
            if (sd.player.level > prevLevel) appendLevelUp(sd.player.level);
            updateSidebar(sd.player, currentMode);
          }
        }
      } catch { /* silencioso */ }
    }

  } catch (e) {
    removeTypingIndicator();
    appendMessage('assistant', `*Erro: ${e.message}*`, 'Sistema');
  } finally {
    setStreaming(false);
  }
}

async function manualRoll() {
  if (!currentSession) return;
  try {
    const r    = await fetch(`${API}/api/roll`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: currentSession })
    });
    const data = await r.json();
    showDiceRoll(data, null);
  } catch (e) { console.error(e); }
}

function setStreaming(val) {
  isStreaming = val;
  document.getElementById('send-btn').disabled   = val;
  document.getElementById('user-input').disabled = val;
  if (!val) document.getElementById('user-input').focus();
}

// ─── UTIL ─────────────────────────────────────────────────────────────────────

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

// ─── RESIZE DAS LATERAIS ──────────────────────────────────────────────────────

(function initResize() {
  /**
   * Drag-to-resize para as colunas laterais.
   * Arrastar a alça esquerda redimensiona o painel do personagem.
   * Arrastar a alça direita redimensiona a sidebar RPG.
   */
  function makeResizable(handleId, panelId, side) {
    const handle = document.getElementById(handleId);
    const panel  = document.getElementById(panelId);
    if (!handle || !panel) return;

    let startX    = 0;
    let startW    = 0;
    let dragging  = false;

    handle.addEventListener('mousedown', e => {
      dragging = true;
      startX   = e.clientX;
      startW   = panel.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cursor    = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const delta = side === 'left'
        ? e.clientX - startX      // painel esquerdo: drag direita = aumenta
        : startX - e.clientX;     // painel direito: drag esquerda = aumenta

      const minW = parseInt(panel.style.minWidth) || 160;
      const maxW = parseInt(panel.style.maxWidth) || 400;
      const newW = Math.max(minW, Math.min(maxW, startW + delta));
      panel.style.width = newW + 'px';

      // Salva preferência do usuário no localStorage
      localStorage.setItem(`panel-${panelId}-width`, newW);
    });

    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
    });

    // Restaura largura salva
    const saved = localStorage.getItem(`panel-${panelId}-width`);
    if (saved) panel.style.width = saved + 'px';
  }

  // Inicializa após o DOM carregar
  document.addEventListener('DOMContentLoaded', () => {
    // Reset forçado: se você renomeou o localStorage antigo, limpa tudo relacionado a painéis
    const keys = ['panel-char-panel-width', 'panel-sidebar-width'];
    keys.forEach(k => {
      const val = localStorage.getItem(k);
      if (!val || parseInt(val) < 100 || parseInt(val) > 500 || isNaN(parseInt(val))) {
        localStorage.removeItem(k);
      }
    });

    makeResizable('resize-left',  'char-panel', 'left');
    makeResizable('resize-right', 'sidebar',    'right');
  });
})();

// ─── GERAÇÃO DE RETRATO COM STABLE DIFFUSION ──────────────────────────────────

async function generatePortrait() {
  if (!currentCharacter || !currentCharacter.id) {
    alert('Nenhum personagem selecionado');
    return;
  }

  const btnGenerate = document.getElementById('btn-generate-portrait');
  const loading = document.getElementById('portrait-loading');
  const placeholder = document.getElementById('char-portrait-placeholder');
  
  // Verificar se SD está disponível
  try {
    const statusRes = await fetch('/api/sd/status');
    const status = await statusRes.json();
    
    if (!status.available) {
      alert('⚠️ Stable Diffusion não está disponível.\n\nInicie o Automatic1111 WebUI com:\nwebui-user.bat --api --medvram --xformers');
      return;
    }
  } catch (err) {
    alert('Erro ao verificar status do SD: ' + err.message);
    return;
  }

  // Mostrar loading
  btnGenerate.style.display = 'none';
  loading.style.display = 'flex';

  // Preparar dados do personagem
  const payload = {
    character_id: currentCharacter.id,
    name: currentCharacter.name || 'Personagem',
    race: currentCharacter.race || 'human',
    char_class: currentCharacter.class || 'warrior',
    gender: currentCharacter.gender || 'female',
    description: currentCharacter.description || null,
    nsfw: true, // Permitir conteúdo adulto (usuário especificou +18)
    force_regenerate: false
  };

  try {
    const response = await fetch('/api/sd/generate-portrait', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (response.ok && result.success) {
      // Sucesso! Carregar imagem gerada
      console.log('✓ Retrato gerado:', result.image_path);
      
      // Recarregar imagem (vai esconder placeholder e mostrar imagem real)
      tryLoadPortrait(currentCharacter.id);
      
      // Esconder loading
      loading.style.display = 'none';
      
    } else {
      throw new Error(result.message || 'Falha ao gerar retrato');
    }

  } catch (err) {
    console.error('Erro ao gerar retrato:', err);
    alert('❌ Erro ao gerar retrato:\n' + err.message);
    
    // Esconder loading, mostrar botão novamente
    loading.style.display = 'none';
    btnGenerate.style.display = 'flex';
  }
}

// Exportar para uso global
window.generatePortrait = generatePortrait;
