// Colunas laterais redimensionáveis (a largura fica salva no navegador).

function makeResizable(handleId, panelId, side) {
  const handle = document.getElementById(handleId);
  const panel = document.getElementById(panelId);
  if (!handle || !panel) return;
  const key = `panel-${panelId}-width`;

  let startX = 0, startW = 0, dragging = false;

  handle.addEventListener('mousedown', (e) => {
    dragging = true;
    startX = e.clientX;
    startW = panel.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = side === 'left' ? e.clientX - startX : startX - e.clientX;
    const min = parseInt(panel.style.minWidth, 10) || 160;
    const max = parseInt(panel.style.maxWidth, 10) || 400;
    const width = Math.max(min, Math.min(max, startW + delta));
    panel.style.width = `${width}px`;
    try { localStorage.setItem(key, String(width)); } catch { /* modo privado */ }
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  try {
    const saved = parseInt(localStorage.getItem(key), 10);
    if (saved >= 100 && saved <= 500) panel.style.width = `${saved}px`;
  } catch { /* ignore */ }
}

export function initLayout() {
  makeResizable('resize-left', 'char-panel', 'left');
  makeResizable('resize-right', 'sidebar', 'right');
}

// Celular: as colunas laterais viram gavetas (👤 personagem e dados, 📊 status e inventário).
const PANEL_CLASSES = { 'char-panel': 'show-char-panel', sidebar: 'show-sidebar' };

export function togglePanel(panelId) {
  const layout = document.querySelector('.chat-layout');
  const cls = PANEL_CLASSES[panelId];
  if (!layout || !cls) return;
  const open = !layout.classList.contains(cls);
  closePanels();
  layout.classList.toggle(cls, open);
}

export function closePanels() {
  document.querySelector('.chat-layout')?.classList.remove(...Object.values(PANEL_CLASSES));
}
