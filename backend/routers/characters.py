"""Rotas de personagens e mundos (listar, ler, criar, editar, apagar)."""

from fastapi import APIRouter, HTTPException

from backend.character_manager import (
    delete_character, list_characters, list_worlds, load_character, load_world,
    save_character, save_world,
)
from backend.models import Character, World
from backend.storage import safe_id, slugify

router = APIRouter(prefix="/api", tags=["characters"])


@router.get("/characters")
async def get_characters():
    return list_characters()


@router.get("/characters/{character_id}")
async def get_character(character_id: str):
    character = load_character(safe_id(character_id, "id do personagem"))
    if not character:
        raise HTTPException(404, "Personagem não encontrado")
    return character.model_dump(mode="json")


@router.put("/characters/{character_id}")
async def put_character(character_id: str, character: Character):
    """Cria ou atualiza um personagem. Rejeita menores de idade (regra 18+)."""
    safe_id(character_id, "id do personagem")
    if character.id != character_id:
        raise HTTPException(400, "O id do corpo não bate com o da URL")
    try:
        save_character(character)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "id": character.id}


@router.post("/characters")
async def create_character(character: Character):
    """Cria personagem novo; gera o id a partir do nome se não vier um válido."""
    base = slugify(character.name)
    new_id, n = base, 2
    while load_character(new_id):
        new_id = f"{base}-{n}"
        n += 1
    character.id = new_id
    try:
        save_character(character)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "id": new_id}


@router.delete("/characters/{character_id}")
async def remove_character(character_id: str):
    if not delete_character(safe_id(character_id, "id do personagem")):
        raise HTTPException(404, "Personagem não encontrado")
    return {"deleted": True}


# ─── MUNDOS ───────────────────────────────────────────────────────────────────

@router.get("/worlds")
async def get_worlds():
    return list_worlds()


@router.get("/worlds/{world_id}")
async def get_world(world_id: str):
    world = load_world(safe_id(world_id, "id do mundo"))
    if not world:
        raise HTTPException(404, "Mundo não encontrado")
    return world.model_dump(mode="json")


@router.put("/worlds/{world_id}")
async def put_world(world_id: str, world: World):
    safe_id(world_id, "id do mundo")
    if world.id != world_id:
        raise HTTPException(400, "O id do corpo não bate com o da URL")
    try:
        save_world(world)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "id": world.id}
