// Livro de fatos do mundo: entradas que só entram no prompt quando citadas.

import { api } from './api.js';
import { state } from './state.js';
import { $, closeModal, escapeHtml, openModal, toast } from './util.js';

let world = null;   // mundo carregado (as outras partes dele são preservadas ao salvar)

function rowHtml(e, i) {
  return `<div class="lore-row" data-row="${i}">
    <div class="lore-row-head">
      <input type="text" class="lore-name" placeholder="Título (ex: Cova de Tarsa)" value="${escapeHtml(e.name)}" />
      <label class="lore-always"><input type="checkbox" class="lore-always-box"${e.always ? ' checked' : ''} /> Sempre</label>
      <button class="msg-action" data-action="delete-lore" data-row="${i}" title="Apagar entrada">🗑️</button>
    </div>
    <input type="text" class="lore-keys" placeholder="Palavras-chave, separadas por vírgula (cova, tarsa)" value="${escapeHtml((e.keys || []).join(', '))}" />
    <textarea class="lore-text" rows="2" placeholder="O fato, em 1 a 3 frases">${escapeHtml(e.text)}</textarea>
  </div>`;
}

function readRows() {
  return [...document.querySelectorAll('#lore-list .lore-row')].map((row, i) => ({
    id: world.entries[i]?.id || '',
    name: row.querySelector('.lore-name').value.trim(),
    keys: row.querySelector('.lore-keys').value.split(',').map((k) => k.trim()).filter(Boolean),
    text: row.querySelector('.lore-text').value.trim(),
    always: row.querySelector('.lore-always-box').checked,
  }));
}

function render() {
  $('lore-list').innerHTML = world.entries.length
    ? world.entries.map(rowHtml).join('')
    : '<p class="modal-help">Nenhuma entrada ainda. Clique em "Nova entrada".</p>';
  $('lore-meta').textContent = `Mundo: ${world.name} · ${world.entries.length} entradas`;
}

export async function openLore() {
  const id = state.character?.world_id;
  if (!id) { toast('Este personagem não tem um mundo associado.', 'info'); return; }
  try {
    world = await api(`/api/worlds/${id}`);
    render();
    openModal('modal-lore');
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function addLore() {
  world.entries = [...readRows(), { id: '', name: '', keys: [], text: '', always: false }];
  render();
  document.querySelector('#lore-list .lore-row:last-child .lore-name')?.focus();
}

export function deleteLore(row) {
  const entries = readRows();
  entries.splice(row, 1);
  world.entries = entries;
  render();
}

export async function saveLore() {
  const entries = readRows().filter((e) => e.name || e.text);
  const incomplete = entries.find((e) => !e.name || !e.text);
  if (incomplete) { toast('Toda entrada precisa de título e de texto.', 'error'); return; }
  try {
    await api(`/api/worlds/${world.id}`, { method: 'PUT', body: { ...world, entries } });
    closeModal('modal-lore');
    toast('Livro de fatos salvo.', 'success');
  } catch (e) {
    toast(e.message, 'error', 7000);
  }
}
