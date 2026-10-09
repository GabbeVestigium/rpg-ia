"""Rotas de sistema: status, configurações, voz."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend import sd_client, tts_client
from backend.models import PlayerProfile
from backend.ollama_client import check_ollama
from backend.profile_manager import load_profile, save_profile
from backend.settings_manager import DEFAULTS, get_settings, update_settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status")
async def status():
    return await check_ollama()


@router.get("/settings")
async def read_settings():
    return {"settings": get_settings(), "defaults": DEFAULTS}


@router.put("/settings")
async def write_settings(changes: Dict[str, Any]):
    return {"settings": update_settings(changes)}


# ─── PERFIL DO JOGADOR ────────────────────────────────────────────────────────

@router.get("/profile")
async def read_profile():
    return load_profile().model_dump()


@router.put("/profile")
async def write_profile(profile: PlayerProfile):
    """Salva quem você é em todas as histórias. Idade abaixo de 18 é recusada (422)."""
    return save_profile(profile).model_dump()


# ─── VOZ ──────────────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)


@router.get("/tts/status")
async def tts_status():
    s = get_settings()
    problem = tts_client.piper_ready() if s["tts_engine"] == "piper" else None
    return {"engine": s["tts_engine"], "ready": problem is None, "problem": problem}


@router.post("/tts")
async def tts(req: TTSRequest):
    """Sintetiza a fala com o Piper e devolve um WAV. A engine 'browser' não passa por aqui."""
    try:
        audio = await tts_client.synthesize(req.text)
    except tts_client.TTSError as e:
        raise HTTPException(503, str(e))
    return Response(content=audio, media_type="audio/wav")


# ─── STABLE DIFFUSION ─────────────────────────────────────────────────────────

@router.get("/sd/status")
async def sd_status():
    import asyncio
    available = await asyncio.to_thread(sd_client.check_sd_available)
    return {
        "available": available,
        "message": "SD API disponível" if available else "SD API offline (inicie o Automatic1111 com --api)",
    }
