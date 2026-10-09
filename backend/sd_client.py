"""
Cliente do Stable Diffusion (Automatic1111 WebUI com --api).

Pensado para GTX 1660 (6 GB) com um modelo anime tipo AbyssOrangeMix3 (AOM3):
512x768, DPM++ 2M Karras, cfg baixo. As funções aqui são síncronas e bloqueantes;
os routers chamam via asyncio.to_thread para não travar o servidor.
"""

import base64
import os
import re
from typing import Dict, Optional, Tuple

import httpx

from backend.config import SD_API_URL
from backend.safety import SD_ALWAYS_NEGATIVE, SD_ALWAYS_POSITIVE, find_problems
from backend.settings_manager import get_settings

SD_TIMEOUT = 240  # segundos; a primeira geração carrega o modelo na VRAM

DEFAULT_SETTINGS = {
    "width": 512,
    "height": 768,
    "steps": 28,
    "cfg_scale": 6,              # AOM3 fica melhor com cfg 5-7
    "sampler_name": "DPM++ 2M Karras",
    "batch_size": 1,
    "restore_faces": False,      # não funciona bem com anime
    "enable_hr": False,          # desligado para poupar VRAM
}

QUALITY_TAGS = "masterpiece, best quality, ultra-detailed, absurdres"

DEFAULT_NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
    "signature, watermark, username, blurry, bad feet, poorly drawn hands, "
    "poorly drawn face, mutation, deformed, extra limbs, malformed limbs, "
    "fused fingers, too many fingers, long neck, cross-eyed, disfigured, ugly"
)

SFW_NEGATIVE = "nsfw, nude, nudity, explicit, sexual, underwear, lingerie, revealing clothes"

# ─── RAÇAS E CLASSES (tags em inglês que o AOM3 entende) ─────────────────────

RACE_TRAITS = {
    "human": "human", "humano": "human",
    "elf": "elf, long pointy ears, elegant", "elfo": "elf, long pointy ears, elegant",
    "elfa": "elf, long pointy ears, elegant",
    "dwarf": "dwarf, stocky", "anão": "dwarf, stocky", "anao": "dwarf, stocky",
    "orc": "orc, green skin, tusks, muscular",
    "halfling": "halfling, small stature",
    "tiefling": "tiefling, demon horns, tail, purple skin",
    "dragonborn": "dragonborn, scales, draconic features, reptilian eyes",
    "dark elf": "dark elf, dark skin, white hair, red eyes",
    "meio-elfo": "half-elf, pointy ears",
}

CLASS_VISUAL = {
    "warrior": "heavy armor, sword, shield", "guerreiro": "heavy armor, sword, shield",
    "mage": "elegant robes, magic staff, glowing runes", "mago": "elegant robes, magic staff, glowing runes",
    "maga": "elegant robes, magic staff, glowing runes",
    "rogue": "dark leather armor, daggers, hood", "ladino": "dark leather armor, daggers, hood",
    "cleric": "holy robes, divine symbols, gentle glow", "clérigo": "holy robes, divine symbols, gentle glow",
    "ranger": "ranger cloak, bow, quiver", "patrulheiro": "ranger cloak, bow, quiver",
    "paladin": "shining plate armor, holy sword", "paladino": "shining plate armor, holy sword",
    "bard": "colorful outfit, lute", "bardo": "colorful outfit, lute",
    "witch": "witch hat, dark robes, spell book", "bruxa": "witch hat, dark robes, spell book",
    "assassin": "black stealth suit, mask, twin blades", "assassino": "black stealth suit, mask, twin blades",
}


# ─── PROMPTS ──────────────────────────────────────────────────────────────────

def _gender_tag(gender: str) -> str:
    return "1girl" if gender.lower() in ("female", "feminino", "f", "mulher") else "1boy"


def clean_tags(text: str, limit: int = 40) -> str:
    """Normaliza uma lista de tags vinda do usuário ou do LLM e tira tags de menor de idade."""
    text = text.replace("\n", ",")
    text = re.sub(r"[^A-Za-z0-9,\-_ ():.']", "", text)
    tags, seen = [], set()
    for raw in text.split(","):
        tag = raw.strip().lower()
        if not tag or tag in seen or len(tag) > 40:
            continue
        if find_problems(tag):
            continue
        seen.add(tag)
        tags.append(tag)
    return ", ".join(tags[:limit])


# Tags de cada expressão. Todas são seguras para qualquer configuração de imagem.
EXPRESSIONS = {
    "happy":     "smiling, happy, cheerful, bright eyes",
    "angry":     "angry, furrowed brow, glaring, clenched teeth",
    "sad":       "sad, teary eyes, looking down, melancholic",
    "surprised": "surprised, wide eyes, open mouth, raised eyebrows",
    "shy":       "blushing, embarrassed, looking away, shy smile",
}


def build_expression_prompt(appearance_tags: str, expression: str, gender: str = "female",
                            nsfw: bool = False) -> Tuple[str, str]:
    """Mesmo rosto do retrato (mesmas tags e mesma semente), mudando só a expressão."""
    parts = [QUALITY_TAGS, SD_ALWAYS_POSITIVE,
             clean_tags(appearance_tags) if appearance_tags else _gender_tag(gender),
             "portrait, upper body, looking at viewer", EXPRESSIONS[expression], "dynamic lighting"]
    return ", ".join(p for p in parts if p), build_negative(nsfw)


def build_negative(nsfw: bool) -> str:
    parts = [DEFAULT_NEGATIVE, SD_ALWAYS_NEGATIVE]
    if not nsfw:
        parts.append(SFW_NEGATIVE)
    return ", ".join(parts)


def build_character_prompt(
    name: str,
    race: str = "human",
    char_class: str = "",
    gender: str = "female",
    description: Optional[str] = None,
    appearance_tags: Optional[str] = None,
    nsfw: bool = False,
) -> Tuple[str, str]:
    """Prompt de retrato. Usa appearance_tags (do personagem) quando existirem."""
    parts = [QUALITY_TAGS, SD_ALWAYS_POSITIVE]
    if appearance_tags:
        parts.append(clean_tags(appearance_tags))
    else:
        parts.append(_gender_tag(gender))
        parts.append(RACE_TRAITS.get(race.lower(), clean_tags(race)))
        if char_class:
            parts.append(CLASS_VISUAL.get(char_class.lower(), clean_tags(char_class)))
    if description:
        parts.append(clean_tags(description))
    parts += ["portrait, upper body, looking at viewer", "beautiful face, detailed eyes",
              "dynamic lighting"]
    parts.append("attractive, seductive expression" if nsfw else "fully clothed, tasteful")
    return ", ".join(p for p in parts if p), build_negative(nsfw)


def build_scene_prompt(
    appearance_tags: str, scene_tags: str, gender: str = "female", nsfw: bool = False,
) -> Tuple[str, str]:
    """Prompt de cena: aparência fixa do personagem + tags da cena atual."""
    parts = [QUALITY_TAGS, SD_ALWAYS_POSITIVE]
    parts.append(clean_tags(appearance_tags) if appearance_tags else _gender_tag(gender))
    parts.append(clean_tags(scene_tags))
    return ", ".join(p for p in parts if p), build_negative(nsfw)


# ─── API DO SD ────────────────────────────────────────────────────────────────

def check_sd_available() -> bool:
    try:
        return httpx.get(f"{SD_API_URL}/sdapi/v1/sd-models", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def get_sd_models() -> list:
    try:
        r = httpx.get(f"{SD_API_URL}/sdapi/v1/sd-models", timeout=10)
        return [m["title"] for m in r.json()] if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return []


def generate_image(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    overrides: Optional[Dict] = None,
) -> bytes:
    """
    Gera uma imagem e devolve os bytes do PNG.
    Levanta ConnectionError se o SD estiver offline e RuntimeError se falhar.
    """
    payload = dict(DEFAULT_SETTINGS)
    payload["steps"] = get_settings()["sd_steps"]
    if overrides:
        payload.update(overrides)
    payload["prompt"] = prompt
    payload["negative_prompt"] = negative_prompt

    try:
        r = httpx.post(f"{SD_API_URL}/sdapi/v1/txt2img", json=payload, timeout=SD_TIMEOUT)
    except httpx.ConnectError:
        raise ConnectionError("Stable Diffusion offline. Inicie o Automatic1111 com --api.")
    except httpx.TimeoutException:
        raise RuntimeError("A geração de imagem demorou demais.")
    if r.status_code != 200:
        raise RuntimeError(f"Erro do Stable Diffusion ({r.status_code}): {r.text[:200]}")
    images = r.json().get("images") or []
    if not images:
        raise RuntimeError("O Stable Diffusion não devolveu nenhuma imagem.")
    return base64.b64decode(images[0])


def save_png(data: bytes, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path
