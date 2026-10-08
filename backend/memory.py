"""
Memória de longo prazo.

O modelo só enxerga uma janela das últimas mensagens. O que sai dela vira um
resumo que fica no system prompt, então personagens e fatos importantes não se
perdem depois de algumas dezenas de turnos.

O histórico completo continua salvo em disco; a sessão guarda só até onde o
resumo já cobre (summarized_upto).
"""

from typing import List

from backend.models import Message, SessionData
from backend.ollama_client import OllamaError, complete
from backend.session_manager import save_session
from backend.settings_manager import get_settings

# Só resume quando há pelo menos isto de mensagens novas fora da janela,
# para não chamar o modelo a cada turno.
SUMMARY_BATCH = 6
MAX_CHUNK = 40

_SYSTEM = (
    "Você mantém a memória de uma história de roleplay. Escreva um resumo factual e "
    "compacto, em português, em terceira pessoa e no passado. Preserve: nomes, lugares, "
    "promessas, segredos revelados, eventos importantes, itens, o estado do relacionamento "
    "entre os personagens e como a última cena terminou. Não invente nada, não julgue e não "
    "comente. Responda só com o resumo, em até 250 palavras."
)


def est_tokens(text: str) -> int:
    """Estimativa conservadora de tokens (português gasta ~1 token a cada 3 caracteres)."""
    return len(text) // 3 + 4


def history_budget(system_prompt: str, settings: dict | None = None) -> int:
    """Tokens que sobram para o histórico depois do system prompt e da resposta."""
    settings = settings or get_settings()
    return settings["num_ctx"] - settings["num_predict"] - est_tokens(system_prompt) - 64


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


def prompt_window(session: SessionData, system_prompt: str) -> List[Message]:
    """
    Mensagens enviadas ao modelo. Sem resumo, a abertura do personagem é mantida
    mesmo quando a janela já passou dela, para o modelo saber como a cena começou.
    """
    start = window_start(session, history_budget(system_prompt))
    window = session.history[start:]
    if start > 0 and not session.summary:
        return [session.history[0]] + window
    return window


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


async def update_summary(session: SessionData, character_name: str, keep_from: int) -> bool:
    """
    Atualiza o resumo com as mensagens que saíram da janela.
    Devolve True se atualizou. Falhas do Ollama não quebram o chat: a faixa
    continua pendente e é tentada de novo no próximo turno.
    """
    if not needs_summary(session, keep_from):
        return False
    start, end = session.summarized_upto, min(keep_from, session.summarized_upto + MAX_CHUNK)  # o que sobrar é resumido no(s) próximo(s) turno(s)
    chunk = session.history[start:end]

    previous = f"Resumo até agora:\n{session.summary}\n\n" if session.summary else ""
    prompt = (
        f"{previous}Novas mensagens a incorporar:\n{_transcript(chunk, character_name)}\n\n"
        "Escreva o resumo atualizado completo."
    )
    try:
        text = await complete(prompt, system=_SYSTEM, num_predict=450, temperature=0.2)
    except OllamaError:
        return False
    if not text.strip():
        return False

    session.summary = text.strip()
    session.summarized_upto = end
    save_session(session)
    return True
