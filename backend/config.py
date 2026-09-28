"""
Config central do RPG IA.
Tudo que pode mudar fica aqui — modelo, porta, limites de memória.
"""

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "deepseek-r1:7b"

# Servidor
HOST = "127.0.0.1"
PORT = 8000

# Memória de conversa — quantas mensagens o modelo "lembra" por sessão
# Com 4GB VRAM e deepseek-r1:7b, 20 turnos é seguro sem overflow
MAX_HISTORY_TURNS = 20

# Diretórios de dados (relativos à raiz do projeto)
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CHARACTERS_DIR = os.path.join(DATA_DIR, "characters")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
