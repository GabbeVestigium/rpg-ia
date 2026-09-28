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


class Character(BaseModel):
    id: str
    name: str
    world_id: str
    description: str           # Aparência, personalidade geral
    personality: str           # Como ela fala, reage, o que gosta/odeia
    scenario: str              # Contexto inicial da história
    first_message: str         # Primeira mensagem que o personagem manda
    avatar_emoji: str = "👤"   # Emoji de avatar (simples por agora)
    tags: List[str] = []


class World(BaseModel):
    id: str
    name: str
    description: str
    genre: str                 # fantasy, sci-fi, romance, horror, etc.
    lore: str                  # Regras e contexto do mundo


class ChatRequest(BaseModel):
    session_id: str
    character_id: str
    message: str


class NewSessionRequest(BaseModel):
    character_id: str


class SessionData(BaseModel):
    session_id: str
    character_id: str
    history: List[Message] = []
    rpg_state: Optional[Any] = None  # RPGState — importado dinamicamente para evitar circular


class ChatResponse(BaseModel):
    session_id: str
    response: str
