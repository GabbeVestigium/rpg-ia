"""
Gerenciador de personagens e mundos (arquivos JSON em data/).

Todo personagem salvo passa por validação de adulto (18+), ver safety.py.
"""

import os
from typing import List, Optional

from pydantic import ValidationError

from backend.config import CHARACTERS_DIR, WORLDS_DIR, PORTRAITS_DIR
from backend.models import Character, World
from backend.safety import validate_age, validate_texts
from backend.storage import is_safe_id, read_json, slugify, write_json_atomic


def _char_path(character_id: str) -> str:
    return os.path.join(CHARACTERS_DIR, f"{character_id}.json")


def _world_path(world_id: str) -> str:
    return os.path.join(WORLDS_DIR, f"{world_id}.json")


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "..."


def _auto_summary(description: str) -> str:
    """Resumo automático para cards: primeira frase, sem marcação markdown."""
    import re
    plain = re.sub(r"[*_#>`]", "", description).replace("\n", " ").strip()
    first = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0]
    return _shorten(first, 180)


# ─── PERSONAGENS ──────────────────────────────────────────────────────────────

def load_character(character_id: str) -> Optional[Character]:
    if not is_safe_id(character_id):
        return None
    data = read_json(_char_path(character_id))
    if not isinstance(data, dict):
        return None
    try:
        return Character(**data)
    except ValidationError:
        return None


def validate_character(character: Character) -> None:
    """Levanta ValueError se o personagem não cumprir a regra 18+."""
    validate_age(character.age, "personagem")
    validate_texts(
        character.name, character.description, character.personality,
        character.scenario, character.first_message, character.example_dialogue,
        character.appearance_tags, " ".join(character.tags),
    )


def save_character(character: Character) -> Character:
    if not is_safe_id(character.id):
        raise ValueError("id do personagem inválido")
    validate_character(character)
    write_json_atomic(_char_path(character.id), character.model_dump(mode="json"))
    return character


def delete_character(character_id: str) -> bool:
    if not is_safe_id(character_id):
        return False
    path = _char_path(character_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    portrait = os.path.join(PORTRAITS_DIR, f"{character_id}.png")
    if os.path.exists(portrait):
        os.remove(portrait)
    return True


def list_characters() -> List[dict]:
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    characters = []
    for fname in sorted(os.listdir(CHARACTERS_DIR)):
        if not fname.endswith(".json"):
            continue
        data = read_json(os.path.join(CHARACTERS_DIR, fname))
        if not isinstance(data, dict):
            continue
        try:
            c = Character(**data)
        except ValidationError:
            continue
        characters.append({
            "id":           c.id,
            "name":         c.name,
            "world_id":     c.world_id,
            "age":          c.age,
            "summary":      c.summary or _auto_summary(c.description),
            "scenario":     _shorten(c.scenario, 200),
            "avatar_emoji": c.avatar_emoji,
            "tags":         c.tags,
            "has_portrait": os.path.exists(os.path.join(PORTRAITS_DIR, f"{c.id}.png")),
        })
    return characters


# ─── MUNDOS ───────────────────────────────────────────────────────────────────

def load_world(world_id: str) -> Optional[World]:
    if not world_id or not is_safe_id(world_id):
        return None
    data = read_json(_world_path(world_id))
    if not isinstance(data, dict):
        return None
    try:
        return World(**data)
    except ValidationError:
        return None


def save_world(world: World) -> World:
    if not is_safe_id(world.id):
        raise ValueError("id do mundo inválido")
    validate_texts(world.name, world.description, world.lore)
    for i, entry in enumerate(world.entries):
        validate_texts(entry.name, entry.text, " ".join(entry.keys))
        entry.id = entry.id or f"{slugify(entry.name)}-{i + 1}"
    write_json_atomic(_world_path(world.id), world.model_dump(mode="json"))
    return world


def list_worlds() -> List[dict]:
    os.makedirs(WORLDS_DIR, exist_ok=True)
    worlds = []
    for fname in sorted(os.listdir(WORLDS_DIR)):
        if not fname.endswith(".json"):
            continue
        data = read_json(os.path.join(WORLDS_DIR, fname))
        if not isinstance(data, dict):
            continue
        try:
            w = World(**data)
        except ValidationError:
            continue
        desc = w.description
        worlds.append({
            "id":          w.id,
            "name":        w.name,
            "genre":       w.genre,
            "description": desc if len(desc) <= 120 else desc[:120] + "...",
        })
    return worlds
