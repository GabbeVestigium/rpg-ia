"""Rotas de imagem: retratos dos personagens e cenas geradas durante o chat."""

import asyncio
import os
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import sd_client
from backend.character_manager import load_character, remove_portrait_files
from backend.config import PORTRAITS_DIR
from backend.models import SceneImage
from backend.ollama_client import unload_model
from backend.scene import generate_scene_image
from backend.session_manager import load_session, save_session, session_lock
from backend.settings_manager import get_settings
from backend.storage import read_json, safe_id, write_json_atomic

router = APIRouter(prefix="/api", tags=["images"])


def _portrait_path(character_id: str) -> str:
    return os.path.join(PORTRAITS_DIR, f"{safe_id(character_id, 'id do personagem')}.png")


def _portrait_url(character_id: str) -> str:
    return f"/portraits/{character_id}.png"


def _meta_path(character_id: str) -> str:
    return os.path.join(PORTRAITS_DIR, f"{safe_id(character_id, 'id do personagem')}.meta.json")


def _expression_path(character_id: str, expression: str) -> str:
    return os.path.join(PORTRAITS_DIR, f"{safe_id(character_id, 'id do personagem')}__{expression}.png")


def _available_expressions(character_id: str) -> list:
    return [e for e in sd_client.EXPRESSIONS if os.path.exists(_expression_path(character_id, e))]


def _seed_for(character_id: str, fresh: bool) -> int:
    """Semente do rosto do personagem: guardada ao lado do retrato para as expressões repetirem."""
    meta = read_json(_meta_path(character_id)) or {}
    if fresh or not isinstance(meta.get("seed"), int):
        meta = {"seed": random.randint(1, 2**31 - 1)}
        write_json_atomic(_meta_path(character_id), meta)
    return meta["seed"]


@router.get("/sd/check-portrait/{character_id}")
async def check_portrait(character_id: str):
    exists = os.path.exists(_portrait_path(character_id))
    return {
        "exists": exists,
        "image_path": _portrait_url(character_id) if exists else None,
        "expressions": _available_expressions(character_id) if exists else [],
        "all_expressions": list(sd_client.EXPRESSIONS),
    }


class PortraitRequest(BaseModel):
    character_id: str
    force_regenerate: bool = False


@router.post("/sd/generate-portrait")
async def generate_portrait(req: PortraitRequest):
    """Gera o retrato do personagem a partir das suas appearance_tags e descrição."""
    character = load_character(req.character_id)
    if not character:
        raise HTTPException(404, "Personagem não encontrado")

    path = _portrait_path(req.character_id)
    if os.path.exists(path) and not req.force_regenerate:
        return {"success": True, "image_path": _portrait_url(character.id), "cached": True}

    settings = get_settings()
    prompt, negative = sd_client.build_character_prompt(
        name=character.name, gender=character.gender,
        appearance_tags=character.appearance_tags,
        # Sem tags, cai no fallback genérico em vez de jogar o texto em português no SD.
        description=None, nsfw=settings["sd_nsfw"],
    )
    try:
        if not await asyncio.to_thread(sd_client.check_sd_available):
            raise ConnectionError("Stable Diffusion offline. Inicie o Automatic1111 com --api.")
        if settings["scene_auto_unload"]:
            await unload_model()
        seed = _seed_for(character.id, fresh=True)
        png = await asyncio.to_thread(sd_client.generate_image, prompt, negative, {"seed": seed})
        await asyncio.to_thread(sd_client.save_png, png, path)
        # Rosto novo: as expressões antigas deixam de combinar. Só saem depois do retrato novo existir,
        # para uma falha do Stable Diffusion nunca deixar o personagem sem imagem.
        for expression in _available_expressions(character.id):
            os.remove(_expression_path(character.id, expression))
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"success": True, "image_path": _portrait_url(character.id), "cached": False}


class ExpressionRequest(BaseModel):
    character_id: str
    expression: str


@router.post("/sd/generate-expression")
async def generate_expression(req: ExpressionRequest):
    """Gera uma expressão do personagem com o mesmo rosto do retrato (mesma semente e tags)."""
    character = load_character(req.character_id)
    if not character:
        raise HTTPException(404, "Personagem não encontrado")
    if character.group:
        raise HTTPException(400, "Personagem de grupo não tem um rosto só.")
    if req.expression not in sd_client.EXPRESSIONS:
        raise HTTPException(400, f"Expressão desconhecida. Use: {', '.join(sd_client.EXPRESSIONS)}")
    if not os.path.exists(_portrait_path(character.id)):
        raise HTTPException(400, "Gere o retrato primeiro: as expressões partem do mesmo rosto.")

    path = _expression_path(character.id, req.expression)
    if os.path.exists(path):
        return {"success": True, "expression": req.expression, "cached": True}

    settings = get_settings()
    prompt, negative = sd_client.build_expression_prompt(
        character.appearance_tags, req.expression, character.gender, settings["sd_nsfw"])
    try:
        if not await asyncio.to_thread(sd_client.check_sd_available):
            raise ConnectionError("Stable Diffusion offline. Inicie o Automatic1111 com --api.")
        if settings["scene_auto_unload"]:
            await unload_model()
        seed = _seed_for(character.id, fresh=False)
        png = await asyncio.to_thread(sd_client.generate_image, prompt, negative, {"seed": seed})
        await asyncio.to_thread(sd_client.save_png, png, path)
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"success": True, "expression": req.expression, "cached": False}


@router.delete("/sd/delete-portrait/{character_id}")
async def delete_portrait(character_id: str):
    path = _portrait_path(character_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Retrato não encontrado")
    remove_portrait_files(character_id)  # retrato, semente e expressões
    return {"success": True}


class SceneRequest(BaseModel):
    session_id: str


@router.post("/scene/generate")
async def generate_scene(req: SceneRequest):
    """Gera uma imagem da cena atual e a guarda na sessão."""
    async with session_lock(req.session_id):
        session = load_session(req.session_id)
        if not session:
            raise HTTPException(404, "Sessão não encontrada")
        character = load_character(session.character_id)
        if not character:
            raise HTTPException(404, "Personagem não encontrado")
        try:
            result = await generate_scene_image(session, character)
        except ConnectionError as e:
            raise HTTPException(503, str(e))
        except RuntimeError as e:
            raise HTTPException(500, str(e))
        image = SceneImage(url=result["url"], at=len(session.history), prompt=result["prompt"])
        session.images.append(image)
        save_session(session)
    return image.model_dump()
