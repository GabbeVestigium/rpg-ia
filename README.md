# ⚔️ RPG IA

IA de roleplay local, sem censura, estilo visual novel. Roda 100% no seu PC.

## Requisitos
- Python 3.12+
- Ollama com `deepseek-r1:7b` instalado

## Como rodar

Abra um terminal PowerShell na pasta do projeto e rode:

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

O script vai:
1. Criar o ambiente virtual Python automaticamente
2. Instalar as dependências
3. Verificar/iniciar o Ollama
4. Subir o servidor em http://127.0.0.1:8000
5. Abrir o browser automaticamente

## Adicionar personagens

Crie um arquivo `.json` em `data/characters/` seguindo o modelo dos existentes.
Crie o mundo correspondente em `data/worlds/` se for um mundo novo.

## Estrutura
```
rpg-ia/
├── backend/          # Servidor FastAPI
├── frontend/         # Interface web
├── data/
│   ├── characters/   # Personagens (JSON)
│   ├── worlds/       # Mundos (JSON)
│   └── sessions/     # Histórico de conversas (auto-gerado)
├── requirements.txt
└── start.ps1         # Script de inicialização
```
