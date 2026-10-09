"""
Rotas de chat: enviar mensagem, regenerar, desfazer e editar.

A resposta sai por SSE. Cada evento é uma linha `data: {json}` com um destes tipos:
  roll   resultado de rolagem automática (modo completo)
  token  pedaço da resposta
  error  mensagem de erro legível
  done   fim do stream
"""

import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.character_manager import load_character, load_world
from backend.memory import history_budget, prompt_window, update_summary, window_start
from backend.models import ChatRequest, EditMessageRequest, MessageRole, RegenerateRequest, SwipeRequest
from backend.ollama_client import OllamaError, build_system_prompt, stream_chat
from backend.rpg_engine import (
    auto_relationship_delta, calculate_xp_reward, cast_delta, cast_targets, detect_risk_action,
    get_roll_modifier, roll_d20,
)
from backend.rpg_models import GameMode
from backend.session_manager import (
    add_message, add_swipe, clear_swipes, get_rpg_state, load_session, pop_last_assistant,
    pop_last_exchange, save_session, session_lock, start_swipes, swipe_info, swipes_valid,
)
from backend.settings_manager import get_settings

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _require(session_id: str, character_id: str):
    session = load_session(session_id)
    if not session:
        raise HTTPException(404, "Sessão não encontrada")
    character = load_character(character_id)
    if not character:
        raise HTTPException(404, "Personagem não encontrado")
    return session, character


def _auto_roll(rpg, text: str) -> Optional[dict]:
    """Rolagem automática para ações de risco no modo completo. Atualiza XP e log."""
    if rpg.mode != GameMode.FULL or not rpg.player:
        return None
    attr = detect_risk_action(text)
    if not attr:
        return None

    modifier = get_roll_modifier(rpg.player, attr)
    result = roll_d20(modifier)
    event = (
        f"[ROLAGEM AUTOMÁTICA: {attr}: d20={result['natural']} + {modifier} = "
        f"{result['final']} | {result['label']}]"
    )

    xp = calculate_xp_reward(result["outcome"])
    leveled_up = rpg.player.add_xp(xp) if xp > 0 else False
    log = f"Rolagem {attr}: {result['natural']}+{modifier}={result['final']} [{result['label']}]"
    if xp:
        log += f" +{xp}XP"
    if leveled_up:
        log += f" | LEVEL UP Nível {rpg.player.level}!"
    rpg.event_log.append(log)
    return {"result": result, "event": event}


def _streaming(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _reply(session_id: str, character_id: str, user_text: Optional[str],
                 regen: bool = False) -> AsyncIterator[str]:
    """
    Gera a resposta do personagem. Com user_text, grava antes a mensagem do jogador
    (e aplica rolagem/relacionamento); sem ele, só responde ao histórico atual
    (regenerar). Tudo roda sob o lock da sessão.
    """
    async with session_lock(session_id):
        session = load_session(session_id)
        character = load_character(character_id)
        if not session or not character:
            yield _sse({"type": "error", "message": "Sessão ou personagem não encontrado."})
            yield _sse({"type": "done"})
            return

        rpg = get_rpg_state(session)
        settings = get_settings()
        added_user_message = False

        if user_text is not None:
            roll = _auto_roll(rpg, user_text)
            stored = f"{user_text}\n\n{roll['event']}" if roll else user_text

            if rpg.player and rpg.mode != GameMode.NARRATIVE:
                if character.group and character.cast and rpg.cast_relations:
                    # Cada integrante tem a sua relação: vale para quem foi citada, ou para quem acabou de falar.
                    previous = next((m.content for m in reversed(session.history)
                                     if m.role == MessageRole.ASSISTANT), "")
                    delta = cast_delta(user_text)
                    for cid in cast_targets(user_text, previous, character.cast):
                        rel = rpg.cast_relations.get(cid)
                        if rel:
                            rel.set_score(rel.score + delta)
                else:
                    delta = auto_relationship_delta(user_text)
                    if delta:
                        rpg.player.relationship.set_score(rpg.player.relationship.score + delta)
            rpg.event_log = rpg.event_log[-50:]
            session.rpg_state = rpg
            clear_swipes(session)  # mensagem nova: as versões da resposta anterior deixam de valer
            add_message(session, MessageRole.USER, stored)
            added_user_message = True

            if roll:
                yield _sse({"type": "roll", "result": roll["result"], "event": roll["event"]})

        world = load_world(character.world_id) if character.world_id else None
        system_prompt = build_system_prompt(
            character, world, rpg,
            memory_summary=session.summary if settings["memory_enabled"] else "",
            response_length=settings["response_length"],
        )

        full = ""
        completed = False
        try:
            async for token in stream_chat(prompt_window(session, system_prompt), system_prompt):
                full += token
                yield _sse({"type": "token", "t": token})
            completed = True
        except OllamaError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:  # erro inesperado não pode derrubar o servidor
            yield _sse({"type": "error", "message": f"Erro inesperado: {e}"})
        finally:
            text = full.strip()
            if text and (completed or len(text) >= 20):
                # Resposta completa, ou parcial que o jogador chegou a ler.
                add_message(session, MessageRole.ASSISTANT, text)
                if regen:
                    add_swipe(session, text)
                    save_session(session)
            elif regen and session.swipes:
                # Falhou ao regenerar: devolve a resposta que já existia em vez de deixar a conversa sem ela.
                add_message(session, MessageRole.ASSISTANT, session.swipes[session.swipe_index])
            elif added_user_message:
                # Nada gerado: desfaz a mensagem do jogador para o histórico não ficar torto.
                if session.history and session.history[-1].role == MessageRole.USER:
                    session.history.pop()
                    save_session(session)

        if completed and text:
            yield _sse({"type": "done"})
            try:
                keep_from = window_start(session, history_budget(system_prompt))
                await update_summary(session, character.name, keep_from)
            except Exception:
                pass  # memória é um extra; nunca deve quebrar o chat
        else:
            yield _sse({"type": "done"})


@router.post("/chat")
async def chat(req: ChatRequest):
    _require(req.session_id, req.character_id)
    return _streaming(_reply(req.session_id, req.character_id, req.message.strip()))


@router.post("/chat/regenerate")
async def regenerate(req: RegenerateRequest):
    """Descarta a última resposta do personagem e gera outra."""
    session, _ = _require(req.session_id, req.character_id)
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        if not session or len(session.history) < 2:
            raise HTTPException(400, "Não há resposta para regenerar")
        if session.history[-1].role == MessageRole.ASSISTANT:
            start_swipes(session)  # a resposta atual vira a versão 1
            pop_last_assistant(session)
    return _streaming(_reply(req.session_id, req.character_id, None, regen=True))


@router.post("/chat/swipe")
async def swipe(req: SwipeRequest):
    """Troca a última resposta por outra das versões guardadas."""
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        if not session:
            raise HTTPException(404, "Sessão não encontrada")
        if not swipes_valid(session):
            raise HTTPException(400, "Não há outras versões desta resposta")
        index = max(0, min(len(session.swipes) - 1, session.swipe_index + req.delta))
        session.swipe_index = index
        session.history[-1].content = session.swipes[index]
        save_session(session)
        return {"content": session.history[-1].content, **swipe_info(session)}


@router.post("/chat/undo")
async def undo(req: RegenerateRequest):
    """Desfaz a última troca e devolve o texto do jogador para ele editar."""
    _require(req.session_id, req.character_id)
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        user_text = pop_last_exchange(session) if session else None
    if user_text is None:
        raise HTTPException(400, "Nada para desfazer")
    return {"user_text": user_text}


@router.post("/session/edit")
async def edit_message(req: EditMessageRequest):
    """Edita o texto de uma mensagem do histórico (para corrigir uma resposta)."""
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        if not session:
            raise HTTPException(404, "Sessão não encontrada")
        if not 0 <= req.index < len(session.history):
            raise HTTPException(400, "Mensagem inexistente")
        # A validade das versões é checada antes de mexer no texto (ela compara com o texto atual).
        edits_current_swipe = swipes_valid(session) and req.index == session.swipe_for
        session.history[req.index].content = req.content.strip()
        if edits_current_swipe:
            session.swipes[session.swipe_index] = session.history[req.index].content
        # O resumo pode ter usado o texto antigo: recalcula a partir dali.
        if req.index < session.summarized_upto:
            session.summary = ""
            session.summarized_upto = 0
        save_session(session)
    return {"ok": True}
