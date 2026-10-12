"""
Gerenciador de personagens e mundos (arquivos JSON em data/).

Todo personagem salvo passa por validação de adulto (18+), ver safety.py.
"""

import os
from typing import List, Optional

from pydantic import ValidationError

from backend.config import CHARACTERS_DIR, DATA_DIR, WORLDS_DIR, PORTRAITS_DIR
from backend.models import Character, World
from backend.safety import validate_age, validate_texts
from backend.storage import is_safe_id, log, read_json, slugify, write_json_atomic

# data/characters e data/worlds vêm com o projeto (versionados no git) e o app nunca os reescreve.
# O que o jogador cria ou edita vai para data/user/..., fora do git, e vale por cima do original
# com o mesmo id. Assim um "git pull" não briga com as edições e nada se perde.
USER_CHARACTERS_DIR = os.path.join(DATA_DIR, "user", "characters")
USER_WORLDS_DIR = os.path.join(DATA_DIR, "user", "worlds")


def _read_entry(user_dir: str, builtin_dir: str, item_id: str) -> Optional[dict]:
    """Dados do item: a cópia do jogador, se houver, senão a original. None se foi apagado."""
    user = os.path.join(user_dir, f"{item_id}.json")
    data = read_json(user if os.path.exists(user) else os.path.join(builtin_dir, f"{item_id}.json"))
    if not isinstance(data, dict) or data.get("deleted") is True:
        return None
    return data


def _list_entries(user_dir: str, builtin_dir: str) -> List[dict]:
    """Todos os itens das duas pastas, a do jogador vencendo pelo id, em ordem de nome de arquivo."""
    ids = set()
    for folder in (builtin_dir, user_dir):
        os.makedirs(folder, exist_ok=True)
        ids.update(f[:-5] for f in os.listdir(folder) if f.endswith(".json") and is_safe_id(f[:-5]))
    entries = []
    for item_id in sorted(ids):
        data = _read_entry(user_dir, builtin_dir, item_id)
        if data is not None:
            entries.append(data)
    return entries


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
    data = _read_entry(USER_CHARACTERS_DIR, CHARACTERS_DIR, character_id)
    if data is None:
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
    write_json_atomic(os.path.join(USER_CHARACTERS_DIR, f"{character.id}.json"), character.model_dump(mode="json"))
    return character


def remove_portrait_files(character_id: str) -> None:
    """Apaga o retrato, as expressões (id__feliz.png...) e a semente do personagem."""
    if not os.path.isdir(PORTRAITS_DIR):
        return
    for name in os.listdir(PORTRAITS_DIR):
        if name in (f"{character_id}.png", f"{character_id}.meta.json") or (
                name.startswith(f"{character_id}__") and name.endswith(".png")):
            os.remove(os.path.join(PORTRAITS_DIR, name))


def delete_character(character_id: str) -> bool:
    if not is_safe_id(character_id):
        return False
    user = os.path.join(USER_CHARACTERS_DIR, f"{character_id}.json")
    builtin = os.path.join(CHARACTERS_DIR, f"{character_id}.json")
    if not os.path.exists(user) and not os.path.exists(builtin):
        return False
    if os.path.exists(builtin):
        # o arquivo original fica intacto (é do git); uma marca na pasta do jogador o esconde
        write_json_atomic(user, {"id": character_id, "deleted": True})
    else:
        os.remove(user)
    remove_portrait_files(character_id)
    return True


def list_characters() -> List[dict]:
    characters = []
    for data in _list_entries(USER_CHARACTERS_DIR, CHARACTERS_DIR):
        try:
            c = Character(**data)
        except (ValidationError, TypeError) as e:
            log.warning("Personagem ignorado (%s): %s", data.get("id"), e)
            continue
        characters.append({
            "id":           c.id,
            "name":         c.name,
            "world_id":     c.world_id,
            "age":          c.age,
            "summary":      c.summary or _auto_summary(c.description),
            "scenario":     _shorten(c.scenario, 200),
            "avatar_emoji": c.avatar_emoji,
            "group":        c.group,
            "tags":         c.tags,
            "has_portrait": os.path.exists(os.path.join(PORTRAITS_DIR, f"{c.id}.png")),
        })
    return characters


# ─── MUNDOS ───────────────────────────────────────────────────────────────────

def load_world(world_id: str) -> Optional[World]:
    if not world_id or not is_safe_id(world_id):
        return None
    data = _read_entry(USER_WORLDS_DIR, WORLDS_DIR, world_id)
    if data is None:
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
    write_json_atomic(os.path.join(USER_WORLDS_DIR, f"{world.id}.json"), world.model_dump(mode="json"))
    return world


def list_worlds() -> List[dict]:
    worlds = []
    for data in _list_entries(USER_WORLDS_DIR, WORLDS_DIR):
        try:
            w = World(**data)
        except (ValidationError, TypeError) as e:
            log.warning("Mundo ignorado (%s): %s", data.get("id"), e)
            continue
        desc = w.description
        worlds.append({
            "id":          w.id,
            "name":        w.name,
            "genre":       w.genre,
            "description": desc if len(desc) <= 120 else desc[:120] + "...",
        })
    return worlds
