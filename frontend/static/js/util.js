// Utilidades de DOM e texto.

export const $ = (id) => document.getElementById(id);

export function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Formata o texto do roleplay. Escapa o HTML primeiro (o modelo pode devolver tags),
 * depois aplica: **negrito**, *ação em itálico* e "fala" destacada.
 */
export function formatText(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/&quot;(.+?)&quot;/g, '<span class="dialogue">&quot;$1&quot;</span>');
}

export function toast(message, kind = 'info', ms = 4500) {
  const box = $('toasts');
  const div = document.createElement('div');
  div.className = `toast toast-${kind}`;
  div.textContent = message;
  box.appendChild(div);
  setTimeout(() => div.remove(), ms);
}

export function showScreen(id) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  $(id).classList.add('active');
}

export function openModal(id) { $(id).style.display = 'flex'; }
export function closeModal(id) { $(id).style.display = 'none'; }

export function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1).toLowerCase() : '';
}

// Tons que ficam bonitos no fundo escuro (amarelo e verde-oliva ficam com cara de sujo, então ficam de fora).
const HUES = [265, 330, 205, 175, 345, 290, 150, 225, 15];

/** Cor própria de cada personagem, tirada do id: o mesmo personagem tem sempre a mesma cor. */
export function characterHue(id) {
  let h = 0;
  for (const ch of String(id || '')) h = (h * 31 + ch.codePointAt(0)) % 9973;
  return HUES[h % HUES.length];
}

/** Avatar pequeno: o retrato quando existe, senão o emoji. */
export function avatarHtml(c) {
  return c.has_portrait
    ? `<img src="/portraits/${encodeURIComponent(c.id)}.png" alt="" loading="lazy" />`
    : `<span>${escapeHtml(c.avatar_emoji || '👤')}</span>`;
}
