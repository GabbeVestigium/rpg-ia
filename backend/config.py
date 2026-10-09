"""
Config central do RPG IA.

Valores fixos de infraestrutura (portas, pastas, URLs) ficam aqui e podem ser
sobrescritos por variável de ambiente. Preferências que você muda jogando
(modelo, temperatura, voz...) ficam em settings_manager.py e na tela de
Configurações, salvas em data/settings.json.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Servidor
HOST = os.environ.get("RPG_HOST", "127.0.0.1")
PORT = int(os.environ.get("RPG_PORT", "8000"))

# Ollama
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Stable Diffusion (Automatic1111 com --api)
SD_API_URL = os.environ.get("SD_API_URL", "http://127.0.0.1:7860")

# Diretórios de dados
DATA_DIR = os.environ.get("RPG_DATA_DIR", os.path.join(BASE_DIR, "data"))
CHARACTERS_DIR = os.path.join(DATA_DIR, "characters")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
SCENES_DIR = os.path.join(DATA_DIR, "scenes")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PROFILE_FILE = os.path.join(DATA_DIR, "profile.json")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
PORTRAITS_DIR = os.environ.get("RPG_PORTRAITS_DIR", os.path.join(FRONTEND_DIR, "static", "images", "characters"))
