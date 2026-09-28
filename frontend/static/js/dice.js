/**
 * dice.js — Animação 3D de dado estilo Baldur's Gate 3
 */

function playDiceSound(type = 'roll') {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();

    if (type === 'crit') {
      [261, 329, 392, 523].forEach((freq, i) => {
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, ctx.currentTime + i * 0.06);
        gain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + i * 0.06 + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.06 + 0.5);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + i * 0.06);
        osc.stop(ctx.currentTime + i * 0.06 + 0.5);
      });
    }
  } catch { }
}

function createD20SVG(number, color = '#c8a84b', glowColor = null) {
  const glow = glowColor ? `filter: drop-shadow(0 0 12px ${glowColor}) drop-shadow(0 0 24px ${glowColor});` : '';
  return `
    <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="${glow}">
      <defs>
        <linearGradient id="faceGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:${adjustColor(color, 50)};stop-opacity:1"/>
          <stop offset="50%" style="stop-color:${color};stop-opacity:1"/>
          <stop offset="100%" style="stop-color:${adjustColor(color, -40)};stop-opacity:1"/>
        </linearGradient>
        <radialGradient id="highlight">
          <stop offset="0%" style="stop-color:white;stop-opacity:0.3"/>
          <stop offset="70%" style="stop-color:white;stop-opacity:0"/>
        </radialGradient>
        <!-- Pattern arabesco sutil -->
        <pattern id="arabesque" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 10,0 Q 15,5 10,10 Q 5,5 10,0 Z" 
                fill="${adjustColor(color, -20)}" opacity="0.15"/>
          <path d="M 0,10 Q 5,15 10,10 Q 5,5 0,10 Z" 
                fill="${adjustColor(color, 30)}" opacity="0.1"/>
          <circle cx="10" cy="10" r="1.5" fill="${adjustColor(color, 40)}" opacity="0.2"/>
        </pattern>
        <!-- Pattern de linhas finas decorativas -->
        <pattern id="ornament" x="0" y="0" width="8" height="8" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="8" y2="8" stroke="${adjustColor(color, -30)}" stroke-width="0.3" opacity="0.2"/>
          <line x1="8" y1="0" x2="0" y2="8" stroke="${adjustColor(color, 20)}" stroke-width="0.3" opacity="0.15"/>
        </pattern>
      </defs>
      <!-- Sombra externa -->
      <polygon points="50,2 95,28 95,72 50,98 5,72 5,28"
               fill="rgba(0,0,0,0.5)" transform="translate(2,4)"/>
      <!-- Corpo principal hexagonal com gradiente -->
      <polygon points="50,2 95,28 95,72 50,98 5,72 5,28"
               fill="url(#faceGrad)" 
               stroke="${adjustColor(color, 60)}" 
               stroke-width="2"/>
      <!-- Textura arabesco -->
      <polygon points="50,2 95,28 95,72 50,98 5,72 5,28"
               fill="url(#arabesque)"/>
      <!-- Ornamento de linhas cruzadas -->
      <polygon points="50,8 88,30 88,70 50,92 12,70 12,30"
               fill="url(#ornament)"/>
      <!-- Highlight sutil no topo -->
      <ellipse cx="50" cy="35" rx="30" ry="20" 
               fill="url(#highlight)"/>
      <!-- Detalhes decorativos nos cantos -->
      <g opacity="0.3" fill="${adjustColor(color, 50)}">
        <circle cx="50" cy="6" r="2"/>
        <circle cx="90" cy="28" r="1.5"/>
        <circle cx="90" cy="72" r="1.5"/>
        <circle cx="50" cy="94" r="2"/>
        <circle cx="10" cy="72" r="1.5"/>
        <circle cx="10" cy="28" r="1.5"/>
      </g>
      <!-- Borda interna para profundidade -->
      <polygon points="50,8 88,30 88,70 50,92 12,70 12,30"
               fill="none" 
               stroke="${adjustColor(color, -20)}" 
               stroke-width="0.5" 
               opacity="0.4"/>
      <!-- Número CENTRALIZADO -->
      <text x="50" y="52" text-anchor="middle" dominant-baseline="middle"
            font-family="Georgia, serif" font-size="${number >= 10 ? '28' : '34'}"
            font-weight="bold" fill="white"
            stroke="${adjustColor(color, -80)}" stroke-width="0.5"
            style="text-shadow: 0 2px 6px rgba(0,0,0,0.9), 0 0 8px rgba(0,0,0,0.5);">${number}</text>
    </svg>`;
}

function adjustColor(hex, amount) {
  try {
    let h = hex.replace('#','');
    if (h.length === 3) h = h.split('').map(c=>c+c).join('');
    const r = Math.max(0, Math.min(255, parseInt(h.substring(0,2),16) + amount));
    const g = Math.max(0, Math.min(255, parseInt(h.substring(2,4),16) + amount));
    const b = Math.max(0, Math.min(255, parseInt(h.substring(4,6),16) + amount));
    return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
  } catch { return hex; }
}

const OUTCOME_CONFIG = {
  sucesso_critico: { color: '#ffd700', glow: '#ffd700', label: '⭐ Sucesso Crítico!', soundType: 'crit',  textColor: '#ffd700' },
  sucesso:         { color: '#4caf82', glow: '#4caf82', label: '✅ Sucesso!',          soundType: 'land',  textColor: '#4caf82' },
  sucesso_parcial: { color: '#80c090', glow: null,      label: '🟡 Sucesso Parcial',   soundType: 'land',  textColor: '#80c090' },
  falha_parcial:   { color: '#c8a84b', glow: null,      label: '🟠 Falha Parcial',     soundType: 'land',  textColor: '#f0b030' },
  falha:           { color: '#8080a0', glow: null,      label: '❌ Falha',              soundType: 'land',  textColor: '#9090a8' },
  falha_critica:   { color: '#e05555', glow: '#e05555', label: '💀 Falha Crítica!',    soundType: 'fail',  textColor: '#e05555' },
};

let diceOverlay = null;

function showDiceRoll(rollResult, onComplete) {
  if (diceOverlay) diceOverlay.remove();

  const { natural, modifier, final, outcome } = rollResult;
  const cfg = OUTCOME_CONFIG[outcome] || OUTCOME_CONFIG['falha'];

  diceOverlay = document.createElement('div');
  diceOverlay.id = 'dice-overlay';
  diceOverlay.innerHTML = `
    <div class="dice-backdrop"></div>
    <div class="dice-stage">
      <div class="dice-wrapper" id="dice-wrapper">
        <div class="dice-3d" id="dice-3d"></div>
      </div>
      <div class="dice-result-panel" id="dice-result-panel" style="opacity:0">
        <div class="dice-formula" id="dice-formula"></div>
        <div class="dice-outcome-label" id="dice-outcome-label"></div>
      </div>
      <div class="dice-skip-hint">Clique para pular</div>
    </div>
  `;
  document.body.appendChild(diceOverlay);

  const wrapper     = document.getElementById('dice-wrapper');
  const dice3d      = document.getElementById('dice-3d');
  const resultPanel = document.getElementById('dice-result-panel');
  const formula     = document.getElementById('dice-formula');
  const outcomeEl   = document.getElementById('dice-outcome-label');

  let completed = false;
  diceOverlay.addEventListener('click', () => {
    if (!completed) finishAnimation();
  });

  let frame       = 0;
  let currentNum  = 1;
  let spinAngle   = 0;
  let rafId       = null;

  const totalDuration = 2000;
  const startTime     = Date.now();

  dice3d.innerHTML = createD20SVG(currentNum, cfg.color);
  wrapper.style.transform = 'scale(0) rotate(-180deg)';
  wrapper.style.transition = 'transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)';

  requestAnimationFrame(() => {
    wrapper.style.transform = 'scale(1) rotate(0deg)';
  });

  function spinStep() {
    const elapsed  = Date.now() - startTime;
    const progress = Math.min(elapsed / totalDuration, 1);
    const eased = easeOutCubic(progress);

    spinAngle += (1 - eased) * 25 + 3;
    const tilt = Math.sin(spinAngle * 0.08) * 15;
    dice3d.style.transform = `rotateY(${spinAngle}deg) rotateX(${tilt}deg)`;

    const blurAmount = (1 - eased) * 5;
    dice3d.style.filter = blurAmount > 0.3
      ? `blur(${blurAmount.toFixed(1)}px) brightness(${1 + blurAmount * 0.1})`
      : 'none';

    const frameSkip = Math.floor(eased * 10 + 1);
    if (frame % frameSkip === 0) {
      if (progress < 0.8) {
        currentNum = Math.floor(Math.random() * 20) + 1;
      } else {
        currentNum = shuffleToward(currentNum, natural);
      }
      const tempCfg = progress > 0.85 ? cfg : { color: '#c8a84b' };
      dice3d.innerHTML = createD20SVG(currentNum, tempCfg.color);
    }

    frame++;

    if (progress < 1) {
      rafId = requestAnimationFrame(spinStep);
    } else {
      finishAnimation();
    }
  }

  requestAnimationFrame(() => setTimeout(() => requestAnimationFrame(spinStep), 300));

  function finishAnimation() {
    if (completed) return;
    completed = true;
    if (rafId) cancelAnimationFrame(rafId);

    dice3d.style.transition = 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.3s ease';
    dice3d.innerHTML    = createD20SVG(natural, cfg.color, cfg.glow);
    dice3d.style.filter = 'none';
    dice3d.style.transform = 'rotateY(0deg) rotateX(0deg) scale(1.05)';
    
    setTimeout(() => {
      dice3d.style.transform = 'rotateY(0deg) rotateX(0deg) scale(1)';
    }, 100);

    setTimeout(() => {
      if (cfg.soundType === 'crit') {
        playDiceSound('crit');
      }

      if (outcome === 'sucesso_critico' || outcome === 'falha_critica') {
        wrapper.style.filter = `drop-shadow(0 0 20px ${cfg.glow}) drop-shadow(0 0 40px ${cfg.glow})`;
        setTimeout(() => { wrapper.style.filter = ''; }, 1500);
      }

      const sign = modifier >= 0 ? `+${modifier}` : `${modifier}`;
      formula.innerHTML = `
        <span class="dice-nat">d20 = ${natural}</span>
        ${modifier !== 0 ? `<span class="dice-sep"> ${sign >= '+0' ? '+' : ''}${modifier} </span><span class="dice-total">= ${final}</span>` : ''}
      `;
      outcomeEl.textContent  = cfg.label;
      outcomeEl.style.color  = cfg.textColor;
      resultPanel.style.transition = 'opacity 0.4s ease';
      resultPanel.style.opacity    = '1';

      setTimeout(() => {
        closeDiceOverlay();
        if (onComplete) onComplete();
      }, 2500);
    }, 400);
  }
}

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function shuffleToward(current, target) {
  if (Math.random() < 0.5) return target;
  const diff = target - current;
  if (diff === 0) return target;
  return current + (diff > 0 ? 1 : -1);
}

function closeDiceOverlay() {
  if (!diceOverlay) return;
  diceOverlay.style.transition = 'opacity 0.3s ease';
  diceOverlay.style.opacity    = '0';
  setTimeout(() => { if (diceOverlay) { diceOverlay.remove(); diceOverlay = null; } }, 300);
}

window.showDiceRoll = showDiceRoll;
window.closeDiceOverlay = closeDiceOverlay;
