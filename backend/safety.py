"""
Regra de projeto: todo personagem (da IA ou do jogador) é adulto, 18+.

Isso vale na idade declarada, no texto de descrição e nas tags que vão para o
Stable Diffusion. A checagem é uma barreira simples (idade mínima + termos que
indicam criança/adolescente). Ela não substitui o bom senso de quem cria o
personagem, mas impede o caminho óbvio.
"""

import re
from typing import List

MIN_AGE = 18

# Termos que indicam menor de idade ou aparência infantil. Ficam de fora palavras
# que aparecem em histórias de fundo de adultos ("na infância", "criança" no
# passado), para não bloquear personagem legítimo.
_MINOR_TERMS = [
    r"loli\w*", r"shota\w*", r"underage", r"under-age", r"minors?", r"toddler",
    r"preteen", r"pre-teen", r"teen", r"teens", r"teenage\w*", r"schoolgirl",
    r"schoolboy", r"jailbait", r"little girl", r"little boy", r"childlike",
    r"child-like", r"baby face", r"adolescente\w*", r"menor de idade",
    r"menores de idade", r"pr[eé]-?adolescente\w*", r"colegial",
    r"apar[eê]ncia infantil", r"corpo de crian[cç]a", r"body of a child",
    r"looks? like a child", r"parece uma crian[cç]a",
]
_MINOR_RE = re.compile(r"\b(?:" + "|".join(_MINOR_TERMS) + r")\b", re.IGNORECASE)

# "tem 15 anos", "aparenta 12 anos", "15 anos de idade", "15-year-old", "aged 14"
_AGE_PATTERNS = [
    re.compile(r"\b(?:tem|ter|aparenta(?:ndo)?|parece(?:ndo)?(?: ter)?|com)\s+(\d{1,2})\s*anos?\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*anos\s+de\s+idade\b", re.IGNORECASE),
    re.compile(r"\bidade\s*(?:de|:)?\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})[\s-]*(?:year|yr)s?[\s-]*old\b", re.IGNORECASE),
    re.compile(r"\bage[d]?\s*[:=]?\s*(\d{1,2})\b", re.IGNORECASE),
]


def find_problems(text: str) -> List[str]:
    """Devolve a lista de motivos pelos quais o texto aponta para menor de idade."""
    if not text:
        return []
    problems: List[str] = []
    for m in _MINOR_RE.finditer(text):
        term = m.group(0).lower()
        if term not in problems:
            problems.append(term)
    for pattern in _AGE_PATTERNS:
        for m in pattern.finditer(text):
            age = int(m.group(1))
            if age < MIN_AGE:
                label = f"idade {age}"
                if label not in problems:
                    problems.append(label)
    return problems


def validate_age(age: int, who: str = "personagem") -> None:
    """Levanta ValueError se a idade declarada for menor que 18."""
    if age is None or age < MIN_AGE:
        raise ValueError(f"O {who} precisa ter {MIN_AGE} anos ou mais.")


def validate_texts(*texts: str) -> None:
    """Levanta ValueError se algum texto indicar menor de idade."""
    found: List[str] = []
    for text in texts:
        for p in find_problems(text or ""):
            if p not in found:
                found.append(p)
    if found:
        raise ValueError(
            "Conteúdo bloqueado: o texto indica menor de idade ou aparência infantil "
            f"({', '.join(found)}). Todos os personagens devem ser adultos (18+)."
        )


# Sempre vai no negative prompt do SD, em qualquer configuração.
SD_ALWAYS_NEGATIVE = "child, loli, shota, young, underage, teen, kid, infant, baby face, flat chest child"
# Sempre vai no prompt positivo.
SD_ALWAYS_POSITIVE = "adult, mature"
