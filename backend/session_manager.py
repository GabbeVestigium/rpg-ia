"""
Gerenciador de sessões — salva histórico + estado RPG em disco.

Cada sessão agora tem dois componentes:
1. history: lista de mensagens (chat)
2. rpg_state: estado do jogo (player, modo, inventário, quests, etc.)

Ambos ficam no mesmo arquivo JSON em data/sessions/.
"""

import json
import os
import uuid
from typing import Optional
from backend.models import SessionData, Message, MessageRole
from backend.rpg_models import RPGState, GameMode
from backend.config import SESSIONS_DIR, MAX_HISTORY_TURNS


def _session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def create_session(character_id: str, mode: GameMode = GameMode.NARRATIVE) -> SessionData:
    """Cria uma nova sessão com modo de jogo definido."""
    session_id = str(uuid.uuid4())[:8]
    session = SessionData(session_id=session_id, character_id=character_id)
    # Inicializa o estado RPG vazio com o modo escolhido
    session.rpg_state = RPGState(mode=mode)
    save_session(session)
    return session


def load_session(session_id: str) -> Optional[SessionData]:
    """Carrega sessão do disco. Retorna None se não existir."""
    path = _session_path(session_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    session = SessionData(
        session_id=data["session_id"],
        character_id=data["character_id"],
        history=[Message(**m) for m in data.get("history", [])]
    )

    # Carrega estado RPG se existir
    if "rpg_state" in data and data["rpg_state"]:
        try:
            session.rpg_state = RPGState(**data["rpg_state"])
        except Exception:
            session.rpg_state = RPGState()
    else:
        session.rpg_state = RPGState()

    return session


def save_session(session: SessionData) -> None:
    """
    Salva sessão em disco de forma atômica.
    Escreve em arquivo temporário e depois faz rename — garante que
    se a escrita falhar no meio, o arquivo original não é corrompido.
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path     = _session_path(session.session_id)
    tmp_path = path + ".tmp"

    data = {
        "session_id":   session.session_id,
        "character_id": session.character_id,
        "history":      [m.model_dump() for m in session.history],
        "rpg_state":    session.rpg_state.model_dump() if session.rpg_state else None
    }

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)  # atômico no mesmo filesystem
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def add_message(session: SessionData, role: MessageRole, content: str) -> SessionData:
    """
    Adiciona mensagem ao histórico com truncamento inteligente.
    Preserva sempre as primeiras 2 mensagens (first_message do personagem)
    e as últimas MAX_HISTORY_TURNS*2 mensagens.
    """
    session.history.append(Message(role=role, content=content))

    max_messages = MAX_HISTORY_TURNS * 2
    if len(session.history) > max_messages + 2:
        # Preserva as 2 primeiras (contexto inicial) + as mais recentes
        session.history = session.history[:2] + session.history[-(max_messages):]

    save_session(session)
    return session


def get_rpg_state(session: SessionData) -> RPGState:
    """Retorna o estado RPG da sessão, criando um vazio se não existir."""
    if not session.rpg_state:
        session.rpg_state = RPGState()
    return session.rpg_state


def save_rpg_state(session: SessionData, state: RPGState) -> SessionData:
    """Atualiza o estado RPG e salva em disco."""
    session.rpg_state = state
    save_session(session)
    return session


def list_sessions(character_id: Optional[str] = None):
    """Lista todas as sessões com info resumida incluindo modo RPG e nome do personagem."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    sessions = []
    for fname in os.listdir(SESSIONS_DIR):
        if fname.endswith(".json"):
            path = os.path.join(SESSIONS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue  # ignora JSONs corrompidos silenciosamente
            if character_id is None or data.get("character_id") == character_id:
                rpg    = data.get("rpg_state", {}) or {}
                player = rpg.get("player") or {}
                sessions.append({
                    "session_id":      data["session_id"],
                    "character_id":    data["character_id"],
                    "message_count":   len(data.get("history", [])),
                    "mode":            rpg.get("mode", "narrative"),
                    "player_name":     player.get("name", ""),
                    "player_level":    player.get("level", 1),
                })
    return sessions
