// Modal da memória da história (resumo automático, editável).

import { api } from './api.js';
import { state } from './state.js';
import { $, closeModal, openModal, toast } from './util.js';

export async function openMemory() {
  try {
    const m = await api(`/api/session/${state.session}/memory`);
    $('memory-text').value = m.summary;
    $('memory-meta').textContent = m.summary
      ? `Cobre as primeiras ${m.summarized_upto} de ${m.total_messages} mensagens.`
      : `Ainda sem resumo (${m.total_messages} mensagens na conversa).`;
    openModal('modal-memory');
  } catch (e) {
    toast(e.message, 'error');
  }
}

export async function saveMemory() {
  try {
    await api(`/api/session/${state.session}/memory`, { method: 'PUT', body: { summary: $('memory-text').value } });
    closeModal('modal-memory');
    toast('Memória salva.', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}
