# AI_CONTEXT.md — Leia isso primeiro!

Este arquivo é para a IA que vai trabalhar neste projeto.
Leia antes de qualquer coisa.

---

## Sobre o Projeto

**RPG-IA** é um sistema de roleplay local com interface estilo visual novel.
100% offline, sem censura, conteúdo adulto (+18) permitido.

**Stack:**
- Backend: Python + FastAPI (porta 8000)
- LLM: Ollama local (porta 11434), modelo escolhido nas Configurações
- Frontend: HTML + CSS + JavaScript Vanilla (sem frameworks)
- Imagens: Stable Diffusion via Automatic1111 (porta 7860, opcional)

---

## Sobre o Usuário

- Área: Segurança da Informação (White Hat / Purple Team)
- Nível: Intermediário
- Idioma: Responder sempre em brasileiro
- Modo: Autopilot total (não pedir confirmação para coisas simples)
- Tom: Direto, ensinar enquanto faz, sem rodeios
- Não usar travessão (—) nas respostas

---

## Como Iniciar o Projeto

```powershell
# 1. Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# 2. Iniciar servidor
python backend/main.py

# 3. Abrir no browser
# http://127.0.0.1:8000
```

Ou usar o `🎮 Iniciar RPG-IA.bat` na pasta raiz.

**Pré-requisito:** Ollama rodando com deepseek-r1:7b instalado.
```powershell
ollama run deepseek-r1:7b
```

---

## Estrutura de Arquivos

```
rpg-ia/
├── AI_CONTEXT.md / DEVELOPMENT.md / INSTALL_SD.md / README.md
├── requirements.txt, requirements-dev.txt   # runtime / testes
├── start.ps1, 🎮 Iniciar RPG-IA.bat          # Launcher
│
├── backend/
│   ├── main.py                # App FastAPI: monta estáticos e inclui os routers
│   ├── routers/               # system, characters, sessions, chat, images
│   ├── config.py              # Infra: HOST, PORT, URLs, pastas (aceita variáveis de ambiente)
│   ├── settings_manager.py    # Preferências em data/settings.json (modelo, temperatura, voz...)
│   ├── ollama_client.py       # System prompt, stream, filtro de <think>, unload da VRAM
│   ├── memory.py              # Janela por tokens + resumo automático da história
│   ├── sd_client.py           # Automatic1111: prompts, geração
│   ├── scene.py               # Cena do chat: LLM extrai tags, SD gera, VRAM alternada
│   ├── tts_client.py          # Voz via Piper (a engine "browser" roda no frontend)
│   ├── safety.py              # Regra 18+ (idade, termos, tags do SD)
│   ├── storage.py             # safe_id, escrita atômica de JSON
│   ├── session_manager.py     # Sessões (histórico completo, resumo, cenas), lock por sessão
│   ├── character_manager.py   # CRUD de personagens/mundos com validação
│   ├── rpg_engine.py / rpg_models.py / models.py
│
├── frontend/
│   ├── index.html
│   └── static/
│       ├── css/style.css
│       └── js/                # Módulos ES (sem build): main, chat, messages, screens,
│                              # sidebar, portrait, settings, editor, memory, tts, forms,
│                              # api, state, util, layout + dice.js (clássico)
│
├── data/
│   ├── characters/, worlds/   # JSONs (editáveis também pela interface)
│   ├── sessions/              # Conversas (gitignored)
│   ├── scenes/                # Imagens de cena geradas (gitignored)
│   └── settings.json          # Preferências (gitignored)
└── tests/                     # pytest com Ollama/SD falsos + e2e_ui.py (Playwright)
```

---

## Endpoints da API

```
GET  /api/status, /api/settings          PUT /api/settings
GET  /api/session/{id}/export?format=md|txt   GET /api/backup   POST /api/backup/restore (zip, nunca apaga)
GET/PUT /api/profile                     (perfil do jogador, data/profile.json; entra no prompt em qualquer modo)
GET/POST /api/characters                 GET/PUT/DELETE /api/characters/{id}   GET /api/characters/{id}/prompt-size
GET  /api/worlds, /api/worlds/{id}       PUT /api/worlds/{id}   (o mundo inclui o livro de fatos: entries)
GET  /api/rpg/options
POST /api/session/new                    GET/DELETE /api/session/{id}
GET  /api/sessions                       GET/PUT /api/session/{id}/memory
POST /api/session/edit                   (edita o texto de uma mensagem)
POST /api/chat                           (SSE: eventos roll | token | error | done, JSON por linha)
POST /api/chat/regenerate, /api/chat/undo, /api/chat/swipe   (swipe: troca a última resposta por outra versão guardada)
POST /api/player/create                  GET /api/player/{session_id}
POST /api/roll, /api/quest/add           PATCH /api/quest/complete
GET  /api/sd/status                      POST /api/scene/generate
POST /api/sd/generate-portrait           GET /api/sd/check-portrait/{id}   DELETE /api/sd/delete-portrait/{id}
GET  /api/tts/status                     POST /api/tts  (Piper, devolve WAV)
```

---

## Features Implementadas

- Chat em streaming com filtro de blocos de raciocínio (`<think>`), regenerar, desfazer, editar e parar.
- Memória: o histórico completo fica em disco; ao modelo vai uma janela que respeita o orçamento de tokens
  (`num_ctx - num_predict - system prompt`) mais um resumo automático do que saiu da janela. O resumo é editável.
- Imagens: retrato do personagem e cenas no chat. O LLM extrai tags da cena, que se juntam às
  `appearance_tags` fixas do personagem (rosto consistente). Na GPU de 6 GB o LLM é descarregado
  da VRAM antes do SD gerar (`scene_auto_unload`).
- Voz: engine `browser` (Web Speech API, sem instalar nada) ou `piper` (CPU). Ler só falas ou tudo.
- Livro de fatos por mundo (`World.entries`, `backend/lorebook.py`): entradas com palavras-chave entram no prompt só quando
  citadas nas últimas mensagens (máx. 5 entradas e 1400 caracteres). Mantenha `World.lore` curto e ponha o detalhe em entradas.
- Galeria com criador/editor de personagem na interface.
- Configurações na interface (modelo instalado, temperatura, min_p, contexto, tamanho da resposta...).
- RPG: 3 modos (narrativo, médio, completo), d20 automático, XP, quests, relacionamento.

---

## Regras do Projeto

1. **Todo personagem é adulto (18+).** `safety.py` valida idade e termos na criação de personagem e do
   jogador, e as tags do SD passam por filtro. O negative prompt do SD sempre inclui termos de menor
   de idade, mesmo com `sd_nsfw` ligado. Nunca remover essas travas.
2. Conteúdo adulto roda no modelo local do usuário. A IA que desenvolve o projeto não escreve
   cenas explícitas nem prompts explícitos; escreve só o código e a estrutura.
3. Todo id vindo da rede passa por `safe_id` antes de virar nome de arquivo.

---

## Personagens Existentes

| ID | Nome | Mundo | O que é |
|----|------|-------|---------|
| `mesa-javali` | Mesa do Javali Cego | quermes | Personagem de grupo (`group: true`): isekai com harém, sete mulheres adultas de jeitos bem diferentes |
| `trama` | Trama (Nanda Quaresma) | taquara | Netrunner de uma cidade cyberpunk brasileira, clima Cyberpunk 2077/Edgerunners, romance trágico |
| `sibila` | Sibila | hiato | Dona da Casa no Hiato, dark fantasy e horror psicológico, tudo tem Preço |

Personagem de grupo: o narrador interpreta todo o elenco e marca quem fala com **Nome:** (ver `build_system_prompt`).
Cada integrante fica em `cast` (id, nome, apelidos, relação inicial) e tem a própria relação com o jogador nos modos
médio e completo (`RPGState.cast_relations`). A mensagem do jogador mexe na relação de quem foi citada pelo nome ou apelido,
ou, se ninguém foi citada, de quem falou por último. Isso vai para o prompt e para a barra "Elenco" da lateral.
Conteúdo sexual explícito não é escrito aqui: as fichas definem desejo, ritmo e a instrução de narrar a intimidade;
o texto explícito vem do modelo local.

Estilo dos textos: nomes que soam como lugar e pessoa, não como tradução literal; detalhes concretos em vez de rótulos
("tsundere", "kuudere"); sem frases de manual. Ao criar personagens novos, siga isso.

---

## Decisões de Design Importantes

1. **Sem frameworks frontend**: módulos ES nativos, 100% offline, sem CDN e sem build.
2. **Streaming via SSE** com um objeto JSON por evento (nada de sentinelas no texto).
3. **GPU de 6 GB (GTX 1660)**: LLM e Stable Diffusion não cabem juntos, então se alternam.
   Padrão `num_ctx=4096` para um 7B em Q4. Dica: `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0`.
4. **Ollama local**: o modelo é escolhido nas Configurações. Para roleplay, 7B a 12B de RP/chat rendem
   mais que o `deepseek-r1:7b` (modelo de raciocínio, gasta tokens "pensando").
5. **Servidor só em 127.0.0.1 e sem CORS aberto**.

---

## O que Está Pendente

- [ ] Expressões do personagem (variações de retrato via img2img)
- [ ] Inventário editável pela interface e itens dados pela história
- [ ] Sons e música ambiente
- [ ] Piper foi escrito mas só testado com binário falso: validar com o Piper real no Windows

---

## Problemas Conhecidos / Avisos

- `venv/` não está no repositório, precisa recriar com `pip install -r requirements.txt`
- Sessões ficam em `data/sessions/` (gitignored), sincronizar via Proton Drive se necessário
- Imagens geradas ficam em `frontend/static/images/characters/` (gitignored)

---

## Recuperação de Contexto (Para IA)

Se o chat ficar muito longo e precisar compactar:
1. Ler este arquivo (AI_CONTEXT.md)
2. Ler DEVELOPMENT.md para histórico detalhado
3. Verificar arquivos modificados recentemente com `git log --oneline -10`
4. Rodar `python -m py_compile backend/main.py` para checar sintaxe

---

## GitHub

Repositório: `https://github.com/GabbeVestigium/rpg-ia` (privado)
Usuário: GabbeVestigium
Branch principal: main

Para clonar no outro PC:
```powershell
git clone https://github.com/GabbeVestigium/rpg-ia.git
cd rpg-ia
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Hardware do Usuário (PC Principal)

- GPU: NVIDIA GeForce GTX 1660 (6GB VRAM)
- RAM: 16GB
- OS: Windows 11
- Shell: PowerShell 7
