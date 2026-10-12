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
    "Cada texto é algo que o jogador faz ou diz agora, escrito em primeira pessoa, em português do Brasil, "
    "com no máximo 12 palavras. As três levam a história para três caminhos diferentes. Use o que acabou de "
    "acontecer na cena e cite pelo nome as pessoas, lugares e objetos que aparecem nela; nada vago como "
    "\"quero ver aquele lugar\". Não escreva pelo outro personagem, não numere, não dê títulos e não explique."
)


def parse_choices(raw: str, character_name: str = "") -> List[str]:
    """Extrai a lista do texto do modelo (que às vezes vem com texto em volta, cortada ou em linhas)
    e limpa cada opção."""
    start, end = raw.find("["), raw.rfind("]")
    items: list = []
    if 0 <= start < end:
        try:
            data = json.loads(raw[start:end + 1])
            items = data if isinstance(data, list) else []
        except json.JSONDecodeError:
            items = []
    if not items:
        # Plano B: textos entre aspas (JSON quebrado ou cortado no meio).
        items = re.findall(r'"([^"\n]{3,})"', raw)
    if not items:
        # Plano C: uma opção por linha ("1. ...", "- ...").
        items = [line for line in raw.splitlines() if re.match(r"^\s*(\d+[.)]|[-*•])\s+\S", line)]

    seen, result = set(), []
    for item in items:
        if isinstance(item, dict):   # {"texto": "..."}: fica com o primeiro valor de texto
            item = next((v for v in item.values() if isinstance(v, str)), "")
        text = re.sub(r"^\s*(\d+[.)]|[-•])\s*", "", str(item or "")).replace("*", "")
        text = re.sub(r"\s+", " ", text).strip(" \"'“”")
        if character_name and text.lower().startswith(character_name.lower() + ":"):
            continue   # fala do outro personagem, não do jogador
        # Rótulo curto na frente ("Ousada: ...", "Opção 1: ..."): sai, se sobrar texto.
        unlabeled = re.sub(r"^[\wÀ-ú]+( (ou|\d+) [\wÀ-ú]+| \d+)?\s*:\s*", "", text)
        if len(unlabeled) >= 3:
            text = unlabeled
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN].rsplit(" ", 1)[0] + "…"
        if len(text) >= 3 and not text.endswith(":") and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result[:COUNT]


async def suggest_choices(character_name: str, last_user: str, reply: str) -> List[str]:
    scene = (f"Jogador: {last_user.strip()}\n\n" if last_user.strip() else "") + f"{character_name}: {reply.strip()}"
    raw = await complete(scene[-3000:], system=_SYSTEM, num_predict=300, temperature=0.8)
    return parse_choices(raw, character_name)


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
