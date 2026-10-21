// Construtor genérico de formulários (usado em Configurações e no editor de personagem).

import { escapeHtml } from './util.js';

/**
 * fields: [{ key, label, type, options?, min?, max?, step?, hint?, rows?, section? }]
 * type: text | number | range | select | checkbox | textarea
 */
export function buildForm(container, fields, values) {
  let html = '';
  for (const f of fields) {
    if (f.section) html += `<h4 class="form-section">${escapeHtml(f.section)}</h4>`;
    const id = `f-${f.key}`;
    const v = values[f.key];
    let control = '';
    if (f.type === 'select') {
      control = `<select id="${id}">${(f.options || []).map((o) => {
        const [val, label] = Array.isArray(o) ? o : [o, o];
        return `<option value="${escapeHtml(val)}"${String(val) === String(v) ? ' selected' : ''}>${escapeHtml(label)}</option>`;
      }).join('')}</select>`;
    } else if (f.type === 'checkbox') {
      control = `<input type="checkbox" id="${id}"${v ? ' checked' : ''} />`;
    } else if (f.type === 'textarea') {
      control = `<textarea id="${id}" rows="${f.rows || 3}">${escapeHtml(v ?? '')}</textarea>`;
    } else if (f.type === 'range') {
      control = `<input type="range" id="${id}" min="${f.min}" max="${f.max}" step="${f.step}" value="${escapeHtml(v)}" />
        <output id="${id}-out">${escapeHtml(v)}</output>`;
    } else {
      const extra = f.type === 'number'
        ? ` min="${f.min ?? ''}" max="${f.max ?? ''}" step="${f.step ?? 1}"` : '';
      control = `<input type="${f.type}" id="${id}" value="${escapeHtml(v ?? '')}"${extra} />`;
    }
    html += `<div class="form-field ${f.type === 'checkbox' ? 'inline' : ''}">
      <label for="${id}">${escapeHtml(f.label)}</label>${control}
      ${f.hint ? `<small>${escapeHtml(f.hint)}</small>` : ''}</div>`;
  }
  container.innerHTML = html;
  container.querySelectorAll('input[type=range]').forEach((r) => {
    r.addEventListener('input', () => { document.getElementById(`${r.id}-out`).textContent = r.value; });
  });
}

export function readForm(container, fields) {
  const out = {};
  for (const f of fields) {
    if (f.section && !f.key) continue;
    const el = container.querySelector(`#f-${f.key}`);
    if (!el) continue;
    if (f.type === 'checkbox') out[f.key] = el.checked;
    else if (f.type === 'number' || f.type === 'range') out[f.key] = Number(el.value);
    else out[f.key] = el.value;
  }
  return out;
}
