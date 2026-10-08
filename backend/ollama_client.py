"""
Cliente Ollama: monta o prompt, conversa com o modelo local e gerencia a VRAM.

O system prompt tem quatro partes:
1. Definição do personagem (quem é, personalidade, cenário, mundo, falas de exemplo)
2. Estado RPG do jogador (nível, relacionamento, inventário, quests)
3. Memória: resumo da história que já saiu da janela de contexto
4. Regras de roleplay e tamanho da resposta
"""

import json
import re
from typing import AsyncIterator, Dict, List, Optional

import httpx

from backend.config import OLLAMA_BASE_URL
from backend.models import Message
from backend.rpg_engine import build_cast_context, build_rpg_context
from backend.rpg_models import GameMode, RPGState
from backend.settings_manager import get_settings

_LENGTH_RULES = {
    "short":  "Respostas curtas: 1 a 2 parágrafos.",
    "medium": "Respostas de tamanho médio: 2 a 4 parágrafos, com detalhe e imersão.",
    "long":   "Respostas longas e ricas: 4 a 6 parágrafos, com descrição sensorial e emoção.",
}


# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

def build_system_prompt(
    character,
    world=None,
    rpg_state: Optional[RPGState] = None,
    memory_summary: str = "",
    response_length: str = "medium",
) -> str:
    """Monta o system prompt completo: personagem + mundo + RPG + memória + regras."""
    world_context = ""
    if world:
        world_context = f"""
## Mundo: {world.name}
{world.description}

### Lore e regras do mundo:
{world.lore}
"""

    rpg_context = ""
    if rpg_state and rpg_state.mode != GameMode.NARRATIVE:
        group_cast = getattr(character, "group", False) and character.cast and rpg_state.cast_relations
        rpg_context = build_rpg_context(rpg_state, include_relationship=not group_cast)
        if group_cast:
            rpg_context += build_cast_context(character.cast, rpg_state.cast_relations)

    mode_instructions = ""
    if rpg_state:
        if rpg_state.mode == GameMode.MEDIUM:
            mode_instructions = """
## Modo de jogo: Médio
- Leve em conta a raça e a classe do jogador ao narrar situações.
- O relacionamento atual influencia seu tom e sua disposição.
- Mencione itens do inventário quando for relevante para a narrativa."""
        elif rpg_state.mode == GameMode.FULL:
            mode_instructions = """
## Modo de jogo: Completo
- Quando o jogador tentar uma ação arriscada e você receber o resultado de uma rolagem,
  narre de acordo: sucesso crítico = resultado espetacular, falha crítica = consequência grave,
  resultados parciais = algo entre os dois. Nunca ignore o resultado da rolagem.
- Leve em conta os atributos e o HP do jogador ao narrar combates e desafios.
- Mencione quests ativas quando relevante.
- Você pode sugerir itens como recompensa quando fizer sentido narrativo."""

    player_name = "o jogador"
    if rpg_state and rpg_state.player and rpg_state.player.name:
        player_name = rpg_state.player.name

    example = ""
    if getattr(character, "example_dialogue", ""):
        example = f"\n## Exemplos de como você fala:\n{character.example_dialogue}\n"

    memory = ""
    if memory_summary:
        memory = f"\n## O que já aconteceu na história (memória):\n{memory_summary}\n"

    length_rule = _LENGTH_RULES.get(response_length, _LENGTH_RULES["medium"])

    group = getattr(character, "group", False)
    if group:
        intro = (f"Você é o narrador de \"{character.name}\" e interpreta TODAS as personagens do elenco, "
                 "cada uma com voz própria. Esteja COMPLETAMENTE nos papéis o tempo todo.")
        who_title, how_title = "O elenco e a cena:", "Como cada uma age e fala:"
        identity = (f"- Você interpreta o elenco de {character.name}. Nunca quebre o personagem e nunca mencione que é uma IA.\n"
                    "- Quando alguém fala, comece o trecho com **Nome:** para deixar claro quem é. Escolha 1 a 3 personagens por cena, "
                    "conforme o lugar e o clima, e deixe as outras aparecerem quando fizer sentido.\n"
                    f"- Interprete apenas o elenco e o mundo. NUNCA escreva falas, pensamentos ou ações de {player_name}: termine sempre deixando espaço para ele reagir.")
    else:
        intro = f"Você é {character.name}. Esteja COMPLETAMENTE no personagem o tempo todo."
        who_title, how_title = "Quem você é:", "Sua personalidade e forma de falar:"
        identity = (f"- Você é {character.name}. Nunca quebre o personagem e nunca mencione que é uma IA.\n"
                    f"- Controle apenas {character.name}. NUNCA escreva falas, pensamentos ou ações de {player_name}: termine sempre deixando espaço para ele reagir.")

    return f"""{intro}

## {who_title}
{character.description}

## {how_title}
{character.personality}

## Contexto e cenário atual:
{character.scenario}
{example}{world_context}{mode_instructions}{rpg_context}{memory}
## Regras do roleplay:
{identity}
- Escreva ações e narração entre *asteriscos* e as falas entre aspas.
- Avance a história a cada resposta: traga um detalhe novo, uma reação, uma pergunta ou uma complicação. Não repita o que já foi dito nem resuma o que o jogador acabou de fazer.
- Mantenha a consistência com a personalidade, o cenário e o que já aconteceu.
- Este é um mundo adulto e todos os personagens são adultos. Tensão sexual, atração e cenas íntimas
  são parte natural da narrativa. Quando a história caminhar para esse território, descreva com
  detalhe e imersão, sem cortar ou censurar. A história, os personagens e o drama vêm primeiro.
- {length_rule}
- Idioma: responda no mesmo idioma que o jogador usar."""


# ─── FILTRO DE RACIOCÍNIO ─────────────────────────────────────────────────────

class ThinkFilter:
    """
    Remove blocos <think>...</think> (modelos de raciocínio como deepseek-r1) de um
    stream de tokens. As tags podem chegar partidas entre tokens, então o filtro
    segura o que pode ser o começo de uma tag até saber o que é.
    """
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, text: str) -> str:
        self._buf += text
        out = []
        while True:
            tag = self.CLOSE if self._inside else self.OPEN
            idx = self._buf.find(tag)
            if idx >= 0:
                if not self._inside:
                    out.append(self._buf[:idx])
                self._buf = self._buf[idx + len(tag):]
                self._inside = not self._inside
                continue
            # Sem tag completa: segura só o sufixo que pode virar uma tag.
            hold = 0
            for n in range(min(len(tag) - 1, len(self._buf)), 0, -1):
                if tag.startswith(self._buf[-n:]):
                    hold = n
                    break
            emit = self._buf[:len(self._buf) - hold]
            self._buf = self._buf[len(self._buf) - hold:]
            if not self._inside:
                out.append(emit)
            break
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._buf
        self._buf = ""
        return rest


def strip_think(text: str) -> str:
    """Versão não-stream: remove blocos de raciocínio de um texto completo."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.DOTALL)
    return text.strip()


# ─── HTTP ─────────────────────────────────────────────────────────────────────

class OllamaError(Exception):
    """Erro legível para mostrar ao jogador."""


async def list_models() -> List[str]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def resolve_model() -> str:
    """Modelo configurado, ou o primeiro instalado se nenhum foi escolhido."""
    configured = get_settings()["model"]
    if configured:
        return configured
    try:
        models = await list_models()
    except Exception:
        models = []
    # Prefere modelos de chat; embeddings não servem para roleplay.
    chat = [m for m in models if "embed" not in m.lower()]
    return chat[0] if chat else "deepseek-r1:7b"


def _options(settings: Dict, num_predict: Optional[int] = None) -> dict:
    return {
        "temperature":    settings["temperature"],
        "top_p":          settings["top_p"],
        "min_p":          settings["min_p"],
        "repeat_penalty": settings["repeat_penalty"],
        "num_ctx":        settings["num_ctx"],
        "num_predict":    num_predict or settings["num_predict"],
    }


async def stream_chat(messages: List[Message], system_prompt: str) -> AsyncIterator[str]:
    """Faz streaming da resposta token por token, já sem blocos de raciocínio."""
    settings = get_settings()
    model = await resolve_model()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + [
            {"role": m.role.value, "content": m.content} for m in messages
        ],
        "stream": True,
        "keep_alive": settings["keep_alive"],
        "options": _options(settings),
    }
    think = ThinkFilter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise OllamaError(f"Modelo '{model}' não instalado. Rode: ollama pull {model}")
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise OllamaError(str(data["error"]))
                    token = data.get("message", {}).get("content", "")
                    if token:
                        clean = think.feed(token)
                        if clean:
                            yield clean
                    if data.get("done"):
                        break
        tail = think.flush()
        if tail:
            yield tail
    except httpx.ConnectError:
        raise OllamaError("Ollama offline. Inicie com 'ollama serve'.")
    except httpx.TimeoutException:
        raise OllamaError("O modelo demorou demais para responder.")


async def complete(prompt: str, system: str = "", num_predict: int = 300, temperature: float = 0.3) -> str:
    """Chamada simples sem streaming, para tarefas internas (resumo, tags de cena)."""
    settings = get_settings()
    model = await resolve_model()
    options = _options(settings, num_predict)
    options["temperature"] = temperature
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json={
                "model": model, "messages": messages, "stream": False,
                "keep_alive": settings["keep_alive"], "options": options,
            })
            r.raise_for_status()
            return strip_think(r.json().get("message", {}).get("content", ""))
    except httpx.ConnectError:
        raise OllamaError("Ollama offline. Inicie com 'ollama serve'.")
    except httpx.HTTPError as e:
        raise OllamaError(f"Erro ao falar com o Ollama: {e}")


async def unload_model() -> None:
    """Tira o modelo da VRAM (usado antes de gerar imagem na GPU de 6 GB)."""
    try:
        model = await resolve_model()
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{OLLAMA_BASE_URL}/api/generate", json={"model": model, "keep_alive": 0})
    except Exception:
        pass  # se o Ollama estiver offline, não há nada a descarregar


async def check_ollama() -> dict:
    """Verifica se o Ollama está rodando e quais modelos estão instalados."""
    try:
        models = await list_models()
        return {"status": "online", "models": models, "active_model": await resolve_model()}
    except Exception as e:
        return {"status": "offline", "error": str(e), "models": []}
