"""
Corta respostas que entram em loop.

Modelos pequenos às vezes repetem o mesmo trecho sem parar ("Estela." / "Vamos lá..." de novo e
de novo). Enquanto a resposta chega, olhamos o fim do texto: se os últimos trechos são uma cópia
dos trechos logo antes deles, a geração para e a cópia é jogada fora.
"""

import re
from typing import List, Optional, Tuple

# Divide em frases e parágrafos, guardando onde cada pedaço começa.
_SPLIT = re.compile(r"\n+|(?<=[.!?…])[\"”']?\s+")
MAX_WINDOW = 8          # até quantos trechos seguidos formam um bloco repetido
MIN_BLOCK_CHARS = 40    # bloco curto ("Sim." "Sim.") pode ser de propósito


def _segments(text: str) -> List[Tuple[int, str]]:
    out, pos = [], 0
    for m in _SPLIT.finditer(text):
        piece = text[pos:m.start()]
        if piece.strip():
            out.append((pos, piece))
        pos = m.end()
    if text[pos:].strip():
        out.append((pos, text[pos:]))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", s.lower()).strip()


def find_loop(text: str) -> Optional[int]:
    """Posição onde começa a cópia repetida no fim do texto, ou None se não há loop."""
    segs = _segments(text)
    for w in range(1, MAX_WINDOW + 1):
        if len(segs) < 2 * w:
            break
        first, second = segs[-2 * w:-w], segs[-w:]
        a = [_norm(s) for _, s in first]
        if a == [_norm(s) for _, s in second] and sum(len(x) for x in a) >= MIN_BLOCK_CHARS:
            return second[0][0]
    return None


def trim_loop(text: str) -> str:
    """Texto sem as cópias repetidas no fim (e sem sobras de espaço)."""
    while (cut := find_loop(text)) is not None:
        text = text[:cut].rstrip()
    return text
