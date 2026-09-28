#!/usr/bin/env python3
"""
SD Client — Integração com Stable Diffusion (Automatic1111 WebUI)
Otimizado para GTX 1660 (4GB VRAM) com suporte a conteúdo adulto.
"""

import os
import base64
import requests
import json
from typing import Optional, Dict, Tuple
from pathlib import Path

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────

SD_API_URL = "http://127.0.0.1:7860"  # Automatic1111 default port
SD_TIMEOUT = 180  # 3 minutos timeout (geração pode demorar)

# Configurações otimizadas para GTX 1660 (4GB VRAM)
DEFAULT_SETTINGS = {
    "width": 512,               # Portrait ideal para personagens
    "height": 768,              
    "steps": 25,                # Balanço qualidade/velocidade
    "cfg_scale": 7,             # Guidance scale
    "sampler_name": "DPM++ 2M Karras",  # Rápido + qualidade
    "batch_size": 1,            # Uma imagem por vez (VRAM limitada)
    "restore_faces": False,     # Consome VRAM extra
    "enable_hr": False,         # Hires fix desligado (VRAM++)
    "denoising_strength": 0.7,
}

# Negative prompt padrão (evita defeitos comuns)
DEFAULT_NEGATIVE = """
blurry, low quality, deformed, ugly, bad anatomy, bad hands, 
extra fingers, missing fingers, fused fingers, too many fingers,
long neck, duplicate, mutilated, poorly drawn hands, poorly drawn face,
mutation, deformed, bad proportions, gross proportions, 
malformed limbs, missing arms, missing legs, extra arms, extra legs,
watermark, signature, username, text, caption, jpeg artifacts,
worst quality, normal quality, lowres
"""

# ─── FUNÇÕES AUXILIARES ───────────────────────────────────────────────────────

def build_character_prompt(
    name: str,
    race: str,
    char_class: str,
    gender: str = "female",
    description: Optional[str] = None,
    nsfw: bool = False,
    style: str = "semi-realistic"
) -> Tuple[str, str]:
    """
    Constrói prompt otimizado para geração de retrato de personagem.
    
    Args:
        name: Nome do personagem
        race: Raça (human, elf, dwarf, orc, etc)
        char_class: Classe (warrior, mage, rogue, etc)
        gender: Gênero (male, female, non-binary)
        description: Descrição adicional livre
        nsfw: Se True, permite conteúdo adulto
        style: Estilo artístico (semi-realistic, anime, painted, etc)
    
    Returns:
        (prompt, negative_prompt)
    """
    
    # Mapeamento de raça para características
    race_traits = {
        "human": "human",
        "humano": "human",
        "elf": "elf, pointed ears, elegant features",
        "elfo": "elf, pointed ears, elegant features",
        "dwarf": "dwarf, short stature, thick beard, stocky build",
        "anão": "dwarf, short stature, thick beard, stocky build",
        "orc": "orc, green skin, tusks, muscular",
        "halfling": "halfling, small stature, cheerful",
        "tiefling": "tiefling, horns, tail, demonic features",
        "dragonborn": "dragonborn, scales, draconic features",
    }
    
    # Mapeamento de classe para equipamento/visual
    class_visual = {
        "warrior": "armored, sword and shield, battle-worn",
        "guerreiro": "armored, sword and shield, battle-worn",
        "mage": "robes with arcane symbols, holding staff, magical aura",
        "mago": "robes with arcane symbols, holding staff, magical aura",
        "rogue": "leather armor, daggers, hooded cloak, stealthy",
        "ladino": "leather armor, daggers, hooded cloak, stealthy",
        "cleric": "holy symbols, light armor, divine glow",
        "clérigo": "holy symbols, light armor, divine glow",
        "ranger": "bow and arrows, forest ranger outfit, nature theme",
        "patrulheiro": "bow and arrows, forest ranger outfit, nature theme",
        "paladin": "heavy plate armor, holy sword, radiant",
        "paladino": "heavy plate armor, holy sword, radiant",
        "bard": "musical instrument, colorful clothes, charming",
        "bardo": "musical instrument, colorful clothes, charming",
    }
    
    # Estilo artístico
    style_prompt = {
        "semi-realistic": "semi-realistic, detailed, high quality, professional digital art",
        "anime": "anime style, cel shaded, vibrant colors",
        "painted": "oil painting, painted style, artistic, brushstrokes",
        "realistic": "photorealistic, realistic, 8k, high detail",
        "fantasy-art": "fantasy art, trending on artstation, detailed illustration",
    }
    
    # Construir prompt base
    race_desc = race_traits.get(race.lower(), race)
    class_desc = class_visual.get(char_class.lower(), char_class)
    style_desc = style_prompt.get(style, style_prompt["semi-realistic"])
    
    prompt_parts = [
        f"portrait of a {gender} {race_desc} {char_class}",
        class_desc,
        style_desc,
        "detailed face, expressive eyes, good anatomy",
        "studio lighting, rim lighting",
        "4k, masterpiece, best quality",
    ]
    
    # Adicionar descrição customizada se fornecida
    if description:
        prompt_parts.insert(2, description)
    
    # Ajustes para NSFW
    if nsfw:
        prompt_parts.extend([
            "beautiful, attractive, seductive",
            "detailed body, anatomically correct",
        ])
    else:
        prompt_parts.append("sfw, clothed, modest")
    
    prompt = ", ".join(prompt_parts)
    
    # Negative prompt (adiciona restrições se não for NSFW)
    negative = DEFAULT_NEGATIVE
    if not nsfw:
        negative += ", nsfw, nude, nudity, explicit, sexual content, exposed"
    
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
        style="semi-realistic"  # Melhor balanço qualidade/VRAM
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
