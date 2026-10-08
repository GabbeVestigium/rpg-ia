"""Rotas de sessão, jogador (RPG), quests e rolagem de dados."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.character_manager import load_character
from backend.models import MessageRole
from backend.rpg_engine import create_player, get_roll_modifier, roll_d20
from backend.rpg_models import (
    CLASSES, RACES, AddQuestRequest, CreatePlayerRequest, GameMode, Quest, QuestStatus,
)
from backend.session_manager import (
    add_message, create_session, delete_session, get_rpg_state, list_sessions,
    load_session, save_rpg_state, session_lock,
)

router = APIRouter(prefix="/api", tags=["sessions"])


def _get_session(session_id: str):
    session = load_session(session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")
    return session


# ─── OPÇÕES ───────────────────────────────────────────────────────────────────

@router.get("/rpg/options")
async def rpg_options():
    """Raças, classes e modos disponíveis para criação de personagem."""
    return {
        "races": [
            {"id": k, "name": k.title(), "trait": v["trait"], "desc": v["desc"],
             "bonus": v["bonus"], "penalty": v.get("penalty", {})}
            for k, v in RACES.items()
        ],
        "classes": [
            {"id": k, "name": k.title(), "hp_base": v["hp_base"], "hit_die": v["hit_die"],
             "primary": v["primary"], "saves": v["saves"], "desc": v["desc"]}
            for k, v in CLASSES.items()
        ],
        "modes": [
            {"id": "narrative", "name": "Narrativo",
             "description": "Pura história. Sem mecânicas, sem números. Total liberdade narrativa."},
            {"id": "medium", "name": "Médio",
             "description": "Escolha raça e classe. Tracker de relacionamento e inventário simples."},
            {"id": "full", "name": "Completo",
             "description": "Sistema completo: atributos, HP, XP, nível, quests e rolagem de dados."},
        ],
    }


# ─── SESSÕES ──────────────────────────────────────────────────────────────────

class NewSessionRequestV2(BaseModel):
    character_id: str
    game_mode: str = "narrative"


@router.post("/session/new")
async def new_session(req: NewSessionRequestV2):
    character = load_character(req.character_id)
    if not character:
        raise HTTPException(404, f"Personagem '{req.character_id}' não encontrado")
    try:
        mode = GameMode(req.game_mode)
    except ValueError:
        mode = GameMode.NARRATIVE

    session = create_session(req.character_id, mode)
    add_message(session, MessageRole.ASSISTANT, character.first_message)
    return {
        "session_id": session.session_id,
        "game_mode": mode.value,
        "character": {
            "id": character.id, "name": character.name, "world_id": character.world_id,
            "avatar_emoji": character.avatar_emoji, "scenario": character.scenario,
            "first_message": character.first_message,
        },
    }


@router.get("/sessions")
async def get_sessions():
    result = []
    for s in list_sessions():
        char = load_character(s["character_id"])
        s["character_name"] = char.name if char else s["character_id"].title()
        s["character_emoji"] = char.avatar_emoji if char else "👤"
        result.append(s)
    return result


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    session = _get_session(session_id)
    character = load_character(session.character_id)
    rpg = get_rpg_state(session)
    return {
        "session_id": session.session_id,
        "character_id": session.character_id,
        "character_name": character.name if character else "?",
        "world_id": character.world_id if character else "",
        "avatar_emoji": character.avatar_emoji if character else "👤",
        "scenario": character.scenario if character else "",
        "game_mode": rpg.mode.value,
        "history": [{"role": m.role.value, "content": m.content} for m in session.history],
        "images": [i.model_dump() for i in session.images],
        "has_summary": bool(session.summary),
        "rpg_state": rpg.model_dump(mode="json") if rpg.player else None,
    }


@router.get("/session/{session_id}/memory")
async def get_memory(session_id: str):
    session = _get_session(session_id)
    return {"summary": session.summary, "summarized_upto": session.summarized_upto,
            "total_messages": len(session.history)}


class MemoryUpdate(BaseModel):
    summary: str


@router.put("/session/{session_id}/memory")
async def put_memory(session_id: str, body: MemoryUpdate):
    """Deixa o jogador corrigir ou escrever a memória à mão."""
    from backend.session_manager import save_session
    async with session_lock(session_id):
        session = _get_session(session_id)
        session.summary = body.summary.strip()[:4000]
        save_session(session)
    return {"ok": True}


@router.delete("/session/{session_id}")
async def remove_session(session_id: str):
    if not delete_session(session_id):
        raise HTTPException(404, "Sessão não encontrada")
    return {"deleted": True}


# ─── JOGADOR ──────────────────────────────────────────────────────────────────

@router.post("/player/create")
async def create_player_endpoint(req: CreatePlayerRequest):
    """Modo médio: nome, raça e classe. Modo completo: também os atributos."""
    session = _get_session(req.session_id)
    rpg = get_rpg_state(session)
    rpg.player = create_player(
        name=req.name, race=req.race, char_class=req.char_class, mode=req.mode,
        custom_attributes=req.attributes, age=req.age, appearance=req.appearance,
    )
    rpg.mode = req.mode
    save_rpg_state(session, rpg)
    return {"success": True, "player": rpg.player.model_dump(mode="json"), "mode": req.mode.value}


@router.get("/player/{session_id}")
async def get_player(session_id: str):
    rpg = get_rpg_state(_get_session(session_id))
    return {
        "mode": rpg.mode.value,
        "player": rpg.player.model_dump(mode="json") if rpg.player else None,
        "event_log": rpg.event_log[-5:],
    }


# ─── QUESTS ───────────────────────────────────────────────────────────────────

@router.post("/quest/add")
async def add_quest(req: AddQuestRequest):
    session = _get_session(req.session_id)
    rpg = get_rpg_state(session)
    if not rpg.player:
        raise HTTPException(400, "Personagem jogador não criado")
    quest = Quest(
        id=uuid.uuid4().hex[:8], title=req.title, description=req.description,
        objectives=req.objectives, reward_xp=req.reward_xp, reward_gold=req.reward_gold,
    )
    rpg.player.quests.append(quest)
    rpg.event_log.append(f"Nova quest recebida: {req.title}")
    save_rpg_state(session, rpg)
    return {"quest_id": quest.id, "quest": quest.model_dump(mode="json")}


class CompleteQuestRequest(BaseModel):
    session_id: str
    quest_id: str


@router.patch("/quest/complete")
async def complete_quest(req: CompleteQuestRequest):
    session = _get_session(req.session_id)
    rpg = get_rpg_state(session)
    if not rpg.player:
        raise HTTPException(400, "Personagem não criado")
    for quest in rpg.player.quests:
        if quest.id == req.quest_id:
            quest.status = QuestStatus.COMPLETED
            leveled_up = rpg.player.add_xp(quest.reward_xp)
            rpg.player.inventory.gold += quest.reward_gold
            msg = f"Quest '{quest.title}' completada! +{quest.reward_xp} XP"
            if leveled_up:
                msg += f" | LEVEL UP! Nível {rpg.player.level}!"
            rpg.event_log.append(msg)
            save_rpg_state(session, rpg)
            return {"success": True, "message": msg, "leveled_up": leveled_up}
    raise HTTPException(404, "Quest não encontrada")


# ─── ROLAGEM MANUAL ───────────────────────────────────────────────────────────

class RollRequest(BaseModel):
    session_id: str
    attribute: Optional[str] = None


@router.post("/roll")
async def manual_roll(req: RollRequest):
    session = _get_session(req.session_id)
    rpg = get_rpg_state(session)
    modifier = get_roll_modifier(rpg.player, req.attribute) if rpg.player and req.attribute else 0
    result = roll_d20(modifier)
    attr = f" ({req.attribute})" if req.attribute else ""
    rpg.event_log.append(
        f"Rolagem{attr}: {result['natural']} + {modifier} = {result['final']} [{result['label']}]"
    )
    save_rpg_state(session, rpg)
    return result
