"""
Botões de escolha depois de cada resposta.

Com o chat já liberado, o modelo lê a última troca e sugere três coisas que o jogador pode
fazer ou dizer agora. O jogador toca numa e ela vira a mensagem dele. São só atalhos: dá para
continuar digitando o que quiser.
"""

import json
import re
from typing import List

from backend.models import MessageRole, SessionData
from backend.ollama_client import complete

COUNT = 3
MAX_LEN = 90

_SYSTEM = (
    "Você sugere as próximas jogadas de um roleplay. Leia a cena e responda SOMENTE um JSON, sem texto extra: "
    'uma lista com 3 textos curtos, por exemplo ["...", "...", "..."]. '
    "Cada texto é algo que o JOGADOR faz ou diz agora, escrito em primeira pessoa, em português do Brasil, "
    "com no máximo 12 palavras. As três precisam levar a história para caminhos diferentes: uma cuidadosa ou "
    "curiosa, uma ousada, e uma inesperada. Use o que acabou de acontecer na cena e cite pelo nome as pessoas, "
    "lugares e objetos que aparecem nela; nada vago como \"quero ver aquele lugar\". Não escreva pelo outro "
    "personagem, não numere e não explique."
)


def parse_choices(raw: str) -> List[str]:
    """Extrai a lista do texto do modelo (que às vezes vem com texto em volta) e limpa cada opção."""
    start, end = raw.find("["), raw.rfind("]")
    items: list = []
    if 0 <= start < end:
        try:
            data = json.loads(raw[start:end + 1])
            items = data if isinstance(data, list) else []
        except json.JSONDecodeError:
            items = []
    if not items:
        # Plano B: uma opção por linha ("1. ...", "- ...").
        items = [line for line in raw.splitlines() if re.match(r"^\s*(\d+[.)]|[-*•])\s+\S", line)]

    seen, result = set(), []
    for item in items:
        text = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", str(item or ""))
        text = re.sub(r"\s+", " ", text).strip(" \"'“”")
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN].rsplit(" ", 1)[0] + "…"
        if len(text) >= 3 and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result[:COUNT]


async def suggest_choices(character_name: str, last_user: str, reply: str) -> List[str]:
    scene = (f"Jogador: {last_user.strip()}\n\n" if last_user.strip() else "") + f"{character_name}: {reply.strip()}"
    raw = await complete(scene[-3000:], system=_SYSTEM, num_predict=200, temperature=0.8)
    return parse_choices(raw)


def remember_choices(session: SessionData, choices: List[str]) -> None:
    """Guarda as escolhas junto da resposta a que pertencem (para voltar a elas ao reabrir a conversa)."""
    session.choices = choices
    session.choices_for = session.history[-1].content if session.history else ""


def current_choices(session: SessionData) -> List[str]:
    """As escolhas só valem enquanto a última mensagem for a mesma resposta para a qual foram feitas."""
    if (session.choices and session.history and session.history[-1].role == MessageRole.ASSISTANT
            and session.history[-1].content == session.choices_for):
        return session.choices
    return []
