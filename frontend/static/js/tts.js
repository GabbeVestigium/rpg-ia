// Voz: engine "browser" (Web Speech API) ou "piper" (servidor, CPU).

import { api } from './api.js';
import { state } from './state.js';
import { toast } from './util.js';

let audio = null;
let speakId = 0;          // cada stopSpeaking invalida a fala que ainda está carregando
let piperWarned = false;  // avisa da troca para a voz do navegador uma vez só

/** Texto a falar: com dialogueOnly, pula as ações entre *asteriscos*. */
export function speakable(text, dialogueOnly) {
  let t = dialogueOnly ? text.replace(/\*[^*]*\*/g, ' ') : text.replace(/\*/g, '');
  t = t.replace(/["“”]/g, '').replace(/\s+/g, ' ').trim();
  return t;
}

export function stopSpeaking() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (audio) { audio.pause(); audio = null; }
  speakId++;
}

export function browserVoices() {
  return 'speechSynthesis' in window ? window.speechSynthesis.getVoices() : [];
}

export async function speak(text) {
  const s = state.settings;
  if (!s || s.tts_engine === 'off') return;
  stopSpeaking();
  const id = speakId;

  if (s.tts_engine === 'piper') {
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Erro ${res.status}`);
      }
      const blob = await res.blob();
      if (id !== speakId) return;   // trocou de conversa ou mandou parar enquanto carregava
      audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
      return;
    } catch (e) {
      if (id !== speakId) return;
      if (!piperWarned) { piperWarned = true; toast(`Voz: ${e.message} Usando a voz do navegador.`, 'info', 8000); }
    }
  }

  const spoken = speakable(text, s.tts_dialogue_only);
  if (!spoken || !('speechSynthesis' in window)) return;
  const utter = new SpeechSynthesisUtterance(spoken);
  utter.rate = s.tts_rate;
  utter.lang = 'pt-BR';
  const voices = browserVoices();
  const chosen = voices.find((v) => v.name === s.tts_voice)
    || voices.find((v) => v.lang && v.lang.toLowerCase().startsWith('pt'));
  if (chosen) { utter.voice = chosen; utter.lang = chosen.lang; }
  window.speechSynthesis.speak(utter);
}

export async function refreshSettings() {
  const { settings } = await api('/api/settings');
  state.settings = settings;
  return settings;
}
