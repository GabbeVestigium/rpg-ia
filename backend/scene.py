"""
Imagens no chat: transforma a cena atual em tags do Stable Diffusion.

Fluxo: o LLM lê as últimas mensagens e descreve só o que é visível (cenário, pose,
roupa, expressão) em tags curtas em inglês. Essas tags se juntam às appearance_tags
fixas do personagem, o que mantém o rosto e o visual consistentes entre cenas.
"""

import asyncio
import os
import uuid
from typing import List

from backend import sd_client
from backend.config import SCENES_DIR
from backend.models import Message, SessionData
from backend.ollama_client import OllamaError, complete, unload_model
from backend.settings_manager import get_settings

_SYSTEM_SFW = (
    "You convert a roleplay scene into Danbooru-style image tags for Stable Diffusion. "
    "Output ONLY 12 to 22 comma-separated lowercase English tags describing what is "
    "visible right now: setting, time of day, lighting, pose, clothing, expression, camera "
    "framing. Do not include the character's name, hair or eye colors (those are added "
    "separately), quality tags, or any sentences. Keep it non-explicit and fully clothed."
)

_SYSTEM_NSFW = (
    "You convert a roleplay scene into Danbooru-style image tags for Stable Diffusion. "
    "Output ONLY 12 to 22 comma-separated lowercase English tags describing what is "
    "visible right now: setting, time of day, lighting, pose, clothing state, expression, "
    "camera framing, faithful to the scene. Do not include the character's name, hair or "
    "eye colors (those are added separately), quality tags, or any sentences. "
    "All characters are adults."
)

_FALLBACK_TAGS = "indoors, looking at viewer, upper body, soft lighting"


def _recent_text(history: List[Message], character_name: str, count: int = 4) -> str:
    lines = []
    for m in history[-count:]:
        who = character_name if m.role.value == "assistant" else "Player"
        lines.append(f"{who}: {m.content[:900]}")
    return "\n".join(lines)


async def extract_scene_tags(session: SessionData, character_name: str) -> str:
    nsfw = get_settings()["sd_nsfw"]
    prompt = f"Scene so far:\n{_recent_text(session.history, character_name)}\n\nTags:"
    try:
        raw = await complete(
            prompt, system=_SYSTEM_NSFW if nsfw else _SYSTEM_SFW,
            num_predict=120, temperature=0.4,
        )
    except OllamaError:
        return _FALLBACK_TAGS
    tags = sd_client.clean_tags(raw, limit=24)
    return tags or _FALLBACK_TAGS


async def generate_scene_image(session: SessionData, character) -> dict:
    """Gera a cena atual. Devolve {url, prompt}. Levanta ConnectionError/RuntimeError."""
    settings = get_settings()

    if not await asyncio.to_thread(sd_client.check_sd_available):
        raise ConnectionError("Stable Diffusion offline. Inicie o Automatic1111 com --api.")

    tags = await extract_scene_tags(session, character.name)
    prompt, negative = sd_client.build_scene_prompt(
        character.appearance_tags, tags, character.gender, settings["sd_nsfw"],
    )

    # Na GPU de 6 GB o LLM e o SD não cabem juntos: libera o LLM antes de gerar.
    # O Ollama recarrega o modelo sozinho na próxima mensagem.
    if settings["scene_auto_unload"]:
        await unload_model()

    png = await asyncio.to_thread(sd_client.generate_image, prompt, negative)

    folder = os.path.join(SCENES_DIR, session.session_id)
    name = f"{uuid.uuid4().hex[:8]}.png"
    await asyncio.to_thread(sd_client.save_png, png, os.path.join(folder, name))
    return {"url": f"/scenes/{session.session_id}/{name}", "prompt": prompt}
