"""Exportar uma conversa em texto e fazer backup/restauração dos seus dados."""

import json
import os
import posixpath
import tempfile
import zipfile
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from starlette.background import BackgroundTask

from backend.character_manager import load_character, validate_character
from backend.config import (
    CHARACTERS_DIR, PORTRAITS_DIR, PROFILE_FILE, SCENES_DIR, SESSIONS_DIR,
    SETTINGS_FILE, WORLDS_DIR,
)
from backend.models import Character, PlayerProfile, World
from backend.profile_manager import load_profile
from backend.safety import validate_texts
from backend.session_manager import get_rpg_state, load_session
from backend.settings_manager import DEFAULTS
from backend.storage import is_safe_id, safe_id, slugify

router = APIRouter(prefix="/api", tags=["data"])


# ─── EXPORTAR CONVERSA ────────────────────────────────────────────────────────

@router.get("/session/{session_id}/export")
async def export_session(session_id: str, format: str = "md"):
    """Baixa a conversa como texto (md ou txt)."""
    session = load_session(safe_id(session_id, "id da sessão"))
    if not session:
        raise HTTPException(404, "Sessão não encontrada")
    character = load_character(session.character_id)
    rpg = get_rpg_state(session)
    char_name = character.name if character else session.character_id
    me = (rpg.player.name if rpg.player and rpg.player.name else load_profile().name) or "Você"

    md = format != "txt"
    lines = [f"# {char_name}" if md else char_name.upper(),
             f"Conversa {session.session_id} · {len(session.history)} mensagens", ""]
    for m in session.history:
        label = char_name if m.role.value == "assistant" else me
        lines += [f"**{label}**" if md else f"{label}:", m.content, ""]
    body = "\n".join(lines)

    name = f"conversa-{slugify(char_name)}-{session.session_id}.{'md' if md else 'txt'}"
    return Response(
        content=body, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ─── BACKUP ───────────────────────────────────────────────────────────────────

# pasta no zip -> pasta real
_DIRS = {"characters": CHARACTERS_DIR, "worlds": WORLDS_DIR, "sessions": SESSIONS_DIR,
         "scenes": SCENES_DIR, "portraits": PORTRAITS_DIR}
_FILES = {"settings.json": SETTINGS_FILE, "profile.json": PROFILE_FILE}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ENTRIES = 20000


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@router.get("/backup")
async def download_backup():
    """Zip com personagens, mundos, conversas, cenas, retratos, configurações e perfil."""
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, real in _DIRS.items():
            for root, _, files in os.walk(real):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, real).replace(os.sep, "/")
                    z.write(full, f"{folder}/{rel}")
        for name, real in _FILES.items():
            if os.path.exists(real):
                z.write(real, name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return FileResponse(
        tmp.name, media_type="application/zip", filename=f"rpg-ia-backup-{stamp}.zip",
        background=BackgroundTask(_remove, tmp.name),
    )


def _check_entry(name: str, raw: bytes):
    """Devolve (destino, None) se o arquivo do backup pode ser restaurado, ou (None, motivo)."""
    if "\\" in name or name.startswith("/") or ".." in name.split("/"):
        return None, "caminho inválido"
    norm = posixpath.normpath(name)
    if norm in _FILES:
        try:
            data = json.loads(raw)
            if norm == "profile.json":
                PlayerProfile(**data)
            elif not isinstance(data, dict) or not set(data) <= set(DEFAULTS):
                return None, "configurações inválidas"
        except (ValueError, ValidationError) as e:
            return None, f"inválido ({str(e)[:60]})"
        return _FILES[norm], None

    parts = norm.split("/")
    if len(parts) < 2 or parts[0] not in _DIRS:
        return None, "pasta não reconhecida"
    folder, rel = parts[0], "/".join(parts[1:])
    ext = os.path.splitext(rel)[1].lower()
    stem = os.path.splitext(parts[-1])[0]

    if folder in ("characters", "worlds", "sessions"):
        if len(parts) != 2 or ext != ".json" or not is_safe_id(stem):
            return None, "nome de arquivo inválido"
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("id", data.get("session_id")) != stem:
                return None, "id não bate com o nome do arquivo"
            if folder == "characters":
                validate_character(Character(**data))      # inclui a regra 18+
            elif folder == "worlds":
                world = World(**data)
                validate_texts(world.name, world.description, world.lore,
                               *[f"{e.name} {e.text}" for e in world.entries])
        except (ValueError, ValidationError) as e:
            return None, f"recusado ({str(e)[:80]})"
    else:  # scenes e portraits: só imagens
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            return None, "só imagens"
        if folder == "scenes" and (len(parts) != 3 or not is_safe_id(parts[1])):
            return None, "caminho de cena inválido"
        if folder == "portraits" and len(parts) != 2:
            return None, "caminho de retrato inválido"
        if not all(p and not p.startswith(".") for p in parts[1:]):
            return None, "nome inválido"
    return os.path.join(_DIRS[folder], *parts[1:]), None


@router.post("/backup/restore")
async def restore_backup(file: UploadFile = File(...), overwrite: bool = Form(False)):
    """
    Restaura um backup sem apagar nada. O que já existe é mantido, a menos que overwrite=true.
    Personagens de menores de idade e arquivos fora do esperado são recusados e listados.
    """
    try:
        z = zipfile.ZipFile(file.file)  # lê direto do arquivo temporário, sem carregar tudo na memória
    except zipfile.BadZipFile:
        raise HTTPException(400, "Isso não parece um arquivo de backup (.zip)")

    restored, skipped, rejected = 0, 0, []
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise HTTPException(400, "Backup grande demais")
    for info in infos:
        if info.file_size > MAX_FILE_BYTES:
            rejected.append({"file": info.filename, "reason": "arquivo grande demais"})
            continue
        data = z.read(info)
        dest, reason = _check_entry(info.filename, data)
        if reason:
            rejected.append({"file": info.filename, "reason": reason})
            continue
        if os.path.exists(dest) and not overwrite:
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        restored += 1
    return {"restored": restored, "skipped_existing": skipped, "rejected": rejected}
