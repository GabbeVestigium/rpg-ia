"""
Utilitários de armazenamento: validação de ids e escrita atômica de JSON.

Todo id que vem da rede (session_id, character_id...) vira nome de arquivo,
então precisa passar por safe_id para ninguém sair da pasta de dados com
algo como "../../etc/passwd".
"""

import json
import os
import re
from typing import Any, Optional

from fastapi import HTTPException

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_safe_id(value: str) -> bool:
    return bool(value) and bool(_ID_RE.match(value))


def safe_id(value: str, what: str = "id") -> str:
    """Retorna o id se for seguro, senão responde 400."""
    if not is_safe_id(value):
        raise HTTPException(400, f"{what} inválido")
    return value


def slugify(text: str) -> str:
    """Transforma um nome em id de arquivo (ex: 'Lyra Ashveil' -> 'lyra-ashveil')."""
    import unicodedata
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return slug[:48] or "personagem"


def read_json(path: str) -> Optional[Any]:
    """Lê JSON; devolve None se o arquivo não existe ou está corrompido."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_json_atomic(path: str, data: Any) -> None:
    """Escreve em arquivo temporário e troca no final, sem corromper o original."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
