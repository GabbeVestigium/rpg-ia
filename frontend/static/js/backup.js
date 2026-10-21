// Exportar conversa e restaurar backup.

import { state } from './state.js';
import { toast } from './util.js';
import { loadCharacters, loadSavedSessions } from './screens.js';

export function exportChat() {
  if (!state.session) return;
  window.location.href = `/api/session/${state.session}/export`;   // o servidor responde como download
}

export async function restoreBackup(file) {
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/backup/restore', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`);
    const bad = data.rejected.length ? ` ${data.rejected.length} arquivo(s) recusado(s).` : '';
    toast(`Backup restaurado: ${data.restored} arquivo(s) novos, ${data.skipped_existing} já existiam.${bad}`,
      data.rejected.length ? 'info' : 'success', 9000);
    if (data.rejected.length) console.warn('Recusados no backup:', data.rejected);
    await Promise.all([loadCharacters(), loadSavedSessions()]);
  } catch (e) {
    toast(e.message, 'error', 8000);
  }
}
