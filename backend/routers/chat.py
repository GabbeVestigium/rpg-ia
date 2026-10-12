"""
Rotas de chat: enviar mensagem, regenerar, desfazer e editar.

A resposta sai por SSE. Cada evento é uma linha `data: {json}` com um destes tipos:
  roll   resultado de rolagem automática (modo completo)
  token  pedaço da resposta
  replace  texto inteiro corrigido (a resposta entrou em loop e a repetição foi cortada)
  error  mensagem de erro legível
  mood   clima da resposta (troca a expressão do retrato)
  done   fim da resposta: o chat é liberado aqui
Depois do "done", com o chat já liberado, ainda podem chegar:
  choices    três sugestões do que o jogador pode fazer agora
  inventory  o que a cena deu ou tirou do jogador
"""

import json
import re
from contextlib import aclosing
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.character_manager import load_character, load_world
from backend.choices import current_choices, remember_choices, suggest_choices
from backend.inventory_ai import apply_changes, describe, extract_changes, looks_like_item_change, revert_changes
from backend.loop_guard import drop_reused_last, guard, reuse_pool, trim_unfinished
from backend.lorebook import select_lore
from backend.mood import detect_mood
from backend.memory import apply_summary, draft_summary, est_tokens, history_budget, prompt_window, summary_point
from backend.models import ChatRequest, EditMessageRequest, Message, MessageRole, RegenerateRequest, SwipeRequest
from backend.profile_manager import load_profile
from backend.ollama_client import (
    NOTE_MARKERS, RESTART, OllamaError, build_system_prompt, chat_stops, player_name_for, stream_chat,
    turn_reminder,
)
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

GROUP_MAX_TEMPERATURE = 0.7


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


ROLL_TAG = "\n\n[ROLAGEM AUTOMÁTICA:"


def _revert_roll(session, user_text: str) -> str:
    """Desfazer: tira a rolagem automática do texto devolvido ao jogador e o XP que ela deu
    (se não subiu de nível; aí o XP fica, para não bagunçar o nível)."""
    text, sep, tag = user_text.partition(ROLL_TAG)
    if not sep:
        return user_text
    rpg = get_rpg_state(session)
    m = re.match(r" (.+?): d20=(\d+) \+ (-?\d+) = (-?\d+) \| (.+)\]", tag)
    if m and rpg.player:
        prefix = f"Rolagem {m[1]}: {m[2]}+{m[3]}={m[4]} [{m[5]}]"
        log = next((l for l in reversed(rpg.event_log) if l.startswith(prefix)), "")
        xp = re.search(r"\+(\d+)XP", log)
        if xp and "LEVEL UP" not in log:
            rpg.player.xp = max(0, rpg.player.xp - int(xp[1]))
            rpg.event_log.append(f"Rolagem desfeita: -{xp[1]}XP")
            session.rpg_state = rpg
            save_session(session)
    return text


def _still_current(session_id: str, text: str):
    """A sessão, se a última mensagem ainda é esta resposta (ninguém mandou, desfez ou editou nada)."""
    session = load_session(session_id)
    if session and session.history and session.history[-1].role == MessageRole.ASSISTANT \
            and session.history[-1].content == text:
        return session
    return None


def _clean_saved(m: Message) -> Message:
    """Conversas antigas podem ter o lembrete copiado dentro da resposta: ele não volta ao modelo."""
    if m.role != MessageRole.ASSISTANT:
        return m
    content = m.content
    for marker in NOTE_MARKERS:
        content = content.split(marker, 1)[0]
    return Message(role=m.role, content=content.rstrip()) if content != m.content else m


def _revert_inventory(session) -> None:
    """Desfaz no inventário o que a última resposta tinha dado ou tirado (se for o caso)."""
    rpg = get_rpg_state(session)
    if rpg.player and rpg.last_inventory:
        revert_changes(rpg.player.inventory, rpg.last_inventory)
        rpg.event_log.append("Inventário revertido (troca refeita)")
    rpg.last_inventory = None
    session.rpg_state = rpg
    save_session(session)


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
    (regenerar). A geração roda sob o lock da sessão; os extras depois do "done" (escolhas,
    inventário, resumo) rodam com o lock livre e só gravam se a resposta ainda for a última.
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
            rpg.last_inventory = None  # a troca anterior já ficou firme: desfazer só mexe na nova
            session.rpg_state = rpg
            clear_swipes(session)  # mensagem nova: as versões da resposta anterior deixam de valer
            add_message(session, MessageRole.USER, stored)
            added_user_message = True

            if roll:
                yield _sse({"type": "roll", "result": roll["result"], "event": roll["event"]})

        world = load_world(character.world_id) if character.world_id else None
        # Fatos do livro do mundo que a conversa acabou de citar (últimas mensagens).
        lore = select_lore(world, [m.content for m in session.history[-4:]])
        profile = load_profile()
        player = player_name_for(rpg, profile)
        last_user = next((m.content for m in reversed(session.history) if m.role == MessageRole.USER), "")
        reminder = turn_reminder(character, player, last_user)

        def prompt_for(char) -> str:
            return build_system_prompt(
                char, world, rpg,
                memory_summary=session.summary if settings["memory_enabled"] else "",
                response_length=settings["response_length"],
                lore_entries=lore,
                profile=profile,
            )

        system_prompt = prompt_for(character)
        budget = history_budget(system_prompt, settings) - est_tokens(reminder)
        if budget < settings["num_ctx"] // 4 and character.example_dialogue:
            # Ficha grande demais para o contexto: as falas de exemplo saem para o histórico caber
            # (sem histórico o modelo repete a própria resposta anterior).
            system_prompt = prompt_for(character.model_copy(update={"example_dialogue": ""}))
            budget = history_budget(system_prompt, settings) - est_tokens(reminder)
        window = [_clean_saved(m) for m in prompt_window(session, budget)]
        # Vai junto da última fala do jogador (só no envio, o histórico salvo não muda): nem todo
        # modelo do Ollama aceita mensagem de sistema no meio da conversa.
        if window and window[-1].role == MessageRole.USER:
            window = window[:-1] + [Message(role=MessageRole.USER, content=f"{window[-1].content}\n\n{reminder}")]
        else:
            window = window + [Message(role=MessageRole.SYSTEM, content=reminder)]
        # Cena com elenco grande: menos criatividade, mais coerência (o modelo inventa menos).
        temperature = min(settings["temperature"], GROUP_MAX_TEMPERATURE) if character.group else None
        # Trechos que o modelo não deve reciclar: as duas últimas respostas e as falas de exemplo.
        recent = [m.content for m in session.history if m.role == MessageRole.ASSISTANT][-2:]
        pool = reuse_pool(recent + [character.example_dialogue or ""])

        full = ""
        completed = False
        info: dict = {}
        try:
            # aclosing: ao sair no meio (loop), fecha a conexão e o Ollama para de gerar na hora.
            async with aclosing(stream_chat(window, system_prompt, temperature,
                                            stop=chat_stops(player), info=info)) as tokens:
                async for token in tokens:
                    if token == RESTART:
                        # O que saiu até aqui era raciocínio do modelo, não resposta.
                        full = ""
                        yield _sse({"type": "replace", "text": full})
                        continue
                    clean, stop = guard(full + token, pool, player)
                    if clean == full + token:
                        yield _sse({"type": "token", "t": token})
                    else:
                        # Loop, trecho reciclado, turno do jogador ou lembrete copiado: manda o texto limpo.
                        yield _sse({"type": "replace", "text": clean})
                    full = clean
                    if stop:
                        break
            final = drop_reused_last(full, pool)
            if info.get("done_reason") == "length":
                final = trim_unfinished(final)   # cortada pelo limite de tokens: termina na última frase
            if final != full:
                full = final
                yield _sse({"type": "replace", "text": full})
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

        if not (completed and text):
            if completed:
                yield _sse({"type": "error", "message": "O modelo não respondeu nada. Tente regenerar ou "
                                                        "escolha outro modelo nas Configurações."})
            yield _sse({"type": "done"})
            return
        base = session.model_copy(deep=True)   # a sessão como ficou ao terminar a resposta

    # Daqui em diante o lock está livre: o jogador já pode mandar outra mensagem.
    if not character.group:
        yield _sse({"type": "mood", "mood": detect_mood(text)})   # troca a expressão do retrato
    yield _sse({"type": "done"})
    last_user = next((m.content for m in reversed(base.history[:-1]) if m.role == MessageRole.USER), "")
    if settings["auto_choices"]:
        try:
            choices = await suggest_choices(character.name, last_user, text)
            current = None
            if choices:
                async with session_lock(session_id):
                    current = _still_current(session_id, text)
                    if current:
                        remember_choices(current, choices)
                        save_session(current)
            if current:
                yield _sse({"type": "choices", "options": choices})
        except Exception:
            pass  # as escolhas são um extra; nunca devem quebrar o chat
    if (settings["auto_inventory"] and rpg.mode != GameMode.NARRATIVE and rpg.player
            and (user_text is not None or regen)):
        try:
            if looks_like_item_change(text, last_user):
                changes = await extract_changes(last_user, text)
                done = None
                async with session_lock(session_id):
                    current = _still_current(session_id, text)
                    cur_rpg = get_rpg_state(current) if current else None
                    if cur_rpg and cur_rpg.player:
                        done = apply_changes(cur_rpg.player.inventory, changes)
                        if done:
                            cur_rpg.last_inventory = done
                            cur_rpg.event_log.append("Inventário: " + ", ".join(describe(done)))
                            current.rpg_state = cur_rpg
                            save_session(current)
                if done:
                    yield _sse({"type": "inventory", "changes": describe(done)})
        except Exception:
            pass  # o inventário automático é um extra; nunca deve quebrar o chat
    try:
        if not session_lock(session_id).locked():   # já chegou outra mensagem: ela tem prioridade
            draft = await draft_summary(base, character.name, summary_point(base, budget))
            if draft:
                async with session_lock(session_id):
                    current = load_session(session_id)
                    if current:
                        apply_summary(current, base, draft)
    except Exception:
        pass  # memória é um extra; nunca deve quebrar o chat


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
            _revert_inventory(session)  # a troca será refeita, então o que ela deu/tirou é desfeito
            start_swipes(session)  # a resposta atual vira a versão 1
            pop_last_assistant(session)
    return _streaming(_reply(req.session_id, req.character_id, None, regen=True))


@router.post("/chat/choices")
async def choices(req: RegenerateRequest):
    """Escolhas para a resposta atual. Usado ao abrir a conversa (a primeira fala também ganha botões)."""
    _, character = _require(req.session_id, req.character_id)
    if not get_settings()["auto_choices"]:
        return {"options": []}
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        if not session or not session.history or session.history[-1].role != MessageRole.ASSISTANT:
            return {"options": []}
        options = current_choices(session)
        if not options:
            last_user = next((m.content for m in reversed(session.history[:-1])
                              if m.role == MessageRole.USER), "")
            try:
                options = await suggest_choices(character.name, last_user, session.history[-1].content)
            except OllamaError:
                options = []
            if options:
                remember_choices(session, options)
                save_session(session)
    return {"options": options}


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
        if session:
            _revert_inventory(session)
        user_text = pop_last_exchange(session) if session else None
        if user_text:
            user_text = _revert_roll(session, user_text)
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
