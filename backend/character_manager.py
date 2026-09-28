"""
Gerenciador de personagens e mundos.
"""

import json
import os
from typing import Optional, List
from backend.models import Character, World
from backend.config import CHARACTERS_DIR, WORLDS_DIR


def load_character(character_id: str) -> Optional[Character]:
    path = os.path.join(CHARACTERS_DIR, f"{character_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return Character(**json.load(f))
    except (json.JSONDecodeError, Exception):
        return None


def load_world(world_id: str) -> Optional[World]:
    path = os.path.join(WORLDS_DIR, f"{world_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return World(**json.load(f))
    except (json.JSONDecodeError, Exception):
        return None


def list_characters() -> List[dict]:
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    characters = []
    for fname in os.listdir(CHARACTERS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CHARACTERS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            characters.append({
                "id":          data["id"],
                "name":        data["name"],
                "world_id":    data.get("world_id", ""),
                "description": data["description"],
                "scenario":    data.get("scenario", ""),
                "avatar_emoji":data.get("avatar_emoji", "👤"),
                "tags":        data.get("tags", [])
            })
        except Exception:
            continue  # ignora arquivo corrompido, continua listando os demais
    return characters


def list_worlds() -> List[dict]:
    os.makedirs(WORLDS_DIR, exist_ok=True)
    worlds = []
    for fname in os.listdir(WORLDS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(WORLDS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            worlds.append({
                "id":          data["id"],
                "name":        data["name"],
                "genre":       data.get("genre", ""),
                "description": data["description"][:120] + "..."
            })
        except Exception:
            continue
    return worlds
