"""
Narrador de aventuras: o jogador escreve uma ideia e a IA monta a história inteira.

O modelo devolve um JSON com título, cenário, elenco e cena de abertura. Daqui sai um
personagem de grupo comum (o narrador interpreta o elenco), salvo como qualquer outro:
aparece na galeria, dá para editar e jogar nos três modos.
"""

import json
import random
import re
from typing import Optional

from backend.character_manager import load_character, save_character
from backend.models import CastMember, Character
from backend.ollama_client import complete
from backend.safety import MIN_AGE, validate_texts
from backend.storage import slugify

MAX_CAST = 4
ATTEMPTS = 2

GENRES = ["Fantasia", "Isekai", "Cyberpunk", "Terror", "Romance", "Mistério", "Faroeste", "Pós-apocalipse",
          "Ficção científica", "Comédia"]

# "Me surpreenda": ideias de partida para quem não sabe o que escrever.
SURPRISES = [
    "Acordo num navio pirata sem lembrar como cheguei, e a capitã diz que eu perdi uma aposta.",
    "Sou o novo zelador de uma biblioteca onde os livros proibidos sussurram à noite.",
    "Um apagão de três dias em São Paulo, e só eu lembro o que aconteceu no primeiro.",
    "Fui invocado para outro mundo como herói, mas a rainha queria invocar outra pessoa.",
    "Detetive particular em Curitiba, 2077. Uma cliente me paga para encontrar ela mesma.",
    "Herdei uma pousada no litoral que só recebe hóspedes em noite de lua cheia.",
    "Caçador de recompensas no sertão, atrás de uma mulher que dizem ser imortal.",
    "Estação espacial de mineração. O turno da noite parou de responder no rádio.",
    "Sou guarda-costas de uma herdeira que tem certeza de que alguém da família quer matá-la.",
    "A cidade inteira dormiu e não acordou. Só eu e uma desconhecida estamos de pé.",
]

_SYSTEM = (
    "Você é um roteirista de histórias interativas. Recebe a ideia do jogador e cria o começo de uma "
    "aventura para ele jogar. Responda SOMENTE um objeto JSON, em português do Brasil, com estas chaves:\n"
    '- "title": nome da história, até 5 palavras\n'
    '- "emoji": um emoji que represente a história\n'
    '- "tags": 3 a 5 gêneros ou temas curtos, em minúsculas\n'
    '- "summary": 1 ou 2 frases que vendem a história, falando com o jogador por "você"\n'
    '- "setting": o mundo e o lugar, 3 a 5 frases concretas (época, clima, perigo, o que está em jogo)\n'
    '- "player_role": quem o jogador é nesta história, 1 ou 2 frases\n'
    '- "cast": lista de 2 a 4 personagens secundários, cada um com "name", "age" (número, todos adultos, '
    '18 anos ou mais) e "about" (aparência, jeito de falar e o que quer do jogador, 2 frases)\n'
    '- "scenario": onde e quando a história começa, 1 ou 2 frases\n'
    '- "opening": a cena de abertura, 2 a 4 parágrafos curtos. Narre em segunda pessoa ("você"), com ações '
    "entre *asteriscos* e falas entre aspas, e pelo menos um personagem do elenco falando. Termine numa "
    "situação aberta que pede uma decisão do jogador. Nunca escreva falas nem decisões do jogador.\n"
    "Todos os personagens são adultos. Seja específico e original, evite clichês genéricos."
)

_NARRATOR = (
    "Você é o narrador desta aventura. Descreva o mundo com detalhes concretos (som, cheiro, luz), "
    "interprete todos os personagens do elenco e quem mais aparecer, cada um com voz própria. Quando alguém "
    "fala, marque com **Nome:**. O jogador decide o que faz; você narra as consequências, de forma justa: "
    "escolhas boas abrem caminhos, escolhas arriscadas podem dar errado. A cada resposta traga algo novo "
    "(uma pista, uma ameaça, uma reviravolta, um personagem) e termine numa situação que pede uma decisão. "
    "Mantenha o tom de {tone}."
)


def _first_json_object(raw: str) -> Optional[dict]:
    start, end = raw.find("{"), raw.rfind("}")
    if not 0 <= start < end:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _text(value, limit: int) -> str:
    text = re.sub(r"[ \t]+", " ", str(value or "")).strip()
    return text[:limit].strip()


def _age(value) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def build_character(data: dict, idea: str, genre: str = "") -> Character:
    """Transforma o JSON do modelo num personagem de grupo. Levanta ValueError se faltar algo
    essencial ou se alguém do elenco não for adulto."""
    title = _text(data.get("title"), 60)
    opening = _text(data.get("opening"), 3000)
    setting = _text(data.get("setting"), 1200)
    if not title or not opening or not setting:
        raise ValueError("A história veio incompleta.")

    cast_lines, cast = [], []
    for item in (data.get("cast") or [])[:MAX_CAST]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"), 40)
        if not name:
            continue
        age = _age(item.get("age"))
        if age < MIN_AGE:
            raise ValueError(f"{name} não é adulto.")
        cast_lines.append(f"- **{name}** ({age}): {_text(item.get('about'), 400)}")
        member_id = slugify(name) or f"p{len(cast) + 1}"
        if all(m.id != member_id for m in cast):
            cast.append(CastMember(id=member_id, name=name.split()[0], start=50))

    role = _text(data.get("player_role"), 400)
    description = setting
    if role:
        description += f"\n\nVocê: {role}"
    if cast_lines:
        description += "\n\nQuem está na história:\n" + "\n".join(cast_lines)

    tags = [_text(t, 24).lower() for t in (data.get("tags") or []) if _text(t, 24)][:5]
    if genre and genre.lower() not in tags:
        tags.insert(0, genre.lower())
    if "aventura" not in tags:
        tags.append("aventura")

    emoji = _text(data.get("emoji"), 8) or "📜"
    character = Character(
        id="aventura",
        name=title,
        age=25,
        gender="other",
        group=True,
        avatar_emoji=emoji,
        summary=_text(data.get("summary"), 240),
        tags=tags,
        description=description,
        personality=_NARRATOR.format(tone=", ".join(tags[:3])),
        scenario=_text(data.get("scenario"), 400) or _text(idea, 400),
        first_message=opening,
        cast=cast,
    )
    validate_texts(character.summary, character.description, character.scenario, character.first_message)
    return character


def _free_id(title: str) -> str:
    base = slugify(title) or "aventura"
    new_id, n = base, 2
    while load_character(new_id):
        new_id = f"{base}-{n}"
        n += 1
    return new_id


async def create_adventure(idea: str, genre: str = "") -> Character:
    """Pede a história ao modelo (até ATTEMPTS vezes se vier quebrada) e salva."""
    idea = idea.strip() or random.choice(SURPRISES)
    validate_texts(idea)
    prompt = f"Ideia do jogador: {idea}"
    if genre:
        prompt += f"\nGênero: {genre}"
    last_error = "A IA não conseguiu montar a história."
    for _ in range(ATTEMPTS):
        raw = await complete(prompt, system=_SYSTEM, num_predict=1400, temperature=0.9, json_mode=True)
        data = _first_json_object(raw)
        if not data:
            last_error = "A IA respondeu num formato que não deu para ler."
            continue
        try:
            character = build_character(data, idea, genre)
        except ValueError as e:
            last_error = str(e)
            continue
        character.id = _free_id(character.name)
        return save_character(character)
    raise ValueError(f"{last_error} Tente de novo ou mude a ideia.")
