"""
Memória de longo prazo.

O modelo só enxerga uma janela das últimas mensagens. O que sai dela vira um
resumo que fica no system prompt, então personagens e fatos importantes não se
perdem depois de algumas dezenas de turnos.

O histórico completo continua salvo em disco; a sessão guarda só até onde o
resumo já cobre (summarized_upto).
"""

from typing import List, Optional, Tuple

from backend.models import Message, SessionData
from backend.ollama_client import OllamaError, complete, reply_tokens
from backend.session_manager import save_session
from backend.settings_manager import get_settings

# Só resume quando há pelo menos isto de mensagens novas fora da janela,
# para não chamar o modelo a cada turno.
SUMMARY_BATCH = 6
SUMMARY_TOKENS = 450
_SYSTEM = (
    "Você mantém a memória de uma história de roleplay. Escreva um resumo factual e "
    "compacto, em português, em terceira pessoa e no passado. Preserve: nomes, lugares, "
    "promessas, segredos revelados, eventos importantes, itens, o estado do relacionamento "
    "entre os personagens e como a última cena terminou. Não invente nada, não julgue e não "
    "comente. Responda só com o resumo, em até 250 palavras."
)


def est_tokens(text: str) -> int:
    """Estimativa conservadora de tokens: em português os tokenizadores da família Mistral
    gastam ~1 token a cada 2,7 caracteres (Llama e Qwen gastam menos)."""
    return len(text) * 10 // 27 + 4


def history_budget(system_prompt: str, settings: dict | None = None) -> int:
    """Tokens que sobram para o histórico depois do system prompt e da resposta
    (com folga para os tokens de template de cada mensagem)."""
    settings = settings or get_settings()
    return settings["num_ctx"] - reply_tokens(settings) - est_tokens(system_prompt) - 100


def window_start(session: SessionData, budget: int, settings: dict | None = None) -> int:
    """
    Índice da primeira mensagem que vai inteira para o modelo: as mais recentes que
    cabem no orçamento de tokens, limitadas a `history_turns` turnos. Sempre inclui
    pelo menos a última troca, mesmo que estoure o orçamento.
    """
    settings = settings or get_settings()
    max_messages = settings["history_turns"] * 2
    history = session.history
    used = 0
    count = 0
    for msg in reversed(history):
        cost = est_tokens(msg.content)
        if count >= 2 and (used + cost > budget or count >= max_messages):
            break
        used += cost
        count += 1
    return len(history) - count


def prompt_window(session: SessionData, budget: int) -> List[Message]:
    """
    Mensagens enviadas ao modelo, dentro de `budget` tokens. Sem resumo, a abertura do
    personagem é mantida mesmo quando a janela já passou dela, para o modelo saber como a
    cena começou (e o custo dela sai do orçamento).
    """
    start = window_start(session, budget)
    if start > 0 and not session.summary:
        start = max(1, window_start(session, budget - est_tokens(session.history[0].content)))
        return [session.history[0]] + session.history[start:]
    return session.history[start:]


def summary_point(session: SessionData, budget: int) -> int:
    """
    Até onde o resumo deve cobrir. Resume um pouco ANTES de as mensagens saírem da janela, para
    nunca haver um buraco entre o fim do resumo e o começo da janela.
    """
    start = window_start(session, budget)
    if start == 0:
        return 0
    return min(len(session.history), start + SUMMARY_BATCH + 2)


def needs_summary(session: SessionData, keep_from: int) -> bool:
    """True se há mensagens suficientes fora da janela que ainda não foram resumidas."""
    if not get_settings()["memory_enabled"]:
        return False
    return keep_from - session.summarized_upto >= SUMMARY_BATCH


def _transcript(messages: List[Message], character_name: str) -> str:
    lines = []
    for m in messages:
        who = character_name if m.role.value == "assistant" else "Jogador"
        lines.append(f"{who}: {m.content}")
    return "\n".join(lines)


def _chunk_end(session: SessionData, keep_from: int) -> int:
    """Fim do pedaço a resumir agora: o que cabe no contexto junto com o resumo anterior.
    O que sobrar é resumido no(s) próximo(s) turno(s)."""
    budget = (get_settings()["num_ctx"] - SUMMARY_TOKENS - est_tokens(_SYSTEM)
              - est_tokens(session.summary) - 100)
    end = session.summarized_upto
    while end < keep_from:
        cost = est_tokens(session.history[end].content) + 4
        if end > session.summarized_upto and cost > budget:
            break
        budget -= cost
        end += 1
    return end


async def draft_summary(session: SessionData, character_name: str, keep_from: int) -> Optional[Tuple[str, int]]:
    """
    Novo resumo com as mensagens que saíram da janela, sem salvar: (texto, até onde cobre).
    None se não precisa ou se o Ollama falhou (a faixa continua pendente e é tentada de novo).
    """
    if not needs_summary(session, keep_from):
        return None
    start, end = session.summarized_upto, _chunk_end(session, keep_from)
    chunk = session.history[start:end]

    previous = f"Resumo até agora:\n{session.summary}\n\n" if session.summary else ""
    prompt = (
        f"{previous}Novas mensagens a incorporar:\n{_transcript(chunk, character_name)}\n\n"
        "Escreva o resumo atualizado completo."
    )
    try:
        text = await complete(prompt, system=_SYSTEM, num_predict=SUMMARY_TOKENS, temperature=0.2)
    except OllamaError:
        return None
    if not text.strip():
        return None
    return text.strip(), end


def apply_summary(current: SessionData, base: SessionData, draft: Tuple[str, int]) -> bool:
    """Grava o resumo feito a partir de `base` só se a sessão atual ainda tem o mesmo começo
    (ninguém editou, desfez ou resumiu no meio tempo)."""
    text, end = draft
    if (current.summary != base.summary or current.summarized_upto != base.summarized_upto
            or len(current.history) < end
            or [m.content for m in current.history[:end]] != [m.content for m in base.history[:end]]):
        return False
    current.summary, current.summarized_upto = text, end
    save_session(current)
    return True


async def update_summary(session: SessionData, character_name: str, keep_from: int) -> bool:
    """Atualiza e salva o resumo. Devolve True se atualizou."""
    draft = await draft_summary(session, character_name, keep_from)
    return bool(draft) and apply_summary(session, session, draft)
