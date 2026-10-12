"""Mecânicas e texto do prompt: rolagem automática, relação, desfazer, HP, ordem do prompt e "você"."""

from backend.adventure import _NARRATOR
from backend.memory import _transcript
from backend.models import Character, Message, MessageRole
from backend.ollama_client import build_system_prompt
from backend.rpg_engine import auto_relationship_delta, build_rpg_context, create_player, detect_risk_action
from backend.rpg_models import GameMode, RPGState

from test_api import new_session, sse_events


def test_auto_roll_only_on_player_actions_and_with_the_right_attribute():
    assert detect_risk_action("Eu ataco o goblin com minha espada") == "STR"
    assert detect_risk_action("*Pulo o muro*") == "DEX"
    assert detect_risk_action("Vou atirar nele") == "DEX"
    assert detect_risk_action("Tento convencer o guarda") == "CHA"
    assert detect_risk_action("Convenco ela a abrir") == "CHA"          # sem acento também
    assert detect_risk_action("Ameaço o guarda") == "CHA"               # antes caía em STR (chave sem "ç")
    assert detect_risk_action("Lanço uma magia de fogo") == "INT"
    for calm in ("Dei um pulo de susto", "Ela usa salto alto", "Levou um soco", "Corto o pão",
                 "Que golpe de sorte", "Não ataco ninguém", "Oi, tudo bem?"):
        assert detect_risk_action(calm) is None, calm


def test_relationship_delta_respects_negation():
    assert auto_relationship_delta("Gosto de você") > 0
    assert auto_relationship_delta("Não gosto disso") < 0
    assert auto_relationship_delta("Nunca te ataco") == 0
    assert auto_relationship_delta("Não, obrigado") > 0


def _rpg(score: int, mode=GameMode.MEDIUM) -> RPGState:
    rpg = RPGState(mode=mode, player=create_player("Kael", "humano", "bardo", mode))
    rpg.player.relationship.set_score(score)
    rpg.event_log = ["Inventário revertido (troca refeita)"]
    return rpg


def test_neutral_relationship_follows_the_sheet_and_hides_internal_log():
    ctx = build_rpg_context(_rpg(50))
    assert "profissional" not in ctx and "ficha" in ctx
    assert "Evento recente" not in ctx and "revertido" not in ctx


def _char(**kw) -> Character:
    base = dict(id="x", name="Lia", age=30, description="d", personality="p", scenario="Uma taverna.",
                first_message="oi")
    return Character(**{**base, **kw})


def test_prompt_keeps_a_stable_prefix_and_talks_to_the_player_as_voce():
    a = build_system_prompt(_char(), None, _rpg(50), memory_summary="Resumo")
    b = build_system_prompt(_char(), None, _rpg(90), memory_summary="Resumo")
    cut = a.index("## O que já aconteceu")
    assert a[:cut] == b[:cut] and a != b                     # só o fim muda entre turnos (cache do Ollama)
    assert a.index("## Regras do roleplay") < cut < a.index("Estado atual do jogador")
    assert "Cenário de abertura" in a and "Contexto e cenário atual" not in a
    assert "para ele reagir" not in a and 'por "você"' in a


def test_summary_and_adventure_narrator_wording():
    lines = _transcript([Message(role=MessageRole.USER, content="Oi")], "Lia")
    assert lines.startswith("Você (jogador):") and "Jogador:" not in lines
    assert "um personagem)" not in _NARRATOR and "quem mais aparecer" not in _NARRATOR


def _full_session(client):
    sid = new_session(client, mode="full")
    client.post("/api/player/create", json={
        "session_id": sid, "name": "Kael", "race": "humano", "char_class": "guerreiro", "mode": "full",
        "attributes": {"STR": 14, "DEX": 12, "CON": 12, "INT": 10, "WIS": 10, "CHA": 10}})
    return sid


def _player(client, sid):
    return client.get(f"/api/player/{sid}").json()["player"]


def test_undo_reverts_roll_xp_hp_and_relationship(client, services):
    sid = _full_session(client)
    before = _player(client, sid)
    for _ in range(5):   # várias rolagens: alguma dá XP ou dano
        client.post("/api/chat", json={"session_id": sid, "character_id": "trama",
                                       "message": "Obrigado. Eu ataco o goblin"})
        r = client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"})
        assert r.json()["user_text"] == "Obrigado. Eu ataco o goblin"     # sem a tag da rolagem
        assert _player(client, sid) == before


def test_failed_reply_reverts_roll_and_relationship(client, services):
    sid = _full_session(client)
    before = _player(client, sid)
    services["fail_chat"] = True
    events = sse_events(client.post("/api/chat", json={"session_id": sid, "character_id": "trama",
                                                       "message": "Obrigado. Eu ataco o goblin"}))
    assert any(e["type"] == "roll" for e in events)
    assert _player(client, sid) == before


def test_failed_physical_roll_costs_hp_and_calm_turns_heal(client, services, monkeypatch):
    import backend.routers.chat as chat
    monkeypatch.setattr(chat, "roll_d20", lambda m: {"natural": 2, "modifier": m, "final": 2 + m,
                                                     "outcome": "falha", "label": "Falha"})
    sid = _full_session(client)
    hp0 = _player(client, sid)["hp_current"]
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Eu ataco o goblin"})
    hurt = _player(client, sid)["hp_current"]
    assert hurt < hp0
    history = client.get(f"/api/session/{sid}").json()["history"]
    assert "HP" in history[-2]["content"]                    # o narrador recebe o dano junto da rolagem
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Respiro fundo"})
    assert _player(client, sid)["hp_current"] == hurt + 1
