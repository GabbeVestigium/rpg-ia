"""
Corta respostas que entram em loop ou saem do papel.

Modelos pequenos às vezes repetem o mesmo trecho sem parar ("Estela." / "Vamos lá..." de novo e
de novo), reciclam parágrafos da resposta anterior ou das falas de exemplo, escrevem o turno do
jogador ou copiam o lembrete escondido. Enquanto a resposta chega, `guard` olha o texto e devolve
a versão limpa, dizendo se a geração deve parar.
"""

import re
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Set, Tuple

from backend.ollama_client import NOTE_MARKERS

# Divide em frases e parágrafos, guardando onde cada pedaço começa. Também separa ações seguidas
# (*sorri.* *olha.*). A versão com vírgulas pega loops de enumeração sem ponto final.
_SPLIT = re.compile(r"\n+|(?<=[.!?…])[\"”'*]?\s+|(?<=\*)\s+(?=\*)")
_SPLIT_COMMAS = re.compile(_SPLIT.pattern + r"|(?<=,)\s+")
MAX_WINDOW = 12         # até quantos trechos seguidos formam um bloco repetido
MIN_BLOCK_CHARS = 40    # bloco curto ("Sim." "Sim.") pode ser de propósito
SAME_RUN = 6            # mas o mesmo trecho 6 vezes seguidas é loop (12 se for curto)
SHORT_PIECE = 12        # abaixo disso o trecho é curto
REUSE_MIN_CHARS = 40    # trecho copiado de respostas anteriores: só conta se for grande
NEAR_MIN_CHARS = 60     # quase-cópia (uma palavra trocada) só em trechos maiores ainda
NEAR_RATIO = 0.9


def _segments(text: str, commas: bool = False) -> List[Tuple[int, str]]:
    out, pos = [], 0
    for m in (_SPLIT_COMMAS if commas else _SPLIT).finditer(text):
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
    segs = _segments(text, commas=True)
    norms = [_norm(s) for _, s in segs]
    # Trecho curto ("Sim, sim, sim...") pode ser ênfase: só conta como loop se dobrar a sequência.
    run = SAME_RUN if norms and len(norms[-1]) >= SHORT_PIECE else 2 * SAME_RUN
    if len(norms) >= run and len(set(norms[-run:])) == 1:
        return segs[-run + 1][0]   # fica a primeira, sai o resto
    for w in range(1, MAX_WINDOW + 1):
        if len(segs) < 2 * w:
            break
        a, b = norms[-2 * w:-w], norms[-w:]
        if a == b and sum(len(x) for x in a) >= MIN_BLOCK_CHARS:
            return segs[-w][0]
    # Um trecho grande que já apareceu antes nesta mesma resposta, com outra coisa no meio. Olha o
    # penúltimo trecho: o último pode estar chegando pela metade.
    sents = _segments(text)
    norms = [_norm(s) for _, s in sents]
    if len(sents) >= 3 and len(norms[-2]) >= MIN_BLOCK_CHARS and norms[-2] in norms[:-2]:
        return sents[-2][0]
    return None


def trim_loop(text: str) -> str:
    """Texto sem as cópias repetidas no fim (e sem sobras de espaço)."""
    while (cut := find_loop(text)) is not None:
        text = text[:cut].rstrip()
    return text


def reuse_pool(texts: Iterable[str]) -> Set[str]:
    """Trechos grandes de respostas anteriores e das falas de exemplo, já normalizados."""
    pool = set()
    for t in texts:
        for _, s in _segments(t or ""):
            n = _norm(s)
            if len(n) >= REUSE_MIN_CHARS:
                pool.add(n)
    return pool


def _is_reused(norm: str, pool: Set[str]) -> bool:
    if len(norm) < REUSE_MIN_CHARS:
        return False
    if norm in pool:
        return True
    if len(norm) < NEAR_MIN_CHARS:
        return False
    for p in pool:
        m = SequenceMatcher(None, norm, p, autojunk=False)
        if m.real_quick_ratio() >= NEAR_RATIO and m.quick_ratio() >= NEAR_RATIO and m.ratio() >= NEAR_RATIO:
            return True
    return False


def _player_turn(text: str, player: str) -> Optional[int]:
    names = ["Você", "Jogador", "User"] + ([re.escape(player)] if player and player != "o jogador" else [])
    m = re.search(rf"(?:^|\n)[ \t]*[*_]*[ \t]*(?:{'|'.join(names)})[ \t]*[*_]*[ \t]*:", text)
    return m.start() if m else None


def guard(text: str, pool: Set[str] = frozenset(), player: str = "") -> Tuple[str, bool]:
    """
    Confere a resposta parcial. Devolve (texto, parar):
    - lembrete copiado, turno do jogador ou loop: corta ali e para;
    - trecho reciclado de respostas anteriores: tira só o trecho e deixa continuar.
    """
    cuts = [i for i in (text.find(m) for m in NOTE_MARKERS) if i >= 0]
    player_at = _player_turn(text, player)
    if player_at is not None:
        cuts.append(player_at)
    if cuts:
        return text[:min(cuts)].rstrip(), True
    cut = find_loop(text)
    if cut is not None:
        return text[:cut].rstrip(), True
    if pool:
        segs = _segments(text)
        # Só o trecho que acabou de terminar (o seguinte já começou): uma checagem por trecho.
        if len(segs) >= 2:
            pos, piece = segs[-2]
            if _is_reused(_norm(piece), pool):
                return text[:pos] + text[segs[-1][0]:], False
    return text, False


def drop_reused_last(text: str, pool: Set[str]) -> str:
    """Fim da resposta: `guard` só confere trechos já fechados, então o último é conferido aqui."""
    segs = _segments(text)
    if pool and segs and _is_reused(_norm(segs[-1][1]), pool):
        return text[:segs[-1][0]].rstrip()
    return text


def trim_unfinished(text: str) -> str:
    """Resposta cortada pelo limite de tokens: volta até o fim da última frase completa."""
    m = None
    for m in re.finditer(r"[.!?…][\"”'*]*(?=\s|$)", text):
        pass
    if not m or m.end() < len(text) * 0.5:
        return text   # sem frase completa que valha a pena: melhor mostrar o que veio
    return text[:m.end()].rstrip()
