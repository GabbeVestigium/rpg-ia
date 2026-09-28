"""
Main — ponto de entrada do servidor FastAPI.

Rotas novas nesta versão:
- POST /api/session/new     agora aceita game_mode
- POST /api/player/create   cria o personagem jogador
- GET  /api/player/{id}     retorna estado RPG atual
- POST /api/roll            força uma rolagem manual
- GET  /api/rpg/options     retorna raças, classes disponíveis
- POST /api/quest/add       adiciona quest à sessão
- PATCH /api/quest/complete completa uma quest
"""

import os
import sys
import json as _json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

from backend.models import ChatRequest, NewSessionRequest, MessageRole
from backend.session_manager import (
    create_session, load_session, add_message,
    list_sessions, save_rpg_state, get_rpg_state
)
from backend.character_manager import load_character, load_world, list_characters, list_worlds
from backend.ollama_client import stream_chat, build_system_prompt, check_ollama
from backend.rpg_models import (
    GameMode, RPGState, CreatePlayerRequest, AddQuestRequest,
    Quest, QuestStatus, RACES, CLASSES
)
from backend.rpg_engine import (
    create_player, detect_risk_action, get_roll_modifier,
    roll_d20, calculate_xp_reward, auto_relationship_delta
)
from backend.config import FRONTEND_DIR, SESSIONS_DIR, DATA_DIR
from backend.sd_client import (
    check_sd_available, generate_character_portrait,
    build_character_prompt, generate_image
)

app = FastAPI(title="RPG IA", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
app.mount("/images", StaticFiles(directory=os.path.join(DATA_DIR, "characters", "images")), name="images")


# ─── FRONTEND ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─── STATUS ───────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    return await check_ollama()


# ─── PERSONAGENS E MUNDOS ─────────────────────────────────────────────────────

@app.get("/api/characters")
async def get_characters():
    return list_characters()


@app.get("/api/worlds")
async def get_worlds():
    return list_worlds()


# ─── OPÇÕES RPG ───────────────────────────────────────────────────────────────

@app.get("/api/rpg/options")
async def rpg_options():
    """Retorna raças e classes disponíveis para criação de personagem."""
    return {
        "races": [
            {
                "id": k,
                "name": k.title(),
                "trait": v["trait"],
                "desc": v["desc"],
                "bonus": v["bonus"],
                "penalty": v.get("penalty", {})
            }
            for k, v in RACES.items()
        ],
        "classes": [
            {
                "id": k,
                "name": k.title(),
                "hp_base": v["hp_base"],
                "hit_die": v["hit_die"],
                "primary": v["primary"],
                "saves": v["saves"],
                "desc": v["desc"]
            }
            for k, v in CLASSES.items()
        ],
        "modes": [
            {"id": "narrative", "name": "Narrativo",
             "description": "Pura história. Sem mecânicas, sem números. Total liberdade narrativa."},
            {"id": "medium",    "name": "Médio",
             "description": "Escolha raça e classe. Tracker de relacionamento e inventário simples."},
            {"id": "full",      "name": "Completo",
             "description": "Sistema completo: atributos, HP, XP, nível, quests e rolagem de dados."},
        ]
    }


# ─── SESSÕES ──────────────────────────────────────────────────────────────────

class NewSessionRequestV2(BaseModel):
    character_id: str
    game_mode: str = "narrative"


@app.post("/api/session/new")
async def new_session(req: NewSessionRequestV2):
    """Cria nova sessão com modo de jogo definido."""
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
            "id": character.id,
            "name": character.name,
            "avatar_emoji": character.avatar_emoji,
            "scenario": character.scenario,
            "first_message": character.first_message
        }
    }


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = load_session(session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    character = load_character(session.character_id)
    rpg = get_rpg_state(session)

    return {
        "session_id": session.session_id,
        "character_id": session.character_id,
        "character_name": character.name if character else "?",
        "avatar_emoji": character.avatar_emoji if character else "👤",
        "game_mode": rpg.mode.value,
        "history": [{"role": m.role, "content": m.content} for m in session.history],
        "rpg_state": rpg.model_dump() if rpg.player else None
    }


@app.get("/api/sessions")
async def get_sessions():
    """Lista todas as sessões salvas com nome display do personagem."""
    raw = list_sessions()
    result = []
    for s in raw:
        char = load_character(s["character_id"])
        s["character_name"]  = char.name          if char else s["character_id"].title()
        s["character_emoji"] = char.avatar_emoji   if char else "👤"
        result.append(s)
    return result


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(path):
        os.remove(path)
        return {"deleted": True}
    raise HTTPException(404, "Sessão não encontrada")


# ─── CRIAÇÃO DE PERSONAGEM JOGADOR ────────────────────────────────────────────

@app.post("/api/player/create")
async def create_player_endpoint(req: CreatePlayerRequest):
    """
    Cria o personagem jogador e associa à sessão.
    
    Modo MEDIUM: só name, race, char_class.
    Modo FULL: também recebe attributes dict {STR, DEX, CON, INT, WIS, CHA}.
    """
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    rpg = get_rpg_state(session)

    player = create_player(
        name=req.name,
        race=req.race,
        char_class=req.char_class,
        mode=req.mode,
        custom_attributes=req.attributes,
        age=req.age,
        appearance=req.appearance
    )

    rpg.player = player
    rpg.mode = req.mode
    save_rpg_state(session, rpg)

    return {
        "success": True,
        "player": player.model_dump(),
        "mode": req.mode.value
    }


@app.get("/api/player/{session_id}")
async def get_player(session_id: str):
    """Retorna o estado RPG completo da sessão."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    rpg = get_rpg_state(session)
    return {
        "mode": rpg.mode.value,
        "player": rpg.player.model_dump() if rpg.player else None,
        "event_log": rpg.event_log[-5:]  # últimos 5 eventos
    }


# ─── QUESTS ───────────────────────────────────────────────────────────────────

@app.post("/api/quest/add")
async def add_quest(req: AddQuestRequest):
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    rpg = get_rpg_state(session)
    if not rpg.player:
        raise HTTPException(400, "Personagem jogador não criado")

    import uuid
    quest = Quest(
        id=str(uuid.uuid4())[:8],
        title=req.title,
        description=req.description,
        objectives=req.objectives,
        reward_xp=req.reward_xp,
        reward_gold=req.reward_gold
    )
    rpg.player.quests.append(quest)
    rpg.event_log.append(f"Nova quest recebida: {req.title}")
    save_rpg_state(session, rpg)

    return {"quest_id": quest.id, "quest": quest.model_dump()}


class CompleteQuestRequest(BaseModel):
    session_id: str
    quest_id: str


@app.patch("/api/quest/complete")
async def complete_quest(req: CompleteQuestRequest):
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

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
    attribute: Optional[str] = None  # STR, DEX, etc.


@app.post("/api/roll")
async def manual_roll(req: RollRequest):
    """Rolagem manual de d20 com modifier do atributo."""
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    rpg = get_rpg_state(session)
    modifier = 0
    if rpg.player and req.attribute:
        modifier = get_roll_modifier(rpg.player, req.attribute)

    result = roll_d20(modifier)

    # Registra no log
    attr_str = f" ({req.attribute})" if req.attribute else ""
    rpg.event_log.append(
        f"Rolagem{attr_str}: {result['natural']} + {modifier} = {result['final']} [{result['label']}]"
    )
    save_rpg_state(session, rpg)

    return result


# ─── CHAT ─────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Chat com detecção automática de ações de risco.
    
    Fluxo:
    1. Detecta se a mensagem contém ação de risco
    2. Se sim e modo FULL, rola d20 automaticamente
    3. Injeta resultado da rolagem na mensagem antes de enviar ao modelo
    4. Stream da resposta com contexto RPG completo
    """
    session = load_session(req.session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")

    character = load_character(req.character_id)
    if not character:
        raise HTTPException(404, "Personagem não encontrado")

    world = load_world(character.world_id) if character.world_id else None
    rpg = get_rpg_state(session)

    # Detecção automática de ação de risco (só modo FULL)
    roll_result = None
    roll_event = None
    message_to_send = req.message

    if rpg.mode == GameMode.FULL and rpg.player:
        risk_attr = detect_risk_action(req.message)
        if risk_attr:
            modifier = get_roll_modifier(rpg.player, risk_attr)
            roll_result = roll_d20(modifier)

            # Injeta o resultado no contexto da mensagem
            roll_event = (
                f"[ROLAGEM AUTOMÁTICA — {risk_attr}: "
                f"d20={roll_result['natural']} + {modifier} = {roll_result['final']} | "
                f"{roll_result['label']}]"
            )
            message_to_send = f"{req.message}\n\n{roll_event}"

            # XP pela ação
            xp_gain = calculate_xp_reward(roll_result["outcome"])
            leveled_up = False
            if xp_gain > 0:
                leveled_up = rpg.player.add_xp(xp_gain)

            log_msg = f"Rolagem {risk_attr}: {roll_result['natural']}+{modifier}={roll_result['final']} [{roll_result['label']}]"
            if xp_gain:
                log_msg += f" +{xp_gain}XP"
            if leveled_up:
                log_msg += f" | LEVEL UP Nível {rpg.player.level}!"
            rpg.event_log.append(log_msg)

    # Ajuste automático de relacionamento
    if rpg.player and rpg.mode != GameMode.NARRATIVE:
        delta = auto_relationship_delta(req.message)
        if delta != 0:
            rpg.player.relationship.set_score(
                rpg.player.relationship.score + delta
            )

    # Limita event_log a 50 entradas para evitar crescimento ilimitado
    if len(rpg.event_log) > 50:
        rpg.event_log = rpg.event_log[-50:]

    save_rpg_state(session, rpg)

    # Monta system prompt com estado RPG atual
    system_prompt = build_system_prompt(character, world, rpg)
    session = add_message(session, MessageRole.USER, message_to_send)

    async def generate():
        full_response = ""
        stream_complete = False  # flag para distinguir stream completo de desconexão

        # Envia evento de rolagem como primeiro token SSE se houver
        if roll_result:
            roll_json = _json.dumps({
                "type": "roll",
                "result": roll_result,
                "event": roll_event
            })
            yield f"data: __ROLL__{roll_json}\n\n"

        try:
            async for token in stream_chat(session.history, system_prompt):
                full_response += token
                yield f"data: {token}\n\n"
            stream_complete = True  # chegou aqui = stream terminou normalmente
        except Exception:
            stream_complete = False  # erro ou desconexão
        finally:
            # Só salva se a resposta for completa (>= 20 chars) e o stream terminou
            # Evita salvar frases truncadas quando o cliente desconecta mid-stream
            clean = full_response.replace("\\n", "\n")
            if clean and stream_complete and len(clean) >= 20:
                add_message(session, MessageRole.ASSISTANT, clean)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ─── STABLE DIFFUSION ENDPOINTS ──────────────────────────────────────────────

class GeneratePortraitRequest(BaseModel):
    character_id: str
    name: str
    race: str
    char_class: str
    gender: str = "female"
    description: Optional[str] = None
    nsfw: bool = False
    force_regenerate: bool = False


@app.get("/api/sd/status")
async def sd_status():
    """Verifica se Stable Diffusion está disponível."""
    available = check_sd_available()
    return {
        "available": available,
        "message": "SD API disponível" if available else "SD API offline (inicie Automatic1111)"
    }


@app.post("/api/sd/generate-portrait")
async def generate_portrait_endpoint(req: GeneratePortraitRequest):
    """
    Gera retrato de personagem via Stable Diffusion.
    
    Retorna path relativo da imagem ou erro se SD não disponível.
    Cache automático: não regenera se imagem já existe (a menos que force_regenerate=True).
    """
    
    # Verificar se SD está disponível
    if not check_sd_available():
        raise HTTPException(
            503, 
            "Stable Diffusion não disponível. Inicie o Automatic1111 WebUI com --api"
        )
    
    try:
        # Gerar retrato
        output_dir = os.path.join(FRONTEND_DIR, "static", "images", "characters")
        
        filepath = generate_character_portrait(
            char_id=req.character_id,
            name=req.name,
            race=req.race,
            char_class=req.char_class,
            gender=req.gender,
            description=req.description,
            nsfw=req.nsfw,
            output_dir=output_dir,
            force_regenerate=req.force_regenerate
        )
        
        if filepath:
            # Retornar path relativo para o frontend
            relative_path = f"/static/images/characters/{req.character_id}.png"
            return {
                "success": True,
                "image_path": relative_path,
                "cached": not req.force_regenerate and os.path.exists(filepath)
            }
        else:
            raise HTTPException(500, "Falha ao gerar imagem via Stable Diffusion")
            
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar imagem: {str(e)}")


@app.get("/api/sd/check-portrait/{character_id}")
async def check_portrait_exists(character_id: str):
    """Verifica se personagem já tem retrato gerado."""
    filepath = os.path.join(
        FRONTEND_DIR, "static", "images", "characters", f"{character_id}.png"
    )
    exists = os.path.exists(filepath)
    
    return {
        "exists": exists,
        "image_path": f"/static/images/characters/{character_id}.png" if exists else None
    }


@app.delete("/api/sd/delete-portrait/{character_id}")
async def delete_portrait(character_id: str):
    """Deleta retrato de personagem (para forçar regeneração)."""
    filepath = os.path.join(
        FRONTEND_DIR, "static", "images", "characters", f"{character_id}.png"
    )
    
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return {"success": True, "message": "Retrato deletado"}
        except Exception as e:
            raise HTTPException(500, f"Erro ao deletar: {str(e)}")
    else:
        raise HTTPException(404, "Retrato não encontrado")


if __name__ == "__main__":
    import uvicorn
    from backend.config import HOST, PORT
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
