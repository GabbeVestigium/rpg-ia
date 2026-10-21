// Tela de Configurações.

import { api } from './api.js';
import { buildForm, readForm } from './forms.js';
import { state } from './state.js';
import { $, closeModal, openModal, toast } from './util.js';
import { browserVoices, refreshSettings } from './tts.js';

function fields(models, voices) {
  return [
    { section: 'Modelo de texto', key: 'model', label: 'Modelo', type: 'select',
      options: [['', 'Automático (primeiro instalado)'], ...models.map((m) => [m, m])],
      hint: 'Para roleplay, prefira um modelo de RP/chat de 7B a 12B em Q4/Q5. Instale com: ollama pull <nome>.' },
    { key: 'temperature', label: 'Criatividade (temperatura)', type: 'range', min: 0.2, max: 1.5, step: 0.05 },
    { key: 'top_p', label: 'Top-P', type: 'range', min: 0.5, max: 1, step: 0.01 },
    { key: 'min_p', label: 'Min-P', type: 'range', min: 0, max: 0.3, step: 0.01,
      hint: 'Corta palavras improváveis sem deixar o texto seco. 0.05 é um bom padrão.' },
    { key: 'repeat_penalty', label: 'Penalidade de repetição', type: 'range', min: 1, max: 1.5, step: 0.01 },
    { key: 'num_ctx', label: 'Contexto (tokens)', type: 'select',
      options: [[3072, '3072'], [4096, '4096 (padrão, 6 GB)'], [6144, '6144'], [8192, '8192'], [12288, '12288']],
      hint: 'Mais contexto usa mais VRAM e deixa o modelo mais lento se não couber na GPU. A janela de mensagens se ajusta sozinha a este valor.' },
    { key: 'num_predict', label: 'Tamanho máximo da resposta (tokens)', type: 'number', min: 64, max: 4096, step: 50 },
    { key: 'response_length', label: 'Tamanho das respostas', type: 'select',
      options: [['short', 'Curtas'], ['medium', 'Médias'], ['long', 'Longas']] },
    { key: 'keep_alive', label: 'Manter o modelo na VRAM por', type: 'text', hint: 'Ex: 30m, 1h, 0 (descarrega logo).' },

    { section: 'Memória', key: 'memory_enabled', label: 'Resumir a história automaticamente', type: 'checkbox' },
    { key: 'history_turns', label: 'Turnos recentes enviados inteiros', type: 'number', min: 4, max: 60,
      hint: 'O que passar disso vira resumo. Menos turnos = mais rápido e menos VRAM.' },

    { section: 'Inventário', key: 'auto_inventory', label: 'Atualizar o inventário conforme a história', type: 'checkbox',
      hint: 'Quando a cena fala de itens ou ouro, o modelo confere o que você ganhou ou perdeu (modos Médio e Completo). Gasta uma geração curta a mais, só nessas cenas.' },

    { section: 'Imagens (Stable Diffusion)', key: 'sd_nsfw', label: 'Permitir imagens adultas (18+)', type: 'checkbox',
      hint: 'Só tira o filtro de nudez. Personagens continuam sempre adultos.' },
    { key: 'sd_steps', label: 'Passos de geração', type: 'number', min: 10, max: 60 },
    { key: 'scene_auto_unload', label: 'Liberar o modelo de texto da VRAM antes de gerar imagem', type: 'checkbox',
      hint: 'Recomendado na GPU de 6 GB: LLM e Stable Diffusion não cabem juntos.' },

    { section: 'Voz', key: 'tts_engine', label: 'Engine de voz', type: 'select',
      options: [['off', 'Desligada'], ['browser', 'Navegador (sem instalar nada)'], ['piper', 'Piper (local, mais natural)']] },
    { key: 'tts_auto_play', label: 'Ler cada resposta automaticamente', type: 'checkbox' },
    { key: 'tts_dialogue_only', label: 'Ler só as falas (pular *ações*)', type: 'checkbox' },
    { key: 'tts_rate', label: 'Velocidade', type: 'range', min: 0.6, max: 1.6, step: 0.05 },
    { key: 'tts_voice', label: 'Voz do navegador', type: 'select',
      options: [['', 'Automática (pt-BR)'], ...voices.map((v) => [v.name, `${v.name} (${v.lang})`])] },
    { key: 'piper_bin', label: 'Caminho do Piper', type: 'text', hint: 'Ex: C:\\piper\\piper.exe' },
    { key: 'piper_model', label: 'Modelo de voz do Piper (.onnx)', type: 'text',
      hint: 'Ex: C:\\piper\\pt_BR-faber-medium.onnx' },
  ];
}

let currentFields = [];

export async function openSettings() {
  let models = [];
  try { models = (await api('/api/status')).models.filter((m) => !m.toLowerCase().includes('embed')); } catch { /* offline */ }
  const settings = await refreshSettings();
  if (settings.model && !models.includes(settings.model)) models.push(settings.model);
  currentFields = fields(models, browserVoices());
  buildForm($('settings-form'), currentFields, settings);
  openModal('modal-settings');
}

export async function saveSettings() {
  try {
    const changes = readForm($('settings-form'), currentFields);
    const { settings } = await api('/api/settings', { method: 'PUT', body: changes });
    state.settings = settings;
    closeModal('modal-settings');
    updateAutoplayButton();
    toast('Configurações salvas.', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

export function updateAutoplayButton() {
  const btn = $('btn-autoplay');
  if (!btn || !state.settings) return;
  const on = state.settings.tts_engine !== 'off' && state.settings.tts_auto_play;
  btn.textContent = on ? '🔊 Voz' : '🔇 Voz';
  btn.classList.toggle('active', on);
}

export async function toggleAutoplay() {
  const s = state.settings;
  if (s.tts_engine === 'off') { toast('Ative uma engine de voz em Configurações.', 'info'); return; }
  const { settings } = await api('/api/settings', { method: 'PUT', body: { tts_auto_play: !s.tts_auto_play } });
  state.settings = settings;
  updateAutoplayButton();
}

