// Estado compartilhado do frontend.

export const state = {
  session: null,        // id da sessão atual
  character: null,      // { id, name, avatar_emoji, world_id, ... }
  mode: 'narrative',
  history: [],          // [{ role, content }] espelho do servidor
  images: [],           // [{ url, at }] cenas geradas
  streaming: false,
  abort: null,          // AbortController da resposta em andamento
  rpgOptions: { races: [], classes: [], modes: [] },
  settings: null,
  sdAvailable: false,
};
