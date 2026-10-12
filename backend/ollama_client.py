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
from backend.lorebook import lore_block
from backend.models import Message
from backend.rpg_engine import build_cast_context, build_rpg_context
from backend.rpg_models import GameMode, RPGState
from backend.settings_manager import get_settings

_LENGTH_RULES = {
    "short":  "Respostas curtas: 1 a 2 parágrafos.",
    "medium": "Respostas de tamanho médio: 2 a 4 parágrafos, com detalhe e imersão.",
    "long":   "Respostas longas e ricas: 3 a 5 parágrafos, com descrição sensorial e emoção.",
}


# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

def build_system_prompt(
    character,
    world=None,
    rpg_state: Optional[RPGState] = None,
    memory_summary: str = "",
    response_length: str = "medium",
    lore_entries=None,
    profile=None,
) -> str:
    """Monta o system prompt completo: personagem + mundo + RPG + memória + regras."""
    world_context = ""
    if world:
        world_context = f"""
## Mundo: {world.name}
{world.description}

### Lore e regras do mundo:
{world.lore}
{lore_block(lore_entries or [])}"""

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

    has_player = bool(rpg_state and rpg_state.player and rpg_state.player.name)
    player_name = "o jogador"
    if has_player:
        player_name = rpg_state.player.name
    elif profile and profile.name:
        player_name = profile.name
    profile_context = build_profile_context(profile, has_player)

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
                    "- Quando alguém fala, comece o trecho com **Nome:** para deixar claro quem é. No máximo 2 personagens falam "
                    "em cada resposta, escolhidas conforme o lugar, o clima e quem o jogador procurou; as outras ficam em silêncio "
                    "ou aparecem só num gesto curto.\n"
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
{example}{world_context}{mode_instructions}{rpg_context}{profile_context}{memory}
## Regras do roleplay:
{identity}
- Escreva ações e narração entre *asteriscos* e as falas entre aspas.
- Avance a história a cada resposta: traga um detalhe novo, uma reação, uma pergunta ou uma complicação. Não repita o que já foi dito nem resuma o que o jogador acabou de fazer.
- Mantenha a consistência com a personalidade, o cenário e o que já aconteceu.
- Este é um mundo adulto e todos os personagens são adultos. Tensão sexual, atração e cenas íntimas
  são parte natural da narrativa. Quando a história caminhar para esse território, descreva com
  detalhe e imersão, sem cortar ou censurar. A história, os personagens e o drama vêm primeiro.
- {length_rule}
- Escreva SEMPRE em português do Brasil, natural e coloquial (nada de inglês nem português de Portugal)."""


def build_profile_context(profile, has_player: bool) -> str:
    """
    Quem é o jogador, vindo do perfil salvo. Se a história já criou um jogador (modo médio e
    completo), nome, idade e aparência dele valem e o perfil só acrescenta o jeito de agir.
    """
    if not profile:
        return ""
    lines = []
    if not has_player:
        if profile.name:
            lines.append(f"- Nome: {profile.name} ({profile.age} anos)")
        if profile.appearance:
            lines.append(f"- Aparência: {profile.appearance}")
    if profile.about:
        lines.append(f"- Jeito de agir e falar: {profile.about}")
    if not lines:
        return ""
    return "\n## Sobre o jogador (a pessoa com quem você está falando):\n" + "\n".join(lines) + "\n"


# ─── FILTRO DE RACIOCÍNIO ─────────────────────────────────────────────────────

class ThinkFilter:
    """
    Remove blocos <think>...</think> (modelos de raciocínio como deepseek-r1) de um
    stream de tokens. As tags podem chegar partidas entre tokens, então o filtro
    segura o que pode ser o começo de uma tag até saber o que é.

    Alguns modelos (qwen3) já começam "dentro" do raciocínio, sem o <think> de abertura:
    se um </think> aparece sem abertura, tudo o que saiu antes era raciocínio e `restart`
    fica True para quem lê o stream descartar o que já mostrou.
    """
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False
        self._seen_open = False
        self.restart = False

    def feed(self, text: str) -> str:
        self._buf += text
        out = []
        while True:
            if not self._inside and not self._seen_open:
                close = self._buf.find(self.CLOSE)
                opening = self._buf.find(self.OPEN)
                if close >= 0 and (opening < 0 or close < opening):
                    out = []
                    self._buf = self._buf[close + len(self.CLOSE):].lstrip()
                    self._seen_open = self.restart = True
                    continue
            tag = self.CLOSE if self._inside else self.OPEN
            idx = self._buf.find(tag)
            if idx >= 0:
                if not self._inside:
                    out.append(self._buf[:idx])
                    self._seen_open = True
                self._buf = self._buf[idx + len(tag):]
                self._inside = not self._inside
                continue
            # Sem tag completa: segura só o sufixo que pode virar uma tag (de abertura ou de fechamento).
            tags = (tag,) if self._inside or self._seen_open else (self.OPEN, self.CLOSE)
            hold = 0
            for n in range(min(len(self.CLOSE) - 1, len(self._buf)), 0, -1):
                if any(t.startswith(self._buf[-n:]) for t in tags):
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
    if "</think>" in text and "<think>" not in text.split("</think>", 1)[0]:
        text = text.split("</think>", 1)[1]   # raciocínio sem a tag de abertura
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


# Modelos bons de roleplay em português que cabem numa GPU de 6 GB, do preferido para o último.
PREFERRED_MODELS = ("qwen3.5-abliterated", "qwen3-abliterated:4b-instruct", "dolphin3", "llama3.1:8b",
                    "dolphin-mistral", "mistral")
# Embeddings não conversam; modelos de raciocínio gastam a resposta pensando.
_NOT_FOR_CHAT = re.compile(r"embed|r1\b|qwq|thinking|(^|/)qwen3(\.5)?:", re.I)
FALLBACK_MODEL = "llama3.1:8b"


def pick_model(models: List[str]) -> str:
    """Escolha automática: o primeiro da lista de preferência que estiver instalado, senão
    qualquer modelo de chat que não seja de raciocínio."""
    chat = [m for m in models if not _NOT_FOR_CHAT.search(m)]
    for key in PREFERRED_MODELS:
        for m in chat:
            if key in m.lower():
                return m
    return chat[0] if chat else FALLBACK_MODEL


async def resolve_model() -> str:
    """Modelo configurado, ou a escolha automática entre os instalados."""
    configured = get_settings()["model"]
    if configured:
        return configured
    try:
        models = await list_models()
    except Exception:
        models = []
    return pick_model(models)


_REPLY_TOKENS = {"short": 300, "medium": 550, "long": 900}


def reply_tokens(settings: Dict) -> int:
    """Tokens reservados para a resposta do chat: o que o tamanho pedido usa, com num_predict como teto.
    A memória (memory.history_budget) reserva o mesmo número, então prompt + resposta cabem em num_ctx."""
    return min(settings["num_predict"], _REPLY_TOKENS.get(settings["response_length"], 550))


def _options(settings: Dict, num_predict: Optional[int] = None) -> dict:
    return {
        "temperature":    settings["temperature"],
        "top_p":          settings["top_p"],
        "min_p":          settings["min_p"],
        "repeat_penalty": settings["repeat_penalty"],
        # 64 (padrão do Ollama) só olha uma frase para trás; muito mais que isso pune palavras comuns do português.
        "repeat_last_n":  128,
        "num_ctx":        settings["num_ctx"],
        "num_predict":    num_predict or reply_tokens(settings),
    }


# Fim de turno dos templates (ChatML, Llama 3, Mistral, Gemma). Um "stop" próprio SUBSTITUI os do
# Modelfile, então eles precisam estar aqui também.
_TEMPLATE_STOPS = ["<|im_start|>", "<|im_end|>", "<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>",
                   "[INST]", "</s>", "<end_of_turn>"]
# Marcas do lembrete do turno: se o modelo começar a copiá-lo, para na hora.
NOTE_MARKERS = ("[Lembrete", "(OOC", "OOC:")


def chat_stops(player_name: str) -> List[str]:
    """Onde a geração para: antes de o modelo escrever o turno do jogador, ou de copiar o lembrete."""
    names = ["Você", "Jogador", "User"]
    if player_name and player_name != "o jogador":
        names.insert(0, player_name)
    stops = []
    for n in names:
        stops += [f"\n{n}:", f"\n**{n}:**", f"\n**{n}**:"]
    return stops + list(NOTE_MARKERS) + _TEMPLATE_STOPS


def player_name_for(rpg_state, profile) -> str:
    if rpg_state and rpg_state.player and rpg_state.player.name:
        return rpg_state.player.name
    if profile and profile.name:
        return profile.name
    return "o jogador"


def turn_reminder(character, player_name: str, last_user: str) -> str:
    """Lembrete curto que vai DEPOIS do histórico. Modelos pequenos (7B/8B) esquecem as regras do
    começo do prompt quando a conversa cresce; colado na mensagem do jogador, o lembrete pesa mais."""
    group = getattr(character, "group", False)
    de = "do jogador" if player_name == "o jogador" else f"de {player_name}"
    # Sem cabeçalho fixo nem citação da fala do jogador: modelos pequenos copiam os dois na resposta.
    lines = ["(OOC: instruções só para você, não repita nem comente.)"]
    if last_user.strip():
        lines.append(f"- Reaja ao que {player_name} acabou de fazer ou perguntar logo acima, sem repetir as palavras "
                     f"{de}. Se foi uma pergunta, alguém responde de verdade.")
    if group:
        lines.append("- No máximo 2 personagens falam. As outras ficam quietas ou só aparecem num gesto curto. "
                     "Não traga gente nova para a cena sem motivo.")
    lines.append(f"- Fale com {player_name} sempre por \"você\", nunca por \"ele\" ou \"dele\".")
    lines.append("- Use só nomes, lugares e regras que já apareceram na ficha, no mundo ou na conversa. "
                 "Se precisar de algo novo, apresente com clareza em vez de citar como se o jogador já soubesse.")
    lines.append(f"- Não escreva falas, pensamentos nem decisões {de}.")
    lines.append("- Responda em português do Brasil.")
    return "\n".join(lines)


# Sinal que stream_chat manda quando descobre que o que já saiu era raciocínio: quem lê descarta o texto.
RESTART = "\x00restart"


async def _raise_for_ollama(response: httpx.Response, model: str) -> None:
    """Erro HTTP do Ollama com a causa real (vem no corpo, em {"error": ...})."""
    if response.status_code < 400:
        return
    if response.status_code == 404:
        raise OllamaError(f"Modelo '{model}' não instalado. Rode: ollama pull {model}")
    body = (await response.aread()).decode(errors="ignore")
    try:
        msg = json.loads(body).get("error") or body
    except (ValueError, AttributeError):
        msg = body
    hint = " Escolha um modelo menor ou diminua o contexto (num_ctx)." if "memory" in str(msg).lower() else ""
    raise OllamaError(f"O Ollama recusou o pedido: {str(msg)[:200]}.{hint}")


async def stream_chat(messages: List[Message], system_prompt: str, temperature: Optional[float] = None,
                      stop: Optional[List[str]] = None, info: Optional[dict] = None) -> AsyncIterator[str]:
    """Faz streaming da resposta token por token, já sem blocos de raciocínio.
    `info`, se passado, recebe o done_reason do Ollama ("length" = cortada pelo limite de tokens)."""
    settings = get_settings()
    model = await resolve_model()
    options = _options(settings)
    if temperature is not None:
        options["temperature"] = temperature
    if stop:
        options["stop"] = stop
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + [
            {"role": m.role.value, "content": m.content} for m in messages
        ],
        "stream": True,
        "think": False,   # modelos de raciocínio respondem direto em vez de gastar a resposta pensando
        "keep_alive": settings["keep_alive"],
        "options": options,
    }
    think = ThinkFilter()
    wrote = thought = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                await _raise_for_ollama(response, model)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise OllamaError(str(data["error"]))
                    message = data.get("message", {})
                    thought = thought or bool(message.get("thinking"))
                    token = message.get("content", "")
                    if token:
                        clean = think.feed(token)
                        if think.restart:
                            think.restart = False
                            yield RESTART
                        if clean:
                            wrote = wrote or bool(clean.strip())
                            yield clean
                    if data.get("done"):
                        if info is not None:
                            info["done_reason"] = data.get("done_reason", "")
                        break
        tail = think.flush()
        if tail:
            wrote = wrote or bool(tail.strip())
            yield tail
        if thought and not wrote:
            raise OllamaError("Este modelo só pensou e não respondeu (modelo de raciocínio). "
                              "Escolha outro modelo nas Configurações.")
    except httpx.ConnectError:
        raise OllamaError("Ollama offline. Inicie com 'ollama serve'.")
    except httpx.TimeoutException:
        raise OllamaError("O modelo demorou demais para responder.")
    except httpx.HTTPError as e:
        raise OllamaError(f"A conexão com o Ollama caiu: {e}")


async def complete(prompt: str, system: str = "", num_predict: int = 300, temperature: float = 0.3,
                   json_mode: bool = False) -> str:
    """Chamada simples sem streaming, para tarefas internas (resumo, tags de cena).
    json_mode pede ao Ollama uma resposta que seja JSON válido."""
    settings = get_settings()
    model = await resolve_model()
    options = _options(settings, num_predict)
    options["temperature"] = temperature
    options["repeat_penalty"] = 1.0   # JSON, listas e resumos repetem chaves e nomes de propósito
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            payload = {
                "model": model, "messages": messages, "stream": False, "think": False,
                "keep_alive": settings["keep_alive"], "options": options,
            }
            if json_mode:
                payload["format"] = "json"
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            await _raise_for_ollama(r, model)
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
