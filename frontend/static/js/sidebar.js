// Sidebar do RPG (relacionamento, status, inventário, missões) e painel do personagem.

import { $, capitalize, escapeHtml } from './util.js';

export const ATTR_LABELS = { STR: 'FOR', DEX: 'DES', CON: 'CON', INT: 'INT', WIS: 'SAB', CHA: 'CAR' };

export function setupSidebar(mode, player) {
  const full = $('rpg-panel-full');
  const narr = $('rpg-panel-narrative');
  if (mode === 'narrative') {
    full.style.display = 'none';
    narr.style.display = 'block';
    return;
  }
  full.style.display = 'block';
  narr.style.display = 'none';
  $('stats-section').style.display = mode === 'full' ? 'block' : 'none';
  $('quests-section').style.display = mode === 'full' ? 'block' : 'none';
  if (player) updateSidebar(player, mode);
}

export function setupDiceTable(mode) {
  const btn = $('btn-roll-table');
  const idle = $('dice-table-idle');
  if (mode === 'full') {
    btn.style.display = 'flex';
    idle.style.display = 'none';
  } else {
    btn.style.display = 'none';
    idle.style.display = 'flex';
    idle.querySelector('small').textContent = mode === 'narrative' ? 'modo narrativo' : 'modo médio';
  }
}

const REL_COLORS = [[0, '#e05555'], [21, '#e09055'], [41, '#9090a8'], [61, '#4caf82'], [81, '#9b7de0']];

export function currentLevel() {
  return parseInt($('level-text')?.textContent?.replace('Nível ', ''), 10) || 1;
}

export function updateSidebar(player, mode) {
  if (!player) return;

  $('player-title').textContent = player.name || 'Personagem';
  $('player-race-class').textContent =
    `${capitalize(player.race)} · ${capitalize(player.char_class)}${player.age ? ` · ${player.age} anos` : ''}`;

  const score = player.relationship?.score ?? 50;
  let color = '#9090a8';
  for (const [threshold, c] of REL_COLORS) if (score >= threshold) color = c;
  $('rel-bar').style.width = `${score}%`;
  $('rel-bar').style.background = color;
  $('rel-score').textContent = score;
  $('rel-label').textContent = player.relationship?.label || 'Neutro';

  if (mode === 'full') {
    const hpPct = player.hp_max > 0 ? Math.max(0, Math.round((player.hp_current / player.hp_max) * 100)) : 0;
    $('hp-bar').style.width = `${hpPct}%`;
    $('hp-text').textContent = `${player.hp_current}/${player.hp_max}`;
    const xpPct = player.xp_next > 0 ? Math.round((player.xp / player.xp_next) * 100) : 0;
    $('xp-bar').style.width = `${xpPct}%`;
    $('xp-text').textContent = `${player.xp}/${player.xp_next}`;
    $('level-text').textContent = `Nível ${player.level}`;

    if (player.attributes) {
      $('attrs-mini').innerHTML = Object.entries(player.attributes).map(([k, v]) => {
        const mod = Math.floor((v - 10) / 2);
        return `<div class="attr-mini">
          <span class="attr-mini-name">${ATTR_LABELS[k] || escapeHtml(k)}</span>
          <span class="attr-mini-val">${Number(v)}</span>
          <span class="attr-mini-mod">${mod >= 0 ? '+' + mod : mod}</span>
        </div>`;
      }).join('');
    }

    const active = (player.quests || []).filter((q) => q.status === 'active');
    $('quests-list').innerHTML = active.length
      ? active.map((q) => `<div class="quest-item"><div class="quest-title">${escapeHtml(q.title)}</div>
          <div class="quest-desc">${escapeHtml((q.description || '').slice(0, 60))}...</div></div>`).join('')
      : '<span class="empty-hint">Nenhuma missão ativa</span>';
  }

  const items = player.inventory?.items || [];
  const gold = player.inventory?.gold || 0;
  $('gold-badge').textContent = gold > 0 ? `🪙 ${gold}` : '';
  $('inventory-list').innerHTML = items.length
    ? items.map((i) => `<div class="inventory-item"><span>${escapeHtml(i.name)}</span>
        <span class="inventory-item-qty">x${Number(i.quantity)}</span></div>`).join('')
    : '<span class="empty-hint">Vazio</span>';
}
