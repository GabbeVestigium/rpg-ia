"""Rotas de imagem: retratos dos personagens e cenas geradas durante o chat."""

import asyncio
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import sd_client
from backend.character_manager import load_character
from backend.config import PORTRAITS_DIR
from backend.models import SceneImage
from backend.ollama_client import unload_model
from backend.scene import generate_scene_image
from backend.session_manager import load_session, save_session, session_lock
from backend.settings_manager import get_settings
from backend.storage import safe_id

router = APIRouter(prefix="/api", tags=["images"])


def _portrait_path(character_id: str) -> str:
    return os.path.join(PORTRAITS_DIR, f"{safe_id(character_id, 'id do personagem')}.png")


def _portrait_url(character_id: str) -> str:
    return f"/static/images/characters/{character_id}.png"


@router.get("/sd/check-portrait/{character_id}")
async def check_portrait(character_id: str):
    exists = os.path.exists(_portrait_path(character_id))
    return {"exists": exists, "image_path": _portrait_url(character_id) if exists else None}


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
        png = await asyncio.to_thread(sd_client.generate_image, prompt, negative)
        await asyncio.to_thread(sd_client.save_png, png, path)
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"success": True, "image_path": _portrait_url(character.id), "cached": False}


@router.delete("/sd/delete-portrait/{character_id}")
async def delete_portrait(character_id: str):
    path = _portrait_path(character_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Retrato não encontrado")
    os.remove(path)
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
