"""
Ponto de entrada do servidor FastAPI.

Rotas ficam em backend/routers/:
  system      status, configurações, voz, status do SD
  characters  personagens e mundos
  sessions    sessões, jogador, quests, rolagem
  chat        conversa em streaming, regenerar, desfazer, editar
  images      retratos e cenas
"""

import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import ALLOWED_HOSTS, FRONTEND_DIR, HOST, PORT, PORTRAITS_DIR, SCENES_DIR
from backend.routers import characters, chat, data, images, sessions, system

class NoCacheStatic(StaticFiles):
    """Arquivos do frontend sempre revalidados: depois de um git pull, o navegador não serve JS antigo."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="RPG IA", version="3.0.0")

# O servidor só escuta em 127.0.0.1, então não há CORS aberto: o frontend é servido por aqui mesmo.
# O celular chega pelo `tailscale serve`, que repassa para 127.0.0.1 só para aparelhos da sua conta.
os.makedirs(PORTRAITS_DIR, exist_ok=True)


def host_allowed(netloc: str) -> bool:
    """Host (com ou sem porta, IPv6 entre colchetes) está na lista de ALLOWED_HOSTS?"""
    try:
        name = urlsplit("//" + netloc).hostname
    except ValueError:
        return False
    if not name:
        return False
    return any(name == h or (h.startswith("*.") and name.endswith(h[1:])) for h in ALLOWED_HOSTS)


@app.middleware("http")
async def guard_host_and_origin(request: Request, call_next):
    # DNS rebinding: um site malicioso que aponta o próprio domínio para 127.0.0.1 chega com outro Host.
    if not host_allowed(request.headers.get("host", "")):
        return JSONResponse({"detail": "Host não permitido"}, status_code=400)
    # CSRF: escrita vinda de outra página é recusada; sem Origin/Referer (curl, testes) passa.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        source = request.headers.get("origin") or request.headers.get("referer")
        if source is not None and not host_allowed(urlsplit(source).netloc if "//" in source else ""):
            return JSONResponse({"detail": "Origem não permitida"}, status_code=403)
    return await call_next(request)

os.makedirs(SCENES_DIR, exist_ok=True)

app.mount("/static", NoCacheStatic(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
app.mount("/scenes", StaticFiles(directory=SCENES_DIR), name="scenes")
app.mount("/portraits", NoCacheStatic(directory=PORTRAITS_DIR), name="portraits")

for module in (system, characters, sessions, chat, images, data):
    app.include_router(module.router)


@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


# App instalável no celular: o service worker precisa ser servido da raiz para valer no site todo.
@app.get("/sw.js")
async def service_worker():
    return FileResponse(os.path.join(FRONTEND_DIR, "sw.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(os.path.join(FRONTEND_DIR, "manifest.webmanifest"), media_type="application/manifest+json")


if __name__ == "__main__":
    import uvicorn
    # Sem reload por padrão: no Windows o reload troca o event loop e o Piper (subprocesso) para de funcionar.
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=os.environ.get("RPG_RELOAD") == "1")
