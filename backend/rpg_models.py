"""
Modelos de dados do sistema RPG.

Três modos de jogo:
- NARRATIVE: pura história, sem mecânicas
- MEDIUM: raça + classe, tracker de relacionamento, inventário simples
- FULL: tudo acima + atributos D&D, HP, XP/level, quests, rolagem de dados

Atributos seguem o padrão D&D 5e adaptado (3-20):
STR, DEX, CON, INT, WIS, CHA
Cada um gera um modifier: (valor - 10) // 2
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from enum import Enum


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class GameMode(str, Enum):
    NARRATIVE = "narrative"   # Só história
    MEDIUM    = "medium"      # Raça + classe + relacionamento
    FULL      = "full"        # Sistema completo


class QuestStatus(str, Enum):
    ACTIVE    = "active"
    COMPLETED = "completed"
    FAILED    = "failed"


# ─── RAÇAS E CLASSES ──────────────────────────────────────────────────────────

RACES = {
    "humano":     {"bonus": {"STR":1,"DEX":1,"CON":1,"INT":1,"WIS":1,"CHA":1}, "penalty": {},
                  "trait": "Sem talento óbvio e, por isso mesmo, imprevisível.", "desc": "+1 em todos os atributos."},
    "elfo":       {"bonus": {"INT":1,"DEX":2}, "penalty": {"CON":-1},
                  "trait": "Reflexo rápido, ouvido fino e a paciência de quem vive demais.", "desc": "+2 DES, +1 INT, -1 CON."},
    "meio-elfo":  {"bonus": {"CHA":2,"DEX":1}, "penalty": {},
                  "trait": "Entra em qualquer conversa e sai sem inimigo.", "desc": "+2 CAR, +1 DES."},
    "draconato":  {"bonus": {"STR":2,"CHA":1}, "penalty": {"DEX":-1},
                  "trait": "Escama, orgulho e um sopro que ninguém convidou.", "desc": "+2 FOR, +1 CAR, -1 DES."},
    "tiefling":   {"bonus": {"INT":1,"CHA":2}, "penalty": {"WIS":-1},
                  "trait": "Chifre e fama. Ninguém confia, todo mundo olha.", "desc": "+2 CAR, +1 INT, -1 SAB."},
    "drow":       {"bonus": {"DEX":2,"CHA":1}, "penalty": {"CON":-1},
                  "trait": "Criado no escuro. Bom em sumir, melhor em cobrar.", "desc": "+2 DES, +1 CAR, -1 CON."},
    "vampiro":    {"bonus": {"CHA":2,"INT":1}, "penalty": {"WIS":-1},
                  "trait": "Eterno, elegante e sempre com fome de alguma coisa.", "desc": "+2 CAR, +1 INT, -1 SAB."},
    "orc":        {"bonus": {"STR":3,"CON":1}, "penalty": {"INT":-1,"CHA":-1},
                  "trait": "Faz o que o corpo manda, e o corpo manda muito.", "desc": "+3 FOR, +1 CON, -1 INT, -1 CAR."},
    "celestial":  {"bonus": {"WIS":2,"CHA":1}, "penalty": {},
                  "trait": "Um fiapo de divindade que ele jura não notar.", "desc": "+2 SAB, +1 CAR."},
    "licantropo": {"bonus": {"STR":2,"CON":2}, "penalty": {"INT":-1,"CHA":-1},
                  "trait": "Calmo até a lua mudar de ideia.", "desc": "+2 FOR, +2 CON, -1 INT, -1 CAR."},
    "humano-aug": {"bonus": {"INT":1,"DEX":1}, "penalty": {"WIS":-1},
                  "trait": "Metade carne, metade assinatura de fabricante.", "desc": "+1 INT, +1 DES, -1 SAB."},
    "sintético":  {"bonus": {"INT":2,"CON":1}, "penalty": {"CHA":-2},
                  "trait": "Pensa depressa, sente devagar e ainda aprende a diferença.", "desc": "+2 INT, +1 CON, -2 CAR."},
    "cambion":    {"bonus": {"CHA":2,"INT":1}, "penalty": {"WIS":-1},
                  "trait": "Sangue de um acordo que a mãe nunca contou.", "desc": "+2 CAR, +1 INT, -1 SAB."},
    "revenante":  {"bonus": {"CON":2,"STR":1}, "penalty": {"CHA":-2},
                  "trait": "Morreu, voltou e ainda não decidiu se foi um favor.", "desc": "+2 CON, +1 FOR, -2 CAR."},
}

CLASSES = {
    "guerreiro":  {"hp_base":10,"hit_die":10,"primary":["STR","CON"],"saves":["STR","CON"],
                  "desc":"Aprendeu com ferro e lama. Aguenta pancada e devolve com juros."},
    "mago":       {"hp_base":6, "hit_die":6, "primary":["INT","WIS"],"saves":["INT","WIS"],
                  "desc":"Estuda o impossível com a saúde de quem passa a vida num livro."},
    "ladino":     {"hp_base":8, "hit_die":8, "primary":["DEX","INT"],"saves":["DEX","INT"],
                  "desc":"Chega antes, sai depois e leva o que ninguém notou que faltava."},
    "paladino":   {"hp_base":10,"hit_die":10,"primary":["STR","CHA"],"saves":["WIS","CHA"],
                  "desc":"Fez um juramento sério demais para a própria tranquilidade."},
    "ranger":     {"hp_base":8, "hit_die":8, "primary":["DEX","WIS"],"saves":["STR","DEX"],
                  "desc":"Rastro, arco e silêncio. Mais à vontade no mato do que numa mesa."},
    "bardo":      {"hp_base":8, "hit_die":8, "primary":["CHA","DEX"],"saves":["DEX","CHA"],
                  "desc":"Resolve com a voz o que os outros resolvem com a espada, e erra menos."},
    "clérigo":    {"hp_base":8, "hit_die":8, "primary":["WIS","CHA"],"saves":["WIS","CHA"],
                  "desc":"Cura quem dá e enterra quem não deu."},
    "druida":     {"hp_base":8, "hit_die":8, "primary":["WIS","CON"],"saves":["INT","WIS"],
                  "desc":"Fala com o que cresce, e o que cresce responde."},
    "bárbaro":    {"hp_base":12,"hit_die":12,"primary":["STR","CON"],"saves":["STR","CON"],
                  "desc":"Quando perde a paciência, perde junto o medo e a dor."},
    "feiticeiro": {"hp_base":6, "hit_die":6, "primary":["CHA","CON"],"saves":["CON","CHA"],
                  "desc":"O poder veio no sangue, sem pedir licença nem manual."},
    "netrunner":  {"hp_base":6, "hit_die":6, "primary":["INT","DEX"],"saves":["INT","DEX"],
                  "desc":"Mora na Rede e visita o corpo quando lembra de comer."},
    "mercenário": {"hp_base":10,"hit_die":10,"primary":["STR","DEX"],"saves":["STR","CON"],
                  "desc":"Cobra adiantado, entrega no prazo e não pergunta de quem é o alvo."},
    "fantasma":   {"hp_base":8, "hit_die":8, "primary":["DEX","CHA"],"saves":["DEX","CHA"],
                  "desc":"Ninguém lembra o rosto. Foi para isso que treinou."},
}


# ─── ATRIBUTOS ────────────────────────────────────────────────────────────────

class Attributes(BaseModel):
    STR: int = Field(10, ge=3, le=20, description="Força")
    DEX: int = Field(10, ge=3, le=20, description="Destreza")
    CON: int = Field(10, ge=3, le=20, description="Constituição")
    INT: int = Field(10, ge=3, le=20, description="Inteligência")
    WIS: int = Field(10, ge=3, le=20, description="Sabedoria")
    CHA: int = Field(10, ge=3, le=20, description="Carisma")

    def modifier(self, attr: str) -> int:
        """Modifier D&D: (valor - 10) // 2"""
        return (getattr(self, attr) - 10) // 2

    def modifier_str(self, attr: str) -> str:
        m = self.modifier(attr)
        return f"+{m}" if m >= 0 else str(m)


# ─── INVENTÁRIO ───────────────────────────────────────────────────────────────

class Item(BaseModel):
    name: str
    description: str = ""
    quantity: int = 1
    type: str = "misc"  # weapon, armor, potion, misc, key


class Inventory(BaseModel):
    items: List[Item] = []
    gold: int = 0

    def add_item(self, item: Item):
        for existing in self.items:
            if existing.name.lower() == item.name.lower():
                existing.quantity += item.quantity
                return
        self.items.append(item)

    def remove_item(self, name: str, quantity: int = 1) -> bool:
        for i, item in enumerate(self.items):
            if item.name.lower() == name.lower():
                if item.quantity <= quantity:
                    self.items.pop(i)
                else:
                    item.quantity -= quantity
                return True
        return False


# ─── QUESTS ───────────────────────────────────────────────────────────────────

class Quest(BaseModel):
    id: str
    title: str
    description: str
    status: QuestStatus = QuestStatus.ACTIVE
    objectives: List[str] = []
    completed_objectives: List[str] = []
    reward_xp: int = 0
    reward_gold: int = 0
    reward_items: List[str] = []


# ─── RELACIONAMENTO ───────────────────────────────────────────────────────────

class Relationship(BaseModel):
    score: int = Field(50, ge=0, le=100)
    label: str = "Neutro"   # calculado, incluído na serialização
    color: str = "#9090a8"  # calculado, incluído na serialização

    def model_post_init(self, __context) -> None:
        """Atualiza label e color após qualquer mudança no score."""
        self._recalculate()

    def _recalculate(self):
        if self.score <= 20:
            object.__setattr__(self, 'label', 'Hostil');     object.__setattr__(self, 'color', '#e05555')
        elif self.score <= 40:
            object.__setattr__(self, 'label', 'Desconfiado'); object.__setattr__(self, 'color', '#e09055')
        elif self.score <= 60:
            object.__setattr__(self, 'label', 'Neutro');      object.__setattr__(self, 'color', '#9090a8')
        elif self.score <= 80:
            object.__setattr__(self, 'label', 'Amigável');    object.__setattr__(self, 'color', '#4caf82')
        else:
            object.__setattr__(self, 'label', 'Íntimo');      object.__setattr__(self, 'color', '#9b7de0')

    def set_score(self, value: int) -> None:
        """Atualiza score e recalcula label/color."""
        object.__setattr__(self, 'score', max(0, min(100, value)))
        self._recalculate()


# ─── PLAYER ───────────────────────────────────────────────────────────────────

class PlayerStats(BaseModel):
    # Identidade
    name: str = "Aventureiro"
    race: str = "humano"
    char_class: str = "guerreiro"
    age: int = 25
    appearance: str = ""
    level: int = 1
    xp: int = 0
    xp_next: int = 300  # XP para o próximo nível

    # Atributos (só no modo FULL)
    attributes: Optional[Attributes] = None

    # HP
    hp_max: int = 10
    hp_current: int = 10

    # Inventário (médio e completo)
    inventory: Inventory = Inventory()

    # Quests (só completo)
    quests: List[Quest] = []

    # Relacionamento com o personagem
    relationship: Relationship = Relationship()

    def xp_progress_pct(self) -> int:
        return min(100, int((self.xp / self.xp_next) * 100))

    def add_xp(self, amount: int) -> bool:
        """Adiciona XP e retorna True se subiu de nível."""
        self.xp += amount
        if self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.xp_next = int(self.xp_next * 1.5)
            # Aumenta HP no level up
            self.hp_max += 5
            self.hp_current = min(self.hp_current + 5, self.hp_max)
            return True
        return False


# ─── ESTADO COMPLETO DA SESSÃO RPG ────────────────────────────────────────────

class RPGState(BaseModel):
    mode: GameMode = GameMode.NARRATIVE
    player: Optional[PlayerStats] = None
    # Relação do jogador com cada integrante do elenco (só personagens de grupo)
    cast_relations: Dict[str, Relationship] = {}
    # Log de eventos importantes (rolagens, level ups, etc.)
    event_log: List[str] = []


# ─── REQUESTS ─────────────────────────────────────────────────────────────────

class CreatePlayerRequest(BaseModel):
    session_id: str
    name: str = Field(min_length=1, max_length=40)
    race: str
    char_class: str
    mode: GameMode
    age: int = 25
    appearance: str = Field(default="", max_length=400)
    attributes: Optional[Dict[str, int]] = None

    @field_validator("age")
    @classmethod
    def _adult_only(cls, v: int) -> int:
        from backend.safety import validate_age
        validate_age(v, "personagem do jogador")
        return v

    @field_validator("appearance", "name")
    @classmethod
    def _no_minor_markers(cls, v: str) -> str:
        from backend.safety import validate_texts
        validate_texts(v)
        return v


class UpdateRelationshipRequest(BaseModel):
    session_id: str
    delta: int  # positivo ou negativo


class AddQuestRequest(BaseModel):
    session_id: str
    title: str
    description: str
    objectives: List[str] = []
    reward_xp: int = 100
    reward_gold: int = 0
