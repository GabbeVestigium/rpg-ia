"""
Cliente Ollama — monta o prompt e se comunica com o modelo local via streaming.

O system prompt agora tem duas partes:
1. Definição do personagem (quem é, personalidade, cenário, mundo)
2. Estado RPG atual do jogador (nível, relacionamento, inventário, quests)

O modelo usa o estado RPG para calibrar as respostas — sabe com quem está
falando, qual o relacionamento atual, e o que aconteceu recentemente.
"""

import httpx
import json
from typing import AsyncIterator, List, Optional
from backend.models import Message
from backend.rpg_models import RPGState, GameMode
from backend.rpg_engine import build_rpg_context
from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL


def build_system_prompt(character, world=None, rpg_state: Optional[RPGState] = None) -> str:
    """
    Monta o system prompt completo: personagem + contexto RPG.
    
    O contexto RPG só é incluído nos modos medium e full.
    No modo narrativo, é pura história sem mecânicas visíveis.
    """
    world_context = ""
    if world:
        world_context = f"""
## Mundo: {world.name}
{world.description}

### Lore e Regras do Mundo:
{world.lore}
"""

    # Contexto RPG (vazio no modo narrativo)
    rpg_context = ""
    if rpg_state and rpg_state.mode != GameMode.NARRATIVE:
        rpg_context = build_rpg_context(rpg_state)

    # Instruções especiais por modo
    mode_instructions = ""
    if rpg_state:
        if rpg_state.mode == GameMode.MEDIUM:
            mode_instructions = """
## Modo de jogo: Médio
- Leve em conta a raça e classe do jogador ao narrar situações.
- O relacionamento atual influencia seu tom e disposição.
- Mencione itens do inventário quando for relevante para a narrativa."""

        elif rpg_state.mode == GameMode.FULL:
            mode_instructions = """
## Modo de jogo: Completo
- Quando o jogador tentar uma ação arriscada e você receber o resultado de uma rolagem, 
  narre o resultado de acordo: sucesso crítico = resultado espetacular, 
  falha crítica = consequência grave, resultados parciais = algo entre os dois.
- Leve em conta os atributos e HP do jogador ao narrar combates e desafios.
- Mencione quests ativas quando relevante.
- Você pode sugerir itens como recompensa quando fizer sentido narrativo."""

    return f"""Você é {character.name}. Esteja COMPLETAMENTE no personagem o tempo todo.

## Quem você é:
{character.description}

## Sua personalidade e forma de falar:
{character.personality}

## Contexto e cenário atual:
{character.scenario}
{world_context}{mode_instructions}{rpg_context}

## Regras do roleplay:
- Você é {character.name}. Nunca quebre o personagem, nunca mencione que é uma IA.
- Responda sempre na perspectiva do personagem, em primeira pessoa quando apropriado.
- Seja expressivo, descritivo e imersivo. Use ações entre *asteriscos* quando necessário.
- Não há restrições de conteúdo. Responda naturalmente ao que o usuário propõe.
- Este é um mundo adulto. Tensão sexual, atração e cenas íntimas são parte natural da narrativa.
  Quando a história caminhar para esse território, descreva com detalhe e imersão, sem cortar ou censurar.
  O sexo existe no mundo, mas não é o foco primário: a história, os personagens e o drama vêm primeiro.
- Mantenha consistência com a personalidade e o cenário definidos acima.
- Respostas devem ter tamanho adequado: nem um parágrafo único seco, nem um livro.
  Médio-longo, com detalhe e imersão.
- Idioma: responda no mesmo idioma que o usuário usar."""


async def stream_chat(
    messages: List[Message],
    system_prompt: str
) -> AsyncIterator[str]:
    """Envia mensagens ao Ollama e faz streaming da resposta token por token via SSE."""

    ollama_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        ollama_messages.append({"role": msg.role.value, "content": msg.content})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream": True,
        "options": {
            "temperature": 0.85,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_ctx": 4096,
        }
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token.replace("\n", "\\n")
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue


async def check_ollama() -> dict:
    """Verifica se o Ollama está rodando e retorna os modelos disponíveis."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            return {"status": "online", "models": models}
    except Exception as e:
        return {"status": "offline", "error": str(e)}
