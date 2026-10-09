import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

# Variáveis precisam existir ANTES de importar backend.config.
_TMP = tempfile.mkdtemp(prefix="rpgia-test-")
os.environ["RPG_DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:18434"
os.environ["SD_API_URL"] = "http://127.0.0.1:18860"
os.environ["RPG_PORTRAITS_DIR"] = os.path.join(_TMP, "portraits")
shutil.copytree(os.path.join(ROOT, "data"), os.environ["RPG_DATA_DIR"], ignore=shutil.ignore_patterns("sessions"))

import fake_services  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def services():
    o = fake_services.serve(fake_services.make_ollama(), 18434)
    s = fake_services.serve(fake_services.make_sd(), 18860)
    yield fake_services.state
    o.should_exit = s.should_exit = True


@pytest.fixture(autouse=True)
def reset_state(services):
    services.update({"chat_calls": [], "unloaded": 0, "txt2img_calls": [], "reply": None, "fail_chat": False,
                    "inventory_reply": '{"gain":[],"lose":[],"gold":0}'})
    # Cada teste começa com configurações e sessões limpas.
    from backend.config import PROFILE_FILE, SESSIONS_DIR, SETTINGS_FILE
    shutil.rmtree(SESSIONS_DIR, ignore_errors=True)
    shutil.rmtree(os.environ["RPG_PORTRAITS_DIR"], ignore_errors=True)  # retratos e expressões
    for f in (SETTINGS_FILE, PROFILE_FILE):
        if os.path.exists(f):
            os.remove(f)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as c:
        yield c
