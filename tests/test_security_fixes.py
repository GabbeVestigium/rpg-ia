"""Host/Origin (DNS rebinding e CSRF), limites do restore, validação do piper_bin e cache do index."""

import io
import os
import zipfile

from backend import tts_client
from backend.main import host_allowed
from backend.routers import data as data_router


def test_host_allowlist():
    for ok in ("127.0.0.1:8000", "localhost", "[::1]:8000", "testserver", "pc.tail1234.ts.net"):
        assert host_allowed(ok), ok
    for bad in ("evil.com", "127.0.0.1.evil.com", "ts.net.evil.com", "", "[bad"):
        assert not host_allowed(bad), bad


def test_rebinding_host_is_refused(client):
    assert client.get("/api/settings", headers={"host": "evil.com:8000"}).status_code == 400
    assert client.get("/api/settings", headers={"host": "localhost:8000"}).status_code == 200


def test_cross_site_write_is_refused(client):
    body = {"temperature": 0.5}
    assert client.put("/api/settings", json=body, headers={"origin": "https://evil.com"}).status_code == 403
    assert client.put("/api/settings", json=body, headers={"origin": "null"}).status_code == 403
    assert client.put("/api/settings", json=body, headers={"referer": "http://evil.com/x"}).status_code == 403
    assert client.put("/api/settings", json=body, headers={"origin": "http://127.0.0.1:8000"}).status_code == 200
    assert client.put("/api/settings", json=body, headers={"origin": "https://pc.tail1.ts.net"}).status_code == 200
    assert client.put("/api/settings", json=body).status_code == 200            # curl / testes
    assert client.get("/api/settings", headers={"origin": "https://evil.com"}).status_code == 200


def test_index_is_not_cached(client):
    assert client.get("/").headers["cache-control"] == "no-cache"


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_restore_limits_upload_and_uncompressed_size(client, monkeypatch):
    backup = _zip({"scenes/x/a.png": b"\0" * 5000})
    monkeypatch.setattr(data_router, "MAX_TOTAL_BYTES", 4000)
    assert client.post("/api/backup/restore", files={"file": ("b.zip", backup)}).status_code == 400
    monkeypatch.setattr(data_router, "MAX_TOTAL_BYTES", 10 ** 9)
    monkeypatch.setattr(data_router, "MAX_UPLOAD_BYTES", 10)
    assert client.post("/api/backup/restore", files={"file": ("b.zip", backup)}).status_code == 400


def test_piper_bin_refuses_network_and_other_programs(monkeypatch, tmp_path):
    settings = {"piper_bin": "piper", "piper_model": ""}
    monkeypatch.setattr(tts_client, "get_settings", lambda: settings)
    monkeypatch.setattr(tts_client.os.path, "isfile", lambda p: True)       # nada aqui pode tocar a rede
    monkeypatch.setattr(tts_client.shutil, "which", lambda b: None)
    for bad in (r"\\server\share\piper.exe", "//server/share/piper.exe", "/\\server\\piper.exe",
                r"C:\Windows\System32\cmd.exe", "cmd", "piper"):
        settings["piper_bin"] = bad
        assert tts_client._piper_bin() is None, bad
    settings["piper_bin"] = r"C:\piper\piper.exe"
    assert tts_client._piper_bin() == r"C:\piper\piper.exe"
    settings["piper_model"] = r"\\server\voz.onnx"
    assert "Modelo" in tts_client.piper_ready()
    settings["piper_model"] = r"C:\piper\voz.txt"
    assert "Modelo" in tts_client.piper_ready()
    settings["piper_model"] = r"C:\piper\voz.onnx"
    assert tts_client.piper_ready() is None
