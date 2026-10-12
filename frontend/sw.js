// Service worker do app no celular. Não guarda nada em cache: a IA roda no PC, então sem o PC
// não há o que mostrar. Só troca a tela de erro do navegador por um aviso em português.

const OFFLINE_HTML = `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RPG IA</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0a0a0f;color:#e8e8f0;font-family:system-ui,sans-serif;text-align:center;padding:24px}
h1{font-size:1.3rem}p{color:#9090a8;line-height:1.6}button{margin-top:16px;padding:12px 24px;
border-radius:8px;border:1px solid #7c5cbf;background:#7c5cbf;color:#fff;font-size:1rem}</style></head>
<body><div><h1>Não consegui falar com o seu PC</h1>
<p>Confira se o PC está ligado, com o RPG IA aberto,<br>e se o Tailscale está ligado no PC e no celular.</p>
<button onclick="location.reload()">Tentar de novo</button></div></body></html>`;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (e) => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => new Response(OFFLINE_HTML, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  })));
});
