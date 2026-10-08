"""
Gerenciador de sessões: salva histórico, estado RPG, memória e cenas em disco.

Cada sessão é um JSON em data/sessions/. O histórico completo fica salvo (a tela
mostra tudo ao retomar), e o que vai para o modelo é uma janela das últimas
mensagens mais o resumo da história anterior (ver memory.py).
"""

import os
import uuid
from typing import List, Optional

from backend.config import SESSIONS_DIR
from backend.models import Message, MessageRole, SceneImage, SessionData
from backend.rpg_models import GameMode, RPGState
from backend.storage import is_safe_id, read_json, write_json_atomic


def _session_path(session_id: str) -> str:
    if not is_safe_id(session_id):
        raise ValueError("session_id inválido")
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def create_session(character_id: str, mode: GameMode = GameMode.NARRATIVE) -> SessionData:
    """Cria uma nova sessão com modo de jogo definido."""
    session = SessionData(session_id=uuid.uuid4().hex[:8], character_id=character_id)
    session.rpg_state = RPGState(mode=mode)
    save_session(session)
    return session


def load_session(session_id: str) -> Optional[SessionData]:
    """Carrega sessão do disco. Retorna None se não existir ou id inválido."""
    if not is_safe_id(session_id):
        return None
    data = read_json(_session_path(session_id))
    if not isinstance(data, dict):
        return None

    try:
        session = SessionData(
            session_id=data["session_id"],
            character_id=data["character_id"],
            history=[Message(**m) for m in data.get("history", [])],
            summary=data.get("summary", ""),
            summarized_upto=data.get("summarized_upto", 0),
            images=[SceneImage(**i) for i in data.get("images", [])],
        )
    except (KeyError, TypeError, ValueError):
        return None

    try:
        session.rpg_state = RPGState(**data["rpg_state"]) if data.get("rpg_state") else RPGState()
    except Exception:
        session.rpg_state = RPGState()
    return session


def save_session(session: SessionData) -> None:
    """Salva a sessão de forma atômica."""
    write_json_atomic(_session_path(session.session_id), {
        "session_id":      session.session_id,
        "character_id":    session.character_id,
        "history":         [m.model_dump(mode="json") for m in session.history],
        "rpg_state":       session.rpg_state.model_dump(mode="json") if session.rpg_state else None,
        "summary":         session.summary,
        "summarized_upto": session.summarized_upto,
        "images":          [i.model_dump(mode="json") for i in session.images],
    })


def delete_session(session_id: str) -> bool:
    if not is_safe_id(session_id):
        return False
    path = _session_path(session_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def add_message(session: SessionData, role: MessageRole, content: str) -> SessionData:
    """Acrescenta uma mensagem e salva. O histórico não é truncado em disco."""
    session.history.append(Message(role=role, content=content))
    save_session(session)
    return session


def pop_last_exchange(session: SessionData) -> Optional[str]:
    """
    Remove a última resposta do personagem (e a mensagem do jogador que a gerou,
    se for o caso) e devolve o texto do jogador, para regenerar ou refazer.
    Nunca remove a mensagem de abertura do personagem.
    """
    if len(session.history) <= 1:
        return None
    if session.history[-1].role == MessageRole.ASSISTANT:
        session.history.pop()
    user_text = None
    if len(session.history) > 1 and session.history[-1].role == MessageRole.USER:
        user_text = session.history.pop().content
    session.summarized_upto = min(session.summarized_upto, len(session.history))
    session.images = [i for i in session.images if i.at <= len(session.history)]
    save_session(session)
    return user_text


def get_rpg_state(session: SessionData) -> RPGState:
    """Retorna o estado RPG da sessão, criando um vazio se não existir."""
    if not session.rpg_state:
        session.rpg_state = RPGState()
    return session.rpg_state


def save_rpg_state(session: SessionData, state: RPGState) -> SessionData:
    session.rpg_state = state
    save_session(session)
    return session


def list_sessions(character_id: Optional[str] = None) -> List[dict]:
    """Lista as sessões com info resumida, mais recentes primeiro."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    sessions = []
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        data = read_json(path)
        if not isinstance(data, dict) or "session_id" not in data:
            continue
        if character_id is not None and data.get("character_id") != character_id:
            continue
        rpg = data.get("rpg_state") or {}
        player = rpg.get("player") or {}
        sessions.append({
            "session_id":    data["session_id"],
            "character_id":  data.get("character_id", ""),
            "message_count": len(data.get("history", [])),
            "mode":          rpg.get("mode", "narrative"),
            "player_name":   player.get("name", ""),
            "player_level":  player.get("level", 1),
            "_mtime":        os.path.getmtime(path),
        })
    sessions.sort(key=lambda s: s["_mtime"], reverse=True)
    for s in sessions:
        del s["_mtime"]
    return sessions


def pop_last_assistant(session: SessionData) -> bool:
    """Remove a última resposta do personagem (para regenerar). Preserva a abertura."""
    if len(session.history) > 1 and session.history[-1].role == MessageRole.ASSISTANT:
        session.history.pop()
        session.summarized_upto = min(session.summarized_upto, len(session.history))
        session.images = [i for i in session.images if i.at <= len(session.history)]
        save_session(session)
        return True
    return False


# Um lock por sessão: impede duas respostas (ou um resumo) escrevendo ao mesmo tempo.
_locks: dict = {}


def session_lock(session_id: str):
    import asyncio
    return _locks.setdefault(session_id, asyncio.Lock())
