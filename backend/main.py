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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR, HOST, PORT, PORTRAITS_DIR, SCENES_DIR
from backend.routers import characters, chat, images, sessions, system

app = FastAPI(title="RPG IA", version="3.0.0")

# O servidor só escuta em 127.0.0.1, então não há CORS aberto: o frontend é servido por aqui mesmo.
os.makedirs(PORTRAITS_DIR, exist_ok=True)
os.makedirs(SCENES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
app.mount("/scenes", StaticFiles(directory=SCENES_DIR), name="scenes")

for module in (system, characters, sessions, chat, images):
    app.include_router(module.router)


@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
