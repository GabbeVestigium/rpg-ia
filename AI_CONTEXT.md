# AI_CONTEXT.md — Leia isso primeiro!

Este arquivo é para a IA que vai trabalhar neste projeto.
Leia antes de qualquer coisa.

---

## Sobre o Projeto

**RPG-IA** é um sistema de roleplay local com interface estilo visual novel.
100% offline, sem censura, conteúdo adulto (+18) permitido.

**Stack:**
- Backend: Python + FastAPI (porta 8000)
- LLM: Ollama rodando local com modelo `deepseek-r1:7b` (porta 11434)
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
├── AI_CONTEXT.md              # Este arquivo
├── DEVELOPMENT.md             # Histórico completo de desenvolvimento
├── INSTALL_SD.md              # Guia de instalação do Stable Diffusion
├── requirements.txt           # Dependências Python
├── 🎮 Iniciar RPG-IA.bat      # Launcher
│
├── backend/
│   ├── main.py                # FastAPI: rotas REST + endpoints SD
│   ├── sd_client.py           # Integração com Stable Diffusion
│   ├── rpg_engine.py          # Engine RPG (d20, XP, combate)
│   ├── rpg_models.py          # Modelos Pydantic
│   ├── session_manager.py     # Gerenciamento de sessões
│   ├── character_manager.py   # Carregamento de personagens/mundos
│   ├── ollama_client.py       # Cliente Ollama (streaming SSE)
│   ├── config.py              # Configurações (HOST, PORT, paths)
│   └── models.py              # Modelos base (ChatRequest, etc.)
│
├── frontend/
│   ├── index.html             # Interface principal (3 colunas)
│   └── static/
│       ├── css/style.css      # Tema dark cyberpunk
│       ├── js/
│       │   ├── app.js         # Lógica principal do frontend
│       │   └── dice.js        # Animação dado D20 com arabesco
│       └── images/characters/ # PNGs gerados pelo SD (gitignored)
│
└── data/
    ├── characters/            # JSONs dos personagens
    ├── worlds/                # JSONs dos mundos
    └── sessions/              # Histórico de conversas (gitignored)
```

---

## Endpoints da API

```
GET  /                              → Frontend (index.html)
GET  /api/status                    → Status Ollama
GET  /api/characters                → Lista personagens
GET  /api/worlds                    → Lista mundos
GET  /api/rpg/options               → Raças e classes disponíveis
POST /api/session/new               → Criar sessão
POST /api/chat                      → Chat (streaming SSE)
POST /api/player/create             → Criar personagem jogador
POST /api/roll                      → Rolar dado manualmente
POST /api/quest/add                 → Adicionar quest
PATCH /api/quest/complete           → Completar quest

GET  /api/sd/status                 → Verifica SD disponível
POST /api/sd/generate-portrait      → Gera retrato via SD
GET  /api/sd/check-portrait/{id}    → Verifica se retrato existe
DELETE /api/sd/delete-portrait/{id} → Deleta retrato (forçar regeneração)
```

---

## Features Implementadas

### Interface
- Layout 3 colunas com painéis redimensionáveis (drag)
- Tema dark cyberpunk (CSS custom properties)
- Animação dado D20 com textura arabesco (dice.js)
- Indicador de typing
- Auto-scroll do chat
- Botão "✨ Gerar Retrato com IA" (aparece quando SD disponível)
- Loading overlay durante geração de imagem

### RPG
- 3 modos de jogo: Completo (d20 automático), Intermediário, Narrativo
- Sistema d20 com modificadores por atributo
- XP e level up automático
- Detecção de ações de risco no texto
- Sistema de quests
- Relacionamento dinâmico (NPC approval)

### Imagens (Stable Diffusion)
- Cache automático (não regenera se PNG já existe)
- Prompts gerados automaticamente por raça/classe
- NSFW habilitado por padrão (nsfw=True)
- Configurado para GTX 1660 (4GB VRAM): 512x768, 25 steps, DPM++ 2M Karras
- Precisa Automatic1111 rodando com: `--api --medvram --xformers --no-half-vae`

---

## Personagens Existentes

| ID | Nome | Mundo | Descrição |
|----|------|-------|-----------|
| `lyra` | Lyra Ashveil | eldoria | Elfa maga renegada, sarcástica, ex-Ordem dos Sete Selos |
| `morrigan` | Morrigan | abismo | Entidade do Abismo em forma humana, misteriosa |
| `vex` | Vex-7 | neon-city | Hacker de elite cyberpunk com implantes |

---

## Decisões de Design Importantes

1. **Sem frameworks frontend** — Zero overhead, 100% offline, sem CDN
2. **Streaming via SSE** — Respostas em tempo real sem WebSocket
3. **NSFW habilitado** — Projeto de uso pessoal, sem filtros
4. **Cache de imagens** — PNG salvo em disco, não regenera automaticamente
5. **Ollama local** — deepseek-r1:7b, privacidade total, sem API keys

---

## O que Está Pendente (Próximas Features)

### Curto Prazo
- [ ] Carregamento de sessões antigas na UI
- [ ] Stats funcionais (HP/Mana integrados ao engine)
- [ ] Botão "Regenerar Retrato" (force_regenerate=True)

### Médio Prazo
- [ ] Sistema de inventário funcional
- [ ] Expressões de personagens (happy, angry, sad, etc.)
- [ ] Sons e músicas ambiente

### Longo Prazo
- [ ] Integração Proton Drive para sync de sessões
- [ ] Batch generation de retratos
- [ ] Sistema de expressões via img2img

---

## Problemas Conhecidos / Avisos

- Arquivo `backend/main (# Edit conflict 2026-09-28 bueqclC #).py` pode ser deletado (é conflito antigo do Kiro)
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

- GPU: NVIDIA GeForce GTX 1660 (4GB VRAM)
- RAM: 16GB
- OS: Windows 11
- Shell: PowerShell 7
