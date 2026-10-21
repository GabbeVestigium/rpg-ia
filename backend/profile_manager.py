"""Perfil do jogador: salvo em data/profile.json e usado em todas as histórias."""

from pydantic import ValidationError

from backend.config import PROFILE_FILE
from backend.models import PlayerProfile
from backend.storage import read_json, write_json_atomic


def load_profile() -> PlayerProfile:
    data = read_json(PROFILE_FILE)
    if isinstance(data, dict):
        try:
            return PlayerProfile(**data)
        except ValidationError:
            pass  # arquivo editado à mão com algo inválido: volta ao perfil vazio
    return PlayerProfile()


def save_profile(profile: PlayerProfile) -> PlayerProfile:
    write_json_atomic(PROFILE_FILE, profile.model_dump(mode="json"))
    return profile
