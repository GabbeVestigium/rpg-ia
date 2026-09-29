#!/usr/bin/env python3
"""
SD Client — Integração com Stable Diffusion (Automatic1111 WebUI)
Otimizado para GTX 1660 (4GB VRAM) com suporte a conteúdo adulto.
Modelo: AbyssOrangeMix3 (AOM3) — estilo anime semi-realista.
"""

import os
import base64
import requests
from typing import Optional, Dict, Tuple

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────

SD_API_URL = "http://127.0.0.1:7860"  # Automatic1111 default port
SD_TIMEOUT = 180  # 3 minutos timeout

# Configurações otimizadas para GTX 1660 (4GB VRAM) + AOM3
# AOM3 performa melhor com cfg_scale entre 5-7 e DPM++ 2M Karras
DEFAULT_SETTINGS = {
    "width": 512,
    "height": 768,              # Portrait ratio
    "steps": 28,                # AOM3 precisa de mais steps que SD realista
    "cfg_scale": 6,             # AOM3 fica melhor com cfg baixo (5-7)
    "sampler_name": "DPM++ 2M Karras",
    "batch_size": 1,
    "restore_faces": False,     # Não funciona bem com anime
    "enable_hr": False,         # Desligado para economizar VRAM
    "denoising_strength": 0.7,
}

# Negative prompt otimizado para AOM3 (anime)
# AOM3 precisa de negative prompts específicos para evitar defeitos comuns
DEFAULT_NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, username, "
    "blurry, bad feet, poorly drawn hands, poorly drawn face, "
    "mutation, deformed, extra limbs, extra arms, extra legs, "
    "malformed limbs, fused fingers, too many fingers, long neck, "
    "cross-eyed, mutilated, gross proportions, missing arms, "
    "missing legs, extra arms, extra legs, disfigured, ugly"
)

# ─── MAPEAMENTOS DE RAÇA E CLASSE ─────────────────────────────────────────────

# Termos em inglês que funcionam bem no AOM3
RACE_TRAITS = {
    "human":      "human",
    "humano":     "human",
    "elf":        "elf girl, long pointy ears, elegant",
    "elfo":       "elf girl, long pointy ears, elegant",
    "elfa":       "elf girl, long pointy ears, elegant",
    "dwarf":      "dwarf, short stature, stocky",
    "anão":       "dwarf, short stature, stocky",
    "orc":        "orc, green skin, tusks, muscular",
    "halfling":   "halfling, small stature, cute",
    "tiefling":   "tiefling, demon horns, tail, purple skin",
    "dragonborn": "dragonborn, scales, draconic features, reptilian eyes",
    "dark elf":   "dark elf, dark skin, white hair, red eyes",
    "elfa negra": "dark elf, dark skin, white hair, red eyes",
}

CLASS_VISUAL = {
    "warrior":     "heavy armor, sword, shield, battle-scarred",
    "guerreiro":   "heavy armor, sword, shield, battle-scarred",
    "mage":        "elegant robes, magic staff, glowing runes, magical aura",
    "mago":        "elegant robes, magic staff, glowing runes, magical aura",
    "maga":        "elegant robes, magic staff, glowing runes, magical aura",
    "rogue":       "dark leather armor, daggers, hood, mysterious",
    "ladino":      "dark leather armor, daggers, hood, mysterious",
    "cleric":      "holy robes, divine symbols, gentle glow, healer",
    "clérigo":     "holy robes, divine symbols, gentle glow, healer",
    "ranger":      "ranger cloak, bow, quiver, nature-themed outfit",
    "patrulheiro": "ranger cloak, bow, quiver, nature-themed outfit",
    "paladin":     "shining plate armor, holy sword, radiant aura",
    "paladino":    "shining plate armor, holy sword, radiant aura",
    "paladina":    "shining plate armor, holy sword, radiant aura",
    "bard":        "colorful outfit, lute, charismatic, performer",
    "bardo":       "colorful outfit, lute, charismatic, performer",
    "witch":       "witch hat, dark robes, spell book, eerie glow",
    "bruxa":       "witch hat, dark robes, spell book, eerie glow",
    "assassin":    "black stealth suit, mask, twin blades, shadows",
    "assassino":   "black stealth suit, mask, twin blades, shadows",
}

# ─── FUNÇÕES AUXILIARES ───────────────────────────────────────────────────────

def build_character_prompt(
    name: str,
    race: str,
    char_class: str,
    gender: str = "female",
    description: Optional[str] = None,
    nsfw: bool = False,
    style: str = "anime"
) -> Tuple[str, str]:
    """
    Constrói prompt otimizado para AOM3 (anime semi-realista).

    O AOM3 usa uma estrutura de prompt diferente do SD realista:
    - Começa com qualidade (masterpiece, best quality)
    - Tags curtas e diretas funcionam melhor que frases longas
    - NSFW requer tags específicas do modelo
    """

    race_desc  = RACE_TRAITS.get(race.lower(), race)
    class_desc = CLASS_VISUAL.get(char_class.lower(), char_class)

    # Gênero em tags anime
    gender_tag = "1girl" if gender.lower() in ("female", "feminino", "f") else "1boy"

    # Base de qualidade — essencial para AOM3
    quality_tags = "masterpiece, best quality, ultra-detailed, absurdres"

    # Construir prompt
    parts = [
        quality_tags,
        gender_tag,
        race_desc,
        class_desc,
        "portrait, upper body, looking at viewer",
        "beautiful face, expressive eyes, detailed eyes",
        "dynamic lighting, dramatic shadows, fantasy setting",
    ]

    # Descrição livre do personagem (cabelo, olhos, traços)
    if description:
        parts.insert(3, description)

    # NSFW — tags específicas do AOM3
    if nsfw:
        parts.extend([
            "attractive, beautiful body, detailed skin",
            "seductive expression, alluring",
        ])
        negative = DEFAULT_NEGATIVE
    else:
        parts.append("fully clothed, tasteful")
        negative = DEFAULT_NEGATIVE + (
            ", nsfw, nude, nudity, explicit, sexual, "
            "revealing clothes, underwear, lingerie"
        )

    prompt = ", ".join(parts)
    return prompt, negative


def check_sd_available() -> bool:
    """Verifica se Automatic1111 está rodando."""
    try:
        response = requests.get(f"{SD_API_URL}/sdapi/v1/sd-models", timeout=5)
        return response.status_code == 200
    except:
        return False


def get_sd_models() -> list:
    """Lista modelos disponíveis no SD."""
    try:
        response = requests.get(f"{SD_API_URL}/sdapi/v1/sd-models", timeout=10)
        if response.status_code == 200:
            models = response.json()
            return [m["title"] for m in models]
        return []
    except:
        return []


def generate_image(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    settings: Optional[Dict] = None
) -> Optional[bytes]:
    """
    Gera imagem via API do Stable Diffusion.
    
    Args:
        prompt: Prompt de geração
        negative_prompt: Prompt negativo
        settings: Configurações customizadas (sobrescreve DEFAULT_SETTINGS)
    
    Returns:
        Bytes da imagem PNG ou None se falhar
    """
    if not check_sd_available():
        raise ConnectionError("Stable Diffusion API não está disponível. Inicie o Automatic1111.")
    
    # Merge settings
    payload = DEFAULT_SETTINGS.copy()
    if settings:
        payload.update(settings)
    
    payload["prompt"] = prompt
    payload["negative_prompt"] = negative_prompt
    
    try:
        print(f"[SD] Gerando imagem... (pode demorar 30-60s)")
        print(f"[SD] Prompt: {prompt[:100]}...")
        
        response = requests.post(
            f"{SD_API_URL}/sdapi/v1/txt2img",
            json=payload,
            timeout=SD_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Pegar primeira imagem gerada
            if result.get("images"):
                image_b64 = result["images"][0]
                image_bytes = base64.b64decode(image_b64)
                print(f"[SD] ✓ Imagem gerada com sucesso ({len(image_bytes)} bytes)")
                return image_bytes
            else:
                print("[SD] ✗ Nenhuma imagem retornada pela API")
                return None
        else:
            print(f"[SD] ✗ Erro na API: {response.status_code}")
            print(f"[SD] Response: {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print("[SD] ✗ Timeout na geração (>3min)")
        return None
    except Exception as e:
        print(f"[SD] ✗ Erro: {e}")
        return None


def generate_character_portrait(
    char_id: str,
    name: str,
    race: str,
    char_class: str,
    gender: str = "female",
    description: Optional[str] = None,
    nsfw: bool = False,
    output_dir: str = "static/images/characters",
    force_regenerate: bool = False
) -> Optional[str]:
    """
    Gera retrato de personagem e salva em disco.
    
    Args:
        char_id: ID único do personagem (usado no filename)
        name: Nome do personagem
        race: Raça
        char_class: Classe
        gender: Gênero
        description: Descrição adicional
        nsfw: Permitir conteúdo adulto
        output_dir: Diretório de saída
        force_regenerate: Se True, regenera mesmo se já existir
    
    Returns:
        Path relativo da imagem ou None se falhar
    """
    
    # Criar diretório se não existir
    os.makedirs(output_dir, exist_ok=True)
    
    # Path da imagem
    filename = f"{char_id}.png"
    filepath = os.path.join(output_dir, filename)
    
    # Se já existe e não forçar regeneração, retorna path
    if os.path.exists(filepath) and not force_regenerate:
        print(f"[SD] ✓ Imagem já existe: {filepath}")
        return filepath
    
    # Gerar prompt
    prompt, negative = build_character_prompt(
        name=name,
        race=race,
        char_class=char_class,
        gender=gender,
        description=description,
        nsfw=nsfw,
        style="anime"  # AOM3 — estilo anime semi-realista
    )
    
    # Gerar imagem
    image_bytes = generate_image(prompt, negative)
    
    if image_bytes:
        # Salvar em disco
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        print(f"[SD] ✓ Imagem salva: {filepath}")
        return filepath
    else:
        print(f"[SD] ✗ Falha ao gerar imagem para {name}")
        return None


# ─── FUNÇÕES DE EXPRESSÕES (FUTURO) ───────────────────────────────────────────

def generate_expression_variants(
    char_id: str,
    base_prompt: str,
    output_dir: str = "static/images/characters"
) -> Dict[str, Optional[str]]:
    """
    Gera variações de expressão para o mesmo personagem.
    
    Args:
        char_id: ID do personagem
        base_prompt: Prompt base do personagem
        output_dir: Diretório de saída
    
    Returns:
        Dict com paths das expressões: {"happy": "path/...", "angry": "path/..."}
    """
    
    expressions = {
        "neutral": "",
        "happy": "smiling, cheerful expression",
        "angry": "angry expression, fierce look",
        "sad": "sad expression, melancholic",
        "surprised": "surprised expression, wide eyes",
        "hurt": "wounded, tired, exhausted",
    }
    
    results = {}
    
    for expr_name, expr_modifier in expressions.items():
        filename = f"{char_id}_{expr_name}.png"
        filepath = os.path.join(output_dir, filename)
        
        # Se já existe, skip
        if os.path.exists(filepath):
            results[expr_name] = filepath
            continue
        
        # Adicionar modificador ao prompt
        prompt = f"{base_prompt}, {expr_modifier}" if expr_modifier else base_prompt
        
        image_bytes = generate_image(prompt, DEFAULT_NEGATIVE)
        
        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            results[expr_name] = filepath
        else:
            results[expr_name] = None
    
    return results


# ─── TESTE ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Teste rápido do sistema."""
    
    print("=== Teste do SD Client ===\n")
    
    # 1. Verificar disponibilidade
    print("1. Verificando Automatic1111...")
    if check_sd_available():
        print("   ✓ SD API disponível\n")
        
        # 2. Listar modelos
        print("2. Modelos instalados:")
        models = get_sd_models()
        for m in models:
            print(f"   - {m}")
        print()
        
        # 3. Gerar imagem de teste
        print("3. Gerando imagem de teste...")
        result = generate_character_portrait(
            char_id="test_elf_mage",
            name="Elara",
            race="elf",
            char_class="mage",
            gender="female",
            description="silver hair, purple eyes, elegant",
            nsfw=False,
            output_dir="../frontend/static/images/characters"
        )
        
        if result:
            print(f"   ✓ Sucesso! Imagem em: {result}")
        else:
            print("   ✗ Falha na geração")
    else:
        print("   ✗ SD API não disponível")
        print("   Inicie o Automatic1111 WebUI primeiro:")
        print("   webui-user.bat --api --medvram --xformers")
