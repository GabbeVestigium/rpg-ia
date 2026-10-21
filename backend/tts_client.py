"""
Voz local via Piper (https://github.com/rhasspy/piper), rodando na CPU para não
disputar a VRAM com o LLM e o Stable Diffusion.

Se você prefere zero instalação, use a engine "browser" nas Configurações: a voz
fica por conta do navegador (no Windows usa as vozes do sistema) e este módulo
nem é chamado.
"""

import asyncio
import os
import re
import shutil
import tempfile
from typing import Optional

from backend.settings_manager import get_settings


class TTSError(Exception):
    pass


def speakable_text(text: str, dialogue_only: bool) -> str:
    """Prepara o texto para falar: tira marcação, e opcionalmente as ações em *asteriscos*."""
    if dialogue_only:
        text = re.sub(r"\*[^*]*\*", " ", text)
    else:
        text = text.replace("*", "")
    text = re.sub(r"[\"“”]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def piper_ready() -> Optional[str]:
    """Devolve None se o Piper está pronto, senão o motivo."""
    s = get_settings()
    if not shutil.which(s["piper_bin"]) and not os.path.isfile(s["piper_bin"]):
        return f"Piper não encontrado ('{s['piper_bin']}'). Instale e ajuste o caminho nas Configurações."
    if not s["piper_model"] or not os.path.isfile(s["piper_model"]):
        return "Modelo de voz (.onnx) do Piper não configurado."
    return None


async def synthesize(text: str) -> bytes:
    """Gera um WAV a partir do texto."""
    s = get_settings()
    problem = piper_ready()
    if problem:
        raise TTSError(problem)

    spoken = speakable_text(text, s["tts_dialogue_only"])
    if not spoken:
        raise TTSError("Não há fala para ler nesta mensagem.")
    spoken = spoken[:2000]

    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        proc = await asyncio.create_subprocess_exec(
            s["piper_bin"], "--model", s["piper_model"], "--output_file", out_path,
            "--length_scale", str(round(1.0 / s["tts_rate"], 2)),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(proc.communicate(spoken.encode("utf-8")), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            raise TTSError("O Piper demorou demais.")
        if proc.returncode != 0:
            raise TTSError(f"Piper falhou: {err.decode(errors='ignore')[:200]}")
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
