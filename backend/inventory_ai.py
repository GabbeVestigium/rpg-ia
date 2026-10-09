"""
Inventário que acompanha a história.

Depois de cada resposta (modos Médio e Completo) o modelo lê a cena e diz o que o jogador
ganhou, perdeu ou gastou. Só chamamos o modelo quando o texto parece falar de itens ou ouro,
para não gastar uma segunda geração em toda mensagem.
"""

import json
import re
from typing import Dict, List, Optional

from backend.ollama_client import OllamaError, complete
from backend.rpg_models import Inventory, Item

# Prefixos que sugerem troca de itens (entreg-a, receb-eu, compr-ou...). Só um filtro barato.
_TRIGGER = re.compile(
    r"\b(entreg|te d[aáo]\b|d[aá] (a )?voc|dou |dei |pega|pegou|peguei|pego |ganh|receb|compr|vend|achou|achei|encontr"
    r"|perd|gast|pag[ao]|moeda|ouro|cr[eé]dito|presente|ofere|roub|furt|saque|guarda|enfia no bolso|item)",
    re.IGNORECASE,
)

_ALLOWED_TYPES = {"weapon", "armor", "potion", "key", "misc"}

_SYSTEM = (
    "Você acompanha o inventário de um jogo de roleplay. Leia a cena e responda SOMENTE um JSON, sem texto extra, "
    'neste formato: {"gain":[{"name":"...","qty":1,"type":"weapon|armor|potion|key|misc"}],'
    '"lose":[{"name":"...","qty":1}],"gold":0}. '
    "Inclua só mudanças CLARAS no inventário do JOGADOR nesta cena: algo que ele recebeu, pegou, comprou, achou, "
    "perdeu, gastou ou entregou. Ouro ganho é positivo e gasto é negativo. Não conte itens apenas mencionados, "
    "vistos, oferecidos e recusados, ou que pertencem a outros personagens. Nomes de itens curtos, em português. "
    'Se nada mudou, responda {"gain":[],"lose":[],"gold":0}.'
)

MAX_PER_TURN = 3
MAX_GOLD = 500


def looks_like_item_change(*texts: str) -> bool:
    return any(_TRIGGER.search(t or "") for t in texts)


def parse_changes(raw: str) -> Dict:
    """Extrai o JSON da resposta do modelo (que às vezes vem com texto em volta) e limpa os campos."""
    start, end = raw.find("{"), raw.rfind("}")
    empty = {"gain": [], "lose": [], "gold": 0}
    if start < 0 or end <= start:
        return empty
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict):
        return empty

    def clean_name(value) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip(" .,;:")[:40]

    def clean_qty(value) -> int:
        try:
            return max(1, min(20, int(value)))
        except (TypeError, ValueError):
            return 1

    gain, lose = [], []
    for g in (data.get("gain") if isinstance(data.get("gain"), list) else [])[:MAX_PER_TURN]:
        if isinstance(g, dict) and clean_name(g.get("name")):
            kind = str(g.get("type", "misc")).lower()
            gain.append({"name": clean_name(g["name"]), "qty": clean_qty(g.get("qty")),
                         "type": kind if kind in _ALLOWED_TYPES else "misc"})
    for l in (data.get("lose") if isinstance(data.get("lose"), list) else [])[:MAX_PER_TURN]:
        if isinstance(l, dict) and clean_name(l.get("name")):
            lose.append({"name": clean_name(l["name"]), "qty": clean_qty(l.get("qty"))})
    try:
        gold = max(-MAX_GOLD, min(MAX_GOLD, int(data.get("gold", 0))))
    except (TypeError, ValueError):
        gold = 0
    return {"gain": gain, "lose": lose, "gold": gold}


async def extract_changes(user_text: str, reply: str) -> Dict:
    """Pergunta ao modelo o que mudou no inventário nesta troca. Falhas viram 'nada mudou'."""
    prompt = f"Jogador disse: {user_text[:600]}\n\nResposta da cena: {reply[:1800]}\n\nJSON:"
    try:
        raw = await complete(prompt, system=_SYSTEM, num_predict=160, temperature=0.1)
    except OllamaError:
        return {"gain": [], "lose": [], "gold": 0}
    return parse_changes(raw)


def _find(inv: Inventory, name: str) -> Optional[Item]:
    """Item do inventário com esse nome (exato, senão um que contém o nome ou vice-versa)."""
    low = name.lower()
    for item in inv.items:
        if item.name.lower() == low:
            return item
    for item in inv.items:
        n = item.name.lower()
        if low in n or n in low:
            return item
    return None


def apply_changes(inv: Inventory, changes: Dict) -> Optional[Dict]:
    """
    Aplica as mudanças e devolve o que realmente aconteceu (para mostrar e para poder desfazer),
    ou None se nada mudou. Perder um item que o jogador não tem não faz nada.
    """
    done = {"gain": [], "lose": [], "gold": 0}
    for g in changes.get("gain", []):
        inv.add_item(Item(name=g["name"], quantity=g["qty"], type=g["type"]))
        done["gain"].append({"name": g["name"], "qty": g["qty"], "type": g["type"]})
    for l in changes.get("lose", []):
        item = _find(inv, l["name"])
        if item:
            qty = min(l["qty"], item.quantity)
            done["lose"].append({"name": item.name, "qty": qty, "type": item.type})
            inv.remove_item(item.name, qty)
    gold = changes.get("gold", 0)
    if gold:
        new_total = max(0, inv.gold + gold)
        done["gold"] = new_total - inv.gold
        inv.gold = new_total
    return done if (done["gain"] or done["lose"] or done["gold"]) else None


def revert_changes(inv: Inventory, done: Dict) -> None:
    """Desfaz o que apply_changes fez (usado quando a troca é desfeita ou regenerada)."""
    for g in done.get("gain", []):
        inv.remove_item(g["name"], g["qty"])
    for l in done.get("lose", []):
        inv.add_item(Item(name=l["name"], quantity=l["qty"], type=l.get("type", "misc")))
    if done.get("gold"):
        inv.gold = max(0, inv.gold - done["gold"])


def describe(done: Dict) -> List[str]:
    """Linhas legíveis para o aviso na tela."""
    lines = [f"+ {g['name']}" + (f" x{g['qty']}" if g["qty"] > 1 else "") for g in done["gain"]]
    lines += [f"- {l['name']}" + (f" x{l['qty']}" if l["qty"] > 1 else "") for l in done["lose"]]
    if done["gold"]:
        lines.append(f"{'+' if done['gold'] > 0 else ''}{done['gold']} ouro")
    return lines
