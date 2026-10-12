import os
import shutil

import pytest


@pytest.fixture(autouse=True)
def clean_user_dir():
    from backend.config import DATA_DIR
    shutil.rmtree(os.path.join(DATA_DIR, "user"), ignore_errors=True)
    yield
    shutil.rmtree(os.path.join(DATA_DIR, "user"), ignore_errors=True)


def test_read_json_accepts_bom_and_skips_non_utf8(tmp_path):
    from backend.storage import read_json
    bom = tmp_path / "bom.json"
    bom.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'{"a": "\xe9"}')  # Latin-1, não UTF-8
    assert read_json(str(bom)) == {"a": 1}
    assert read_json(str(bad)) is None


def test_gallery_survives_bad_files(client):
    from backend.config import CHARACTERS_DIR
    with open(os.path.join(CHARACTERS_DIR, "quebrado.json"), "wb") as f:
        f.write(b'{"name": "\xe9"}')
    with open(os.path.join(CHARACTERS_DIR, "lista.json"), "w", encoding="utf-8") as f:
        f.write('[1, 2]')
    r = client.get("/api/characters")
    assert r.status_code == 200 and r.json()


def test_write_json_atomic_retries_when_windows_locks_the_file(tmp_path, monkeypatch):
    from backend import storage
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("em uso")
        real(src, dst)

    monkeypatch.setattr(storage.os, "replace", flaky)
    monkeypatch.setattr(storage.time, "sleep", lambda s: None)
    path = str(tmp_path / "x.json")
    storage.write_json_atomic(path, {"ok": True})
    assert storage.read_json(path) == {"ok": True} and len(calls) == 3


def test_edits_go_to_user_folder_and_builtin_file_is_untouched(client):
    from backend.character_manager import USER_CHARACTERS_DIR
    from backend.config import CHARACTERS_DIR
    builtin = os.path.join(CHARACTERS_DIR, "estela.json")
    before = open(builtin, "rb").read()

    data = client.get("/api/characters/estela").json()
    data["name"] = "Estela Editada"
    assert client.put("/api/characters/estela", json=data).status_code == 200
    assert open(builtin, "rb").read() == before
    assert os.path.exists(os.path.join(USER_CHARACTERS_DIR, "estela.json"))
    assert client.get("/api/characters/estela").json()["name"] == "Estela Editada"
    names = [c["name"] for c in client.get("/api/characters").json()]
    assert "Estela Editada" in names and names.count("Estela Editada") == 1

    # apagar um personagem que vem com o projeto: some da galeria, o arquivo original fica
    assert client.delete("/api/characters/estela").status_code == 200
    assert client.get("/api/characters/estela").status_code == 404
    assert "estela" not in [c["id"] for c in client.get("/api/characters").json()]
    assert open(builtin, "rb").read() == before

    # criar de novo com o mesmo nome reaproveita o id
    data["name"] = "Estela"
    assert client.post("/api/characters", json=data).json()["id"] == "estela"
    assert client.get("/api/characters/estela").status_code == 200


def test_new_character_lives_only_in_user_folder_and_delete_removes_it(client):
    from backend.character_manager import USER_CHARACTERS_DIR
    from backend.config import CHARACTERS_DIR
    data = client.get("/api/characters/estela").json()
    data["name"] = "Nova Pessoa"
    new_id = client.post("/api/characters", json=data).json()["id"]
    assert not os.path.exists(os.path.join(CHARACTERS_DIR, f"{new_id}.json"))
    user_file = os.path.join(USER_CHARACTERS_DIR, f"{new_id}.json")
    assert os.path.exists(user_file)
    assert client.delete(f"/api/characters/{new_id}").status_code == 200
    assert not os.path.exists(user_file)


def test_world_edit_goes_to_user_folder(client):
    from backend.character_manager import USER_WORLDS_DIR
    from backend.config import WORLDS_DIR
    wid = client.get("/api/worlds").json()[0]["id"]
    before = open(os.path.join(WORLDS_DIR, f"{wid}.json"), "rb").read()
    world = client.get(f"/api/worlds/{wid}").json()
    world["name"] = "Mundo Editado"
    assert client.put(f"/api/worlds/{wid}", json=world).status_code == 200
    assert open(os.path.join(WORLDS_DIR, f"{wid}.json"), "rb").read() == before
    assert os.path.exists(os.path.join(USER_WORLDS_DIR, f"{wid}.json"))
    assert client.get(f"/api/worlds/{wid}").json()["name"] == "Mundo Editado"


def test_backup_carries_user_characters_and_restore_goes_to_user_folder(client):
    import io
    import zipfile
    from test_api import _zip_bytes
    data = client.get("/api/characters/estela").json()
    data["name"] = "Minha Criação"
    new_id = client.post("/api/characters", json=data).json()["id"]
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").content))
    assert f"characters/{new_id}.json" in z.namelist() and "characters/estela.json" in z.namelist()
    saved = z.read(f"characters/{new_id}.json")

    # Novo PC: a personagem some e o backup traz ela de volta, por cima de um marcador de apagado.
    assert client.delete(f"/api/characters/{new_id}").status_code == 200
    assert client.delete("/api/characters/estela").status_code == 200
    estela = z.read("characters/estela.json")
    r = client.post("/api/backup/restore", files={"file": ("b.zip", _zip_bytes(
        {f"characters/{new_id}.json": saved, "characters/estela.json": estela}))}, data={"overwrite": "true"}).json()
    assert r["restored"] == 2
    assert client.get(f"/api/characters/{new_id}").json()["name"] == "Minha Criação"
    assert client.get("/api/characters/estela").status_code == 200


def test_undo_keeps_sheet_created_after_the_message(client):
    from test_api import new_session
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    client.post("/api/player/create", json={"session_id": sid, "name": "Kael", "race": "humano",
                                            "char_class": "bardo", "mode": "medium", "age": 30})
    client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"})
    assert client.get(f"/api/player/{sid}").json()["player"]["name"] == "Kael"


def test_short_emphatic_repeat_is_not_a_loop():
    from backend.loop_guard import guard
    text = '"Sim, sim, sim, sim, sim, sim!" *ela ri*'
    assert guard(text) == (text, False)
    assert guard("Estela. " * 13)[1]   # o curto repetido sem fim ainda é cortado
