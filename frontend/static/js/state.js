// Estado compartilhado do frontend.

export const state = {
  session: null,        // id da sessão atual
  character: null,      // { id, name, avatar_emoji, world_id, ... }
  mode: 'narrative',
  history: [],          // [{ role, content }] espelho do servidor
  images: [],           // [{ url, at }] cenas geradas
  swipe: { index: 0, count: 0 },  // versões da última resposta (🔄 guarda as anteriores)
  cast: [],             // [{ id, name, score, label, color }] relação com cada integrante (personagem de grupo)
  streaming: false,
  abort: null,          // AbortController da resposta em andamento
  rpgOptions: { races: [], classes: [], modes: [] },
  settings: null,
  profile: null,        // { name, age, appearance, about } salvo em Meu perfil
  sdAvailable: false,
};
