"""
Livro de fatos (lorebook).

O núcleo do mundo (`World.lore`) vai em todo prompt, então precisa ser curto. Os detalhes
ficam em entradas com palavras-chave e só entram quando a conversa as cita, o que poupa
contexto, algo valioso numa GPU de 6 GB.
"""

import re
from typing import List

from backend.models import LoreEntry, World
from backend.rpg_engine import _fold

MAX_ENTRIES = 5       # no máximo isto entra por mensagem
MAX_CHARS = 1400      # e no máximo isto de texto no total


def _last_match(text: str, keys: List[str]) -> int:
    """Posição do último trecho que casa com alguma chave (-1 se nenhuma casa)."""
    best = -1
    for key in keys:
        key = _fold(key).strip()
        if not key:
            continue
        for m in re.finditer(rf"(?<!\w){re.escape(key)}(?!\w)", text):
            best = max(best, m.start())
    return best


def select_lore(world: World | None, texts: List[str]) -> List[LoreEntry]:
    """
    Escolhe as entradas para esta mensagem. `texts` vem do mais antigo para o mais novo
    (ex: últimas mensagens). Entradas "always" sempre entram; as outras ficam em ordem de
    quão recente foi a menção, e o orçamento corta o excesso.
    """
    if not world or not world.entries:
        return []
    joined = "\n".join(_fold(t) for t in texts if t)

    chosen: List[LoreEntry] = [e for e in world.entries if e.always]
    scored = []
    for e in world.entries:
        if e.always:
            continue
        pos = _last_match(joined, e.keys or [e.name])
        if pos >= 0:
            scored.append((pos, e))
    scored.sort(key=lambda t: t[0], reverse=True)  # mais recente primeiro
    chosen += [e for _, e in scored]

    result, used = [], 0
    for e in chosen:
        cost = len(e.name) + len(e.text) + 4
        if result and (len(result) >= MAX_ENTRIES or used + cost > MAX_CHARS):
            break
        result.append(e)
        used += cost
    return result


def lore_block(entries: List[LoreEntry]) -> str:
    """Texto do prompt para as entradas escolhidas."""
    if not entries:
        return ""
    lines = ["\n### Fatos que importam agora:"]
    lines += [f"- {e.name}: {e.text}" for e in entries]
    return "\n".join(lines) + "\n"
