"""Ollama e Stable Diffusion falsos, para testar sem GPU nem modelos."""

import base64
import json
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# 1x1 PNG
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

state = {"chat_calls": [], "unloaded": 0, "txt2img_calls": [], "reply": None, "fail_chat": False}


def make_ollama() -> FastAPI:
    app = FastAPI()

    @app.get("/api/tags")
    async def tags():
        return {"models": [{"name": "fake-rp:8b"}, {"name": "nomic-embed-text"}]}

    @app.post("/api/generate")
    async def generate(req: Request):
        body = await req.json()
        if body.get("keep_alive") == 0:
            state["unloaded"] += 1
        return {"done": True}

    @app.post("/api/chat")
    async def chat(req: Request):
        body = await req.json()
        state["chat_calls"].append(body)
        if state["fail_chat"]:
            return JSONResponse({"error": "boom"}, status_code=500)

        system = body["messages"][0]["content"]
        is_summary = "memória de uma história" in system
        is_tags = "Danbooru" in system
        if is_summary:
            text = "Resumo falso: Lyra e o jogador se conheceram na taverna."
        elif is_tags:
            text = "tavern, night, candlelight, sitting, smile, upper body, 1girl, ELF-ears"
        else:
            text = state["reply"] or "<think>pensando alto</think>*Sorri de leve* \"Olá, viajante.\" Sente-se."

        if not body.get("stream", True):
            return {"message": {"role": "assistant", "content": text}, "done": True}

        async def gen():
            # quebra de propósito no meio das tags <think> para testar o filtro
            chunks = [text[i:i + 4] for i in range(0, len(text), 4)]
            for c in chunks:
                yield json.dumps({"message": {"content": c}, "done": False}) + "\n"
            yield json.dumps({"message": {"content": ""}, "done": True}) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    return app


def make_sd() -> FastAPI:
    app = FastAPI()

    @app.get("/sdapi/v1/sd-models")
    async def models():
        return [{"title": "AOM3"}]

    @app.post("/sdapi/v1/txt2img")
    async def txt2img(req: Request):
        state["txt2img_calls"].append(await req.json())
        return {"images": [PNG_B64]}

    return app


def serve(app: FastAPI, port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server
