"""
Modelos Pydantic — estruturas de dados da aplicação.
Pydantic valida automaticamente os tipos, o que evita bugs silenciosos.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    role: MessageRole
    content: str


class CastMember(BaseModel):
    """Integrante do elenco de um personagem de grupo, com relação própria com o jogador."""
    id: str                        # identificador estável (chave do medidor)
    name: str                      # primeiro nome, como aparece nas falas ("Yasmin")
    aliases: List[str] = []        # como o jogador pode chamá-la ("maga", "irmã")
    start: int = 50                # relação inicial, 0 a 100


class Character(BaseModel):
    id: str
    name: str
    world_id: str = ""
    age: int = 25                  # Obrigatório 18+ (validado em safety.py)
    gender: str = "female"         # female / male / other (usado nas imagens)
    summary: str = ""              # Resumo curto para o card da galeria (opcional)
    description: str               # Aparência, personalidade geral
    personality: str               # Como ela fala, reage, o que gosta/odeia
    scenario: str                  # Contexto inicial da história
    first_message: str             # Primeira mensagem que o personagem manda
    example_dialogue: str = ""     # Trechos de fala de exemplo (calibra o estilo)
    appearance_tags: str = ""      # Tags em inglês para o SD ("silver hair, violet eyes")
    group: bool = False            # True: o narrador interpreta um elenco (ex: harém)
    cast: List[CastMember] = []    # Elenco de um personagem de grupo (medidor de relação por pessoa)
    avatar_emoji: str = "👤"       # Emoji de avatar
    tags: List[str] = []


class LoreEntry(BaseModel):
    """Fato do mundo que só entra no prompt quando a conversa toca no assunto."""
    id: str = ""
    name: str                      # título curto ("Cova de Tarsa")
    keys: List[str] = []           # palavras que ativam a entrada ("cova", "tarsa")
    text: str                      # o fato em si, 1 a 3 frases
    always: bool = False           # True: entra em todo prompt (gasta contexto)


class World(BaseModel):
    id: str
    name: str
    description: str
    genre: str = ""                # fantasy, sci-fi, romance, horror, etc.
    lore: str = ""                 # Núcleo do mundo, sempre no prompt (mantenha curto)
    entries: List[LoreEntry] = []  # Livro de fatos: entram só quando a conversa os cita


class ChatRequest(BaseModel):
    session_id: str
    character_id: str
    message: str = Field(min_length=1, max_length=4000)


class RegenerateRequest(BaseModel):
    session_id: str
    character_id: str


class EditMessageRequest(BaseModel):
    session_id: str
    index: int
    content: str = Field(min_length=1, max_length=8000)


class SwipeRequest(BaseModel):
    session_id: str
    delta: int                     # -1 versão anterior, +1 próxima


class NewSessionRequest(BaseModel):
    character_id: str


class SceneImage(BaseModel):
    url: str
    at: int                        # len(history) no momento da geração
    prompt: str = ""


class SessionData(BaseModel):
    session_id: str
    character_id: str
    history: List[Message] = []
    rpg_state: Optional[Any] = None  # RPGState — importado dinamicamente para evitar circular
    summary: str = ""                # Resumo da história que já saiu da janela de contexto
    summarized_upto: int = 0         # Quantas mensagens do histórico o resumo já cobre
    images: List[SceneImage] = []    # Cenas geradas durante o chat
    swipes: List[str] = []           # Versões da última resposta (🔄 guarda as anteriores)
    swipe_index: int = 0             # Qual versão está no histórico agora
    swipe_for: int = -1              # Índice da mensagem a que as versões pertencem


class ChatResponse(BaseModel):
    session_id: str
    response: str
