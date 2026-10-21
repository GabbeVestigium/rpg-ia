"""
Clima de uma resposta, para trocar a expressão do retrato.

É uma heurística barata por palavras (sem chamar o modelo): conta pistas de cada emoção nos
trechos finais da resposta e escolhe a mais forte. Sem pista clara, fica "neutral".
"""

import re
from typing import Dict, List

from backend.rpg_engine import _fold

# Prefixos já sem acento. A resposta é comparada em minúsculas e sem acento.
_CLUES: Dict[str, List[str]] = {
    "happy":     ["sorri", "riu", "risad", "gargalh", "feliz", "alegr", "radiante", "satisfeit", "abraca", "encant"],
    "angry":     ["raiva", "furios", "irritad", "rosna", "cerra os punhos", "franze", "grita", "bufa", "ira ", "enfurec"],
    "sad":       ["chora", "choro", "lagrima", "triste", "voz embargad", "soluc", "abatid", "melancol", "olhos marejad"],
    "surprised": ["surpres", "arregal", "espanta", "engasg", "perplex", "chocad", "boquiaberta", "sobressalt"],
    "shy":       ["cora ", "corou", "corand", "rubor", "envergonh", "desvia o olhar", "gagueja", "timid", "bochechas"],
}

MOODS = ["neutral", *_CLUES]
TAIL_CHARS = 500      # a emoção que vale é a do fim da resposta


def detect_mood(text: str) -> str:
    tail = _fold(text)[-TAIL_CHARS:] + " "
    best, best_score = "neutral", 0
    for mood, stems in _CLUES.items():
        score = sum(len(re.findall(rf"(?<!\w){re.escape(s)}", tail)) for s in stems)
        if score > best_score:
            best, best_score = mood, score
    return best
