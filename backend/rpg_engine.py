"""
RPG Engine — mecânicas do sistema de jogo.

Responsabilidades:
- Rolagem de dados (d4, d6, d8, d10, d12, d20, d100)
- Resolução de ações com modificadores de atributos
- Cálculo de HP, stats derivados
- Detecção de ações de risco no texto do jogador
- Geração de contexto RPG para o system prompt
- Aplicação de bônus de raça
"""

import random
import re
from typing import Optional, Tuple
from backend.rpg_models import (
    PlayerStats, Attributes, RPGState, GameMode,
    RACES, CLASSES, Item, Quest, QuestStatus
)


# ─── DADOS ────────────────────────────────────────────────────────────────────

def roll(sides: int, count: int = 1) -> Tuple[int, list]:
    """Rola `count` dados de `sides` lados. Retorna total e lista de resultados."""
    results = [random.randint(1, sides) for _ in range(count)]
    return sum(results), results


def roll_d20(modifier: int = 0) -> dict:
    """
    Rolagem de d20 com modificador.
    Resultado:
    - 1: falha crítica
    - 20: sucesso crítico
    - < 8: falha
    - 8-11: falha parcial
    - 12-16: sucesso parcial
    - 17+: sucesso total
    """
    total, [natural] = roll(20)
    final = max(1, total + modifier)
    
    if natural == 1:
        outcome = "falha_critica"
        label = "Falha Crítica!"
    elif natural == 20:
        outcome = "sucesso_critico"
        label = "Sucesso Crítico!"
    elif final <= 7:
        outcome = "falha"
        label = "Falha"
    elif final <= 11:
        outcome = "falha_parcial"
        label = "Falha Parcial"
    elif final <= 16:
        outcome = "sucesso_parcial"
        label = "Sucesso Parcial"
    else:
        outcome = "sucesso"
        label = "Sucesso!"

    return {
        "natural": natural,
        "modifier": modifier,
        "final": final,
        "outcome": outcome,
        "label": label
    }


# ─── CRIAÇÃO DE PERSONAGEM ────────────────────────────────────────────────────

def create_player(
    name: str,
    race: str,
    char_class: str,
    mode: GameMode,
    custom_attributes: Optional[dict] = None,
    age: int = 25,
    appearance: str = ""
) -> PlayerStats:
    """
    Cria o PlayerStats inicial baseado em raça, classe e modo.
    
    Modo MEDIUM: raça + classe definem só o flavor, sem atributos numéricos.
    Modo FULL: atributos completos com bônus de raça aplicados.
    """
    race_data  = RACES.get(race, RACES["humano"])
    class_data = CLASSES.get(char_class, CLASSES["guerreiro"])

    player = PlayerStats(
        name=name,
        race=race,
        char_class=char_class,
        age=age,
        appearance=appearance,
        hp_max=class_data["hp_base"],
        hp_current=class_data["hp_base"],
    )

    if mode == GameMode.FULL:
        # Atributos base: padrão array D&D (15,14,13,12,10,8) ou customizados
        base = custom_attributes or {
            "STR": 10, "DEX": 10, "CON": 10,
            "INT": 10, "WIS": 10, "CHA": 10
        }
        attrs = Attributes(**base)

        # Aplica bônus de raça (o RACES["humano"] já tem +1 em tudo definido)
        for attr, bonus in race_data["bonus"].items():
            current = getattr(attrs, attr)
            setattr(attrs, attr, min(20, current + bonus))

        # Aplica penalidades de raça
        for attr, penalty in race_data.get("penalty", {}).items():
            current = getattr(attrs, attr)
            setattr(attrs, attr, max(3, current + penalty))

        # HP base = hp_classe + modifier de CON
        con_mod = attrs.modifier("CON")
        player.hp_max = max(1, class_data["hp_base"] + con_mod)
        player.hp_current = player.hp_max
        player.attributes = attrs

    # Inventário inicial por classe
    starter_items = _get_starter_items(char_class)
    for item in starter_items:
        player.inventory.add_item(item)
    player.inventory.gold = random.randint(10, 50)

    return player


def _get_starter_items(char_class: str) -> list:
    starters = {
        "guerreiro":  [Item(name="Espada longa",   type="weapon", description="Lâmina de aço bem equilibrada"),
                       Item(name="Escudo de madeira", type="armor")],
        "mago":       [Item(name="Cajado de carvalho", type="weapon"),
                       Item(name="Livro de magias", type="misc", description="Contém seus feitiços iniciais")],
        "ladino":     [Item(name="Adaga",  type="weapon", quantity=2),
                       Item(name="Kit de ladrão", type="misc")],
        "paladino":   [Item(name="Maça de guerra", type="weapon"),
                       Item(name="Armadura de couro", type="armor")],
        "ranger":     [Item(name="Arco curto", type="weapon"),
                       Item(name="Aljava com 20 flechas", type="misc")],
        "bardo":      [Item(name="Alaúde", type="misc"),
                       Item(name="Rapieira", type="weapon")],
        "clérigo":    [Item(name="Símbolo sagrado", type="misc"),
                       Item(name="Maça", type="weapon")],
        "druida":     [Item(name="Cajado de teixo", type="weapon"),
                       Item(name="Foco druídico", type="misc")],
        "bárbaro":    [Item(name="Machadão", type="weapon", description="Duas mãos, dano brutal"),
                       Item(name="Peles de urso", type="armor")],
        "feiticeiro": [Item(name="Componentes arcanos", type="misc"),
                       Item(name="Adaga", type="weapon")],
        "netrunner":  [Item(name="Deck de hacking", type="misc", description="Interface neural portátil"),
                       Item(name="Pistola smart", type="weapon")],
        "mercenário": [Item(name="Fuzil de assalto", type="weapon"),
                       Item(name="Colete balístico", type="armor")],
        "fantasma":   [Item(name="Faca monofilamento", type="weapon"),
                       Item(name="Disfarce holográfico", type="misc")],
    }
    return starters.get(char_class, [Item(name="Faca", type="weapon")])


# ─── DETECÇÃO DE AÇÕES DE RISCO ───────────────────────────────────────────────

# Palavras-chave que indicam ação com risco de falha
RISK_KEYWORDS = [
    # Combate
    r"\batac[oa]\b", r"\bgolp[eo]\b", r"\bcort[oa]\b", r"\bfur[ao]\b",
    r"\bdisparo\b", r"\bchut[oa]\b", r"\bsoc[ao]\b", r"\bdesarm[ao]\b",
    # Furtividade
    r"\besconco\b", r"\bfurto\b", r"\broubo\b", r"\bescal[ao]\b",
    r"\bme escondi\b", r"\bfugi\b", r"\bdesapareço\b",
    # Persuasão/Enganação
    r"\bconvenço\b", r"\bseduz[oa]\b", r"\bengano\b", r"\bminto\b",
    r"\bpersuado\b", r"\bameaço\b", r"\bintimido\b",
    # Magia/Habilidade
    r"\bcast[oa]\b", r"\bconjur[ao]\b", r"\buso.*magia\b", r"\blanço\b",
    r"\bhack[eo]?\b", r"\binvado\b", r"\barrombo\b",
    # Físico
    r"\bpulo\b", r"\bsalto\b", r"\bnadar\b", r"\bescalo\b", r"\bespremo\b",
    r"\bquebr[ao]\b", r"\barrombo\b", r"\bforço\b",
    # Inglês (para quem mistura)
    r"\battack\b", r"\bstrike\b", r"\bsneak\b", r"\bpersuade\b",
]

COMPILED_RISK = [re.compile(p, re.IGNORECASE) for p in RISK_KEYWORDS]

# Mapeamento de tipo de ação para atributo relevante
ACTION_ATTRIBUTE_MAP = {
    "atac": "STR", "golp": "STR", "cort": "STR", "fur": "DEX",
    "dispar": "DEX", "chut": "STR", "soc": "STR", "desarmo": "STR",
    "escond": "DEX", "furto": "DEX", "roubo": "DEX", "escal": "DEX",
    "convenc": "CHA", "seduz": "CHA", "engano": "CHA", "minto": "CHA",
    "persuad": "CHA", "ameac": "CHA", "intimid": "CHA",
    "conjur": "INT", "magia": "INT", "lanc": "INT",
    "hack": "INT", "invad": "INT", "arrombo": "DEX",
    "pulo": "DEX", "salto": "DEX", "nadar": "STR", "quebr": "STR",
}


def detect_risk_action(text: str) -> Optional[str]:
    """
    Detecta se a mensagem contém uma ação de risco.
    Retorna o atributo relevante para a rolagem, ou None.
    """
    text_lower = text.lower()
    for pattern in COMPILED_RISK:
        if pattern.search(text_lower):
            # Tenta identificar o atributo relevante
            for keyword, attr in ACTION_ATTRIBUTE_MAP.items():
                if keyword in text_lower:
                    return attr
            return "STR"  # padrão se não identificar
    return None


def get_roll_modifier(player: PlayerStats, attribute: str) -> int:
    """Retorna o modifier do atributo + bônus de proficiência por nível."""
    if not player.attributes:
        return 0
    base_mod = player.attributes.modifier(attribute)
    # Bônus de proficiência: +2 níveis 1-4, +3 níveis 5-8, +4 níveis 9-12...
    prof_bonus = 1 + (player.level // 4)
    return base_mod + prof_bonus


# ─── CONTEXTO RPG PARA O MODELO ───────────────────────────────────────────────

def build_rpg_context(state: RPGState, include_relationship: bool = True) -> str:
    """
    Monta o bloco de contexto RPG que vai no system prompt.
    O modelo usa isso para calibrar respostas — sabe o nível do jogador,
    o relacionamento atual, o que tem no inventário, quests ativas.
    """
    if state.mode == GameMode.NARRATIVE or not state.player:
        return ""

    p = state.player
    lines = ["\n## Estado atual do jogador (use isso para calibrar suas respostas):"]

    # Info básica
    age_str = f", {p.age} anos" if p.age else ""
    lines.append(f"- Nome: {p.name} | Raça: {p.race} | Classe: {p.char_class}{age_str} | Nível: {p.level}")
    if p.appearance:
        lines.append(f"- Aparência: {p.appearance}")

    # Relacionamento (personagens de grupo têm um medidor por integrante, ver build_cast_context)
    if include_relationship:
        rel = p.relationship
        lines.append(f"- Relacionamento com você: {rel.score}/100 ({rel.label})")
        lines.append(f"  Trate o jogador de acordo com esse nível. {_relationship_guidance(rel.score)}")

    if state.mode == GameMode.FULL and p.attributes:
        # HP
        lines.append(f"- HP: {p.hp_current}/{p.hp_max}")
        # Atributos resumidos
        a = p.attributes
        attrs = f"FOR:{a.STR}({a.modifier_str('STR')}) DES:{a.DEX}({a.modifier_str('DEX')}) CON:{a.CON}({a.modifier_str('CON')}) INT:{a.INT}({a.modifier_str('INT')}) SAB:{a.WIS}({a.modifier_str('WIS')}) CAR:{a.CHA}({a.modifier_str('CHA')})"
        lines.append(f"- Atributos: {attrs}")

    # Inventário relevante
    if p.inventory.items:
        items = ", ".join(f"{i.name}({i.quantity})" for i in p.inventory.items[:5])
        lines.append(f"- Inventário: {items}" + (" ..." if len(p.inventory.items) > 5 else ""))
    if p.inventory.gold > 0:
        lines.append(f"- Ouro: {p.inventory.gold}")

    # Quests ativas
    if state.mode == GameMode.FULL:
        active_quests = [q for q in p.quests if q.status == QuestStatus.ACTIVE]
        if active_quests:
            lines.append("- Missões ativas:")
            for q in active_quests[:3]:
                lines.append(f"  * {q.title}: {q.description[:80]}...")

    # Eventos recentes
    if state.event_log:
        lines.append(f"- Evento recente: {state.event_log[-1]}")

    return "\n".join(lines)


def build_cast_context(cast, relations) -> str:
    """Bloco do prompt com como cada integrante do elenco se sente em relação ao jogador."""
    if not cast or not relations:
        return ""
    lines = ["\n## Como cada uma se sente em relação ao jogador (cada uma age de acordo, sem sair da própria personalidade):"]
    for m in cast:
        rel = relations.get(m.id)
        if rel:
            lines.append(f"- {m.name}: {rel.score}/100 ({rel.label}). {_relationship_guidance(rel.score)}")
    return "\n".join(lines)


def _relationship_guidance(score: int) -> str:
    if score <= 20:
        return "Seja hostil, desconfiado ou agressivo. Não coopere facilmente."
    if score <= 40:
        return "Seja reservado e cético. Ajude pouco e com condições."
    if score <= 60:
        return "Seja neutro e profissional. Responda ao que for perguntado."
    if score <= 80:
        return "Seja caloroso e cooperativo. Demonstre afeição genuína."
    return "Seja íntimo e aberto. Compartilhe segredos. Flerte se apropriado."


# ─── XP E RELACIONAMENTO AUTO ────────────────────────────────────────────────

def calculate_xp_reward(outcome: str) -> int:
    """XP por resultado de rolagem."""
    rewards = {
        "sucesso_critico": 50,
        "sucesso": 25,
        "sucesso_parcial": 10,
        "falha_parcial": 5,
        "falha": 0,
        "falha_critica": 0,
    }
    return rewards.get(outcome, 0)


def auto_relationship_delta(message: str) -> int:
    """
    Analisa o tom da mensagem do jogador e sugere delta de relacionamento.
    Pequeno, para não dominar a narrativa.
    """
    positive = [r"\bobrigado\b", r"\bdesculp", r"\bagradeço\b", r"\bajudo\b",
                r"\bprotejo\b", r"\bconfio\b", r"\bgosto\b", r"\bquero\b"]
    negative = [r"\bameaço\b", r"\binsulto\b", r"\bidiota\b", r"\bburro\b",
                r"\btraio\b", r"\bminto\b", r"\bataco\b", r"\bódio\b"]

    text = message.lower()
    score = 0
    for p in positive:
        if re.search(p, text): score += 2
    for n in negative:
        if re.search(n, text): score -= 3
    return max(-10, min(10, score))


# ─── ELENCO (personagens de grupo) ────────────────────────────────────────────

def _fold(text: str) -> str:
    """Minúsculas e sem acento, para casar 'Zélia' com 'zelia'."""
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def match_cast(message: str, cast) -> list:
    """Ids dos integrantes citados pelo nome ou apelido na mensagem do jogador."""
    text = _fold(message)
    found = []
    for m in cast:
        for name in [m.name, *m.aliases]:
            if name and re.search(rf"\b{re.escape(_fold(name))}\b", text):
                found.append(m.id)
                break
    return found


def last_speaker(text: str, cast) -> Optional[str]:
    """Id de quem falou por último numa resposta (marcada como **Nome:**)."""
    by_name = {_fold(m.name): m.id for m in cast}
    speakers = re.findall(r"\*\*([^*:]{1,40}):\*\*", text)
    for name in reversed(speakers):
        folded = _fold(name)
        for key, cid in by_name.items():
            if key in folded:
                return cid
    return None


def cast_targets(message: str, previous_reply: str, cast) -> list:
    """Quem recebe o efeito da mensagem: os citados, ou senão quem acabou de falar."""
    named = match_cast(message, cast)
    if named:
        return named
    speaker = last_speaker(previous_reply, cast)
    return [speaker] if speaker else []


def cast_delta(message: str) -> int:
    """Efeito de uma mensagem sobre a relação: o tom das palavras, mais 1 só por dar atenção."""
    return max(-10, min(10, auto_relationship_delta(message) + 1))


def cast_summary(cast, relations) -> list:
    """Lista para a interface: um item por integrante, com nota e rótulo."""
    out = []
    for m in cast:
        rel = relations.get(m.id)
        if rel:
            out.append({"id": m.id, "name": m.name, "score": rel.score,
                        "label": rel.label, "color": rel.color})
    return out
