"""
Configurações em tempo de execução, editáveis na tela de Configurações.

Ficam em data/settings.json. Qualquer chave ausente ou inválida cai no valor
padrão, então o arquivo pode ser editado à mão sem medo.

Padrões pensados para GTX 1660 (6 GB): um modelo 7B quantizado (Q4) cabe inteiro
na GPU com contexto de 4k; um 8B fica no limite, então aumente o contexto com cuidado.
"""

from typing import Any, Dict

from backend.config import SETTINGS_FILE
from backend.storage import read_json, write_json_atomic

# tipo, mínimo, máximo (None = livre) ou lista de opções
_SCHEMA: Dict[str, dict] = {
    # Modelo de texto
    "model":               {"default": "",    "type": str},     # vazio = auto (primeiro instalado)
    "temperature":         {"default": 0.85,  "type": float, "min": 0.0, "max": 2.0},
    "top_p":               {"default": 0.92,  "type": float, "min": 0.0, "max": 1.0},
    "min_p":               {"default": 0.05,  "type": float, "min": 0.0, "max": 1.0},
    "repeat_penalty":      {"default": 1.1,   "type": float, "min": 1.0, "max": 2.0},
    "num_ctx":             {"default": 4096,  "type": int,   "min": 1024, "max": 32768},
    "num_predict":         {"default": 700,   "type": int,   "min": 64,   "max": 4096},
    "keep_alive":          {"default": "30m", "type": str},
    # Estilo da resposta
    "response_length":     {"default": "medium", "type": str, "options": ["short", "medium", "long"]},
    # Memória
    "history_turns":       {"default": 12,    "type": int,   "min": 4, "max": 60},
    "memory_enabled":      {"default": True,  "type": bool},
    # Inventário
    "auto_inventory":      {"default": True,  "type": bool},
    # Imagens
    "sd_nsfw":             {"default": False, "type": bool},
    "sd_steps":            {"default": 28,    "type": int,   "min": 10, "max": 60},
    "scene_auto_unload":   {"default": True,  "type": bool},   # descarrega o LLM da VRAM antes do SD
    # Voz
    "tts_engine":          {"default": "browser", "type": str, "options": ["off", "browser", "piper"]},
    "tts_auto_play":       {"default": False, "type": bool},
    "tts_dialogue_only":   {"default": True,  "type": bool},   # lê só as falas, pula *ações*
    "tts_rate":            {"default": 1.0,   "type": float, "min": 0.5, "max": 2.0},
    "tts_voice":           {"default": "",    "type": str},     # nome da voz do navegador
    "piper_bin":           {"default": "piper", "type": str},
    "piper_model":         {"default": "",    "type": str},     # caminho do .onnx
}

DEFAULTS: Dict[str, Any] = {k: v["default"] for k, v in _SCHEMA.items()}


def _coerce(key: str, value: Any) -> Any:
    """Converte e limita um valor ao que o schema permite; inválido vira o padrão."""
    spec = _SCHEMA[key]
    typ = spec["type"]
    try:
        if typ is bool:
            if isinstance(value, str):
                value = value.strip().lower() in ("1", "true", "yes", "on")
            value = bool(value)
        elif typ is int:
            value = int(value)
        elif typ is float:
            value = float(value)
        else:
            value = str(value)
    except (TypeError, ValueError):
        return spec["default"]

    if "options" in spec and value not in spec["options"]:
        return spec["default"]
    if typ in (int, float):
        if "min" in spec:
            value = max(spec["min"], value)
        if "max" in spec:
            value = min(spec["max"], value)
    return value


def get_settings() -> Dict[str, Any]:
    stored = read_json(SETTINGS_FILE) or {}
    result = dict(DEFAULTS)
    if isinstance(stored, dict):
        for key in _SCHEMA:
            if key in stored:
                result[key] = _coerce(key, stored[key])
    return result


def update_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica mudanças parciais ignorando chaves desconhecidas, e salva."""
    current = get_settings()
    for key, value in (changes or {}).items():
        if key in _SCHEMA:
            current[key] = _coerce(key, value)
    write_json_atomic(SETTINGS_FILE, current)
    return current
