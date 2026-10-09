import json
import os

from backend.config import SCENES_DIR


def sse_events(response):
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def reply_text(events):
    return "".join(e["t"] for e in events if e["type"] == "token")


def new_session(client, char="trama", mode="narrative"):
    r = client.post("/api/session/new", json={"character_id": char, "game_mode": mode})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def test_status_picks_chat_model_over_embedding(client):
    d = client.get("/api/status").json()
    assert d["status"] == "online" and d["active_model"] == "fake-rp:8b"


def test_chat_streams_without_think_and_saves(client):
    sid = new_session(client)
    r = client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    events = sse_events(r)
    assert events[-1]["type"] == "done"
    text = reply_text(events)
    assert "pensando" not in text and "<think>" not in text
    assert text.startswith("*Sorri de leve*")
    hist = client.get(f"/api/session/{sid}").json()["history"]
    assert [m["role"] for m in hist] == ["assistant", "user", "assistant"]
    assert hist[-1]["content"] == text.strip()


def test_system_prompt_has_character_and_rules(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    system = services["chat_calls"][0]["messages"][0]["content"]
    assert "Trama" in system and "NUNCA escreva falas" in system
    assert "Exemplos de como você fala" in system
    opts = services["chat_calls"][0]["options"]
    assert opts["num_ctx"] == 4096 and opts["min_p"] == 0.05


def test_ollama_error_reports_and_does_not_keep_dangling_user_msg(client, services):
    sid = new_session(client)
    services["fail_chat"] = True
    r = client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    events = sse_events(r)
    assert any(e["type"] == "error" for e in events) and events[-1]["type"] == "done"
    hist = client.get(f"/api/session/{sid}").json()["history"]
    assert [m["role"] for m in hist] == ["assistant"]


def test_regenerate_replaces_last_reply(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    services["reply"] = "Segunda versão da resposta, bem diferente."
    r = client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    assert "Segunda versão" in reply_text(sse_events(r))
    hist = client.get(f"/api/session/{sid}").json()["history"]
    assert [m["role"] for m in hist] == ["assistant", "user", "assistant"]
    assert hist[-1]["content"].startswith("Segunda versão")


def test_undo_returns_user_text(client):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Minha fala"})
    r = client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"})
    assert r.json()["user_text"] == "Minha fala"
    assert len(client.get(f"/api/session/{sid}").json()["history"]) == 1
    assert client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"}).status_code == 400


def test_edit_message(client):
    sid = new_session(client)
    client.post("/api/session/edit", json={"session_id": sid, "index": 0, "content": "Nova abertura"})
    assert client.get(f"/api/session/{sid}").json()["history"][0]["content"] == "Nova abertura"
    assert client.post("/api/session/edit", json={"session_id": sid, "index": 9, "content": "x"}).status_code == 400


def test_memory_summary_kicks_in_after_window(client, services):
    client.put("/api/settings", json={"history_turns": 4})
    sid = new_session(client)
    for i in range(10):
        client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": f"mensagem {i}"})
    mem = client.get(f"/api/session/{sid}/memory").json()
    assert "Resumo falso" in mem["summary"] and mem["summarized_upto"] > 0
    # a janela enviada ao modelo é limitada, e o resumo entra no system prompt
    last = [c for c in services["chat_calls"] if "Trama" in c["messages"][0]["content"]][-1]
    assert len(last["messages"]) - 1 <= 4 * 2 + 1
    assert "Resumo falso" in last["messages"][0]["content"]
    # o histórico completo continua salvo
    assert len(client.get(f"/api/session/{sid}").json()["history"]) == 21


def test_memory_can_be_edited_by_hand(client):
    sid = new_session(client)
    client.put(f"/api/session/{sid}/memory", json={"summary": "Fato importante"})
    assert client.get(f"/api/session/{sid}/memory").json()["summary"] == "Fato importante"


def test_path_traversal_is_rejected(client):
    assert client.get("/api/session/..%2f..%2fsettings").status_code in (400, 404)
    assert client.get("/api/characters/..%2fx").status_code in (400, 404)
    assert client.get("/api/sd/check-portrait/..%2f..%2fx").status_code in (400, 404)
    assert client.delete("/api/session/..%2f..%2fx").status_code in (400, 404)


def test_character_crud_and_adult_rule(client):
    base = {
        "id": "x", "name": "Nova", "age": 30, "gender": "female", "description": "Ruiva alta.",
        "personality": "Calma.", "scenario": "Uma estrada.", "first_message": "*Acena*",
        "appearance_tags": "1girl, red hair",
    }
    r = client.post("/api/characters", json=base)
    assert r.status_code == 200 and r.json()["id"] == "nova"
    assert client.get("/api/characters/nova").json()["appearance_tags"] == "1girl, red hair"
    assert any(c["id"] == "nova" for c in client.get("/api/characters").json())
    # menor de idade: idade e texto
    assert client.post("/api/characters", json={**base, "age": 17}).status_code == 422
    r = client.post("/api/characters", json={**base, "description": "uma loli"})
    assert r.status_code == 422 and "adultos" in r.json()["detail"]
    assert client.delete("/api/characters/nova").status_code == 200
    assert client.get("/api/characters/nova").status_code == 404


def test_player_must_be_adult(client):
    sid = new_session(client, mode="medium")
    body = {"session_id": sid, "name": "Kael", "race": "humano", "char_class": "guerreiro",
            "mode": "medium", "age": 17}
    assert client.post("/api/player/create", json=body).status_code == 422
    body.update(age=25, appearance="tem 15 anos")
    assert client.post("/api/player/create", json=body).status_code == 422
    body.update(appearance="alto, cicatriz")
    assert client.post("/api/player/create", json=body).status_code == 200


def test_full_mode_auto_roll_event(client):
    sid = new_session(client, mode="full")
    client.post("/api/player/create", json={
        "session_id": sid, "name": "Kael", "race": "humano", "char_class": "guerreiro", "mode": "full",
        "attributes": {"STR": 14, "DEX": 12, "CON": 12, "INT": 10, "WIS": 10, "CHA": 10}})
    r = client.post("/api/chat", json={"session_id": sid, "character_id": "trama",
                                       "message": "Eu ataco o goblin com minha espada"})
    types = [e["type"] for e in sse_events(r)]
    assert types[0] == "roll" and types[-1] == "done"


def test_scene_generation_unloads_llm_and_saves_image(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    r = client.post("/api/scene/generate", json={"session_id": sid})
    assert r.status_code == 200, r.text
    data = r.json()
    assert services["unloaded"] == 1
    call = services["txt2img_calls"][0]
    assert "tavern" in call["prompt"] and "blue cybernetic eyes" in call["prompt"]  # tags da cena + aparência fixa
    assert "elf-ears" in call["prompt"]
    assert "child" in call["negative_prompt"] and "nsfw" in call["negative_prompt"]  # SFW por padrão
    assert os.path.exists(os.path.join(SCENES_DIR, data["url"].split("/scenes/")[1]))
    assert client.get(data["url"]).status_code == 200
    assert client.get(f"/api/session/{sid}").json()["images"][0]["url"] == data["url"]


def test_scene_nsfw_setting_only_changes_negative(client, services):
    client.put("/api/settings", json={"sd_nsfw": True})
    sid = new_session(client)
    client.post("/api/scene/generate", json={"session_id": sid})
    neg = services["txt2img_calls"][0]["negative_prompt"]
    assert "child" in neg and "nsfw" not in neg  # a trava de menor de idade nunca sai


def test_portrait_generation(client):
    r = client.post("/api/sd/generate-portrait", json={"character_id": "trama"})
    assert r.status_code == 200 and r.json()["cached"] is False
    assert client.get("/api/sd/check-portrait/trama").json()["exists"] is True
    assert client.post("/api/sd/generate-portrait", json={"character_id": "trama"}).json()["cached"] is True
    assert client.delete("/api/sd/delete-portrait/trama").status_code == 200


def test_tts_without_piper_reports_clearly(client):
    client.put("/api/settings", json={"tts_engine": "piper"})
    r = client.post("/api/tts", json={"text": "*olha* \"Oi\""})
    assert r.status_code == 503 and "Piper" in r.json()["detail"]


def test_group_character_prompt_makes_narrator_play_the_cast(client, services):
    sid = new_session(client, char="mesa-javali")
    client.post("/api/chat", json={"session_id": sid, "character_id": "mesa-javali", "message": "Oi"})
    system = services["chat_calls"][0]["messages"][0]["content"]
    assert "narrador" in system and "TODAS as personagens" in system and "**Nome:**" in system
    assert "Controle apenas" not in system
    for name in ("Yasmin", "Helena", "Iara", "Lavínia", "Cléo", "Violeta", "Bianca"):
        assert name in system


def test_shipped_characters_are_valid_adults(client):
    chars = client.get("/api/characters").json()
    assert {c["id"] for c in chars} >= {"mesa-javali", "trama", "sibila"}
    assert all(c["age"] >= 18 for c in chars)


def _scores(client, sid):
    return {c["id"]: c["score"] for c in client.get(f"/api/session/{sid}").json()["cast"]}


def test_group_has_one_relationship_per_cast_member(client, services):
    sid = client.post("/api/session/new", json={"character_id": "mesa-javali", "game_mode": "medium"}).json()["session_id"]
    client.post("/api/player/create", json={"session_id": sid, "name": "Tonico", "race": "humano",
                                            "char_class": "bardo", "mode": "medium", "age": 25})
    before = _scores(client, sid)
    assert before["yasmin"] == 35 and before["cleo"] == 70 and len(before) == 7  # cada uma com a sua largada

    client.post("/api/chat", json={"session_id": sid, "character_id": "mesa-javali",
                                   "message": "Obrigado, Yasmin, eu confio em você"})
    after = _scores(client, sid)
    assert after["yasmin"] > before["yasmin"]                                   # a citada subiu
    assert all(after[k] == before[k] for k in before if k != "yasmin")        # as outras não mexeram

    # o prompt do modelo traz o sentimento de cada uma
    system = services["chat_calls"][-1]["messages"][0]["content"]
    assert "Como cada uma se sente" in system and "Yasmin:" in system and "Cléo:" in system
    assert "Relacionamento com você" not in system


def test_group_narrative_mode_has_no_cast_tracking(client):
    sid = new_session(client, char="mesa-javali", mode="narrative")
    assert client.get(f"/api/session/{sid}").json()["cast"] == []


def test_editing_group_character_keeps_its_cast(client):
    c = client.get("/api/characters/mesa-javali").json()
    c["summary"] = "novo resumo"
    assert client.put("/api/characters/mesa-javali", json=c).status_code == 200
    assert len(client.get("/api/characters/mesa-javali").json()["cast"]) == 7


def test_static_files_are_revalidated(client):
    r = client.get("/static/js/main.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert "javascript" in r.headers["content-type"]


def _swipe(client, sid):
    return client.get(f"/api/session/{sid}").json()["swipe"]


def test_regenerate_keeps_previous_versions_and_swipe_navigates(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    first = client.get(f"/api/session/{sid}").json()["history"][-1]["content"]
    assert _swipe(client, sid) == {"index": 0, "count": 0}            # sem alternativas ainda

    services["reply"] = "Segunda versão, completamente diferente da primeira."
    client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    services["reply"] = "Terceira versão, ainda diferente das outras duas."
    client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    assert _swipe(client, sid) == {"index": 2, "count": 3}
    assert len(client.get(f"/api/session/{sid}").json()["history"]) == 3  # nada duplicado

    back = client.post("/api/chat/swipe", json={"session_id": sid, "delta": -1}).json()
    assert back["content"].startswith("Segunda") and back["index"] == 1
    back = client.post("/api/chat/swipe", json={"session_id": sid, "delta": -5}).json()
    assert back["content"] == first and back["index"] == 0           # limita na primeira
    assert client.get(f"/api/session/{sid}").json()["history"][-1]["content"] == first
    nxt = client.post("/api/chat/swipe", json={"session_id": sid, "delta": 1}).json()
    assert nxt["content"].startswith("Segunda")


def test_failed_regenerate_restores_the_previous_reply(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    before = client.get(f"/api/session/{sid}").json()["history"]
    services["fail_chat"] = True
    r = client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    assert any(e["type"] == "error" for e in sse_events(r))
    assert client.get(f"/api/session/{sid}").json()["history"] == before   # a resposta antiga voltou


def test_new_message_edit_and_undo_handle_swipes(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    services["reply"] = "Versão B da resposta, para termos duas versões."
    client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    # editar a resposta atual atualiza a versão atual
    client.post("/api/session/edit", json={"session_id": sid, "index": 2, "content": "Versão B corrigida."})
    client.post("/api/chat/swipe", json={"session_id": sid, "delta": -1})
    assert client.post("/api/chat/swipe", json={"session_id": sid, "delta": 1}).json()["content"] == "Versão B corrigida."
    # mensagem nova descarta as versões antigas
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "E agora?"})
    assert _swipe(client, sid)["count"] == 0
    assert client.post("/api/chat/swipe", json={"session_id": sid, "delta": -1}).status_code == 400
    # desfazer também descarta
    services["reply"] = "Outra versão qualquer para a nova resposta."
    client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"})
    assert _swipe(client, sid)["count"] == 0


def _system_of_last_chat(services):
    return services["chat_calls"][-1]["messages"][0]["content"]


def test_lore_entry_enters_prompt_only_when_cited(client, services):
    sid = new_session(client, char="mesa-javali")
    client.post("/api/chat", json={"session_id": sid, "character_id": "mesa-javali", "message": "Bora para a Cova de Tarsa"})
    system = _system_of_last_chat(services)
    assert "Fatos que importam agora" in system and "Cova de Tarsa:" in system
    assert "Banhos do Frei Jorge:" not in system                    # não citado, não entra
    client.post("/api/chat", json={"session_id": sid, "character_id": "mesa-javali", "message": "Que tal um banho quente?"})
    system = _system_of_last_chat(services)
    assert "Banhos do Frei Jorge:" in system


def test_lorebook_can_be_edited_and_is_validated(client, services):
    world = client.get("/api/worlds/taquara").json()
    assert len(world["entries"]) >= 10
    world["entries"].append({"name": "Gato do bar", "keys": ["gato"], "text": "Um gato cinza que dorme no balcão."})
    assert client.put("/api/worlds/taquara", json=world).status_code == 200
    saved = client.get("/api/worlds/taquara").json()["entries"][-1]
    assert saved["name"] == "Gato do bar" and saved["id"]           # ganhou um id

    sid = new_session(client, char="trama")
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "O gato do bar sumiu"})
    assert "Gato do bar:" in _system_of_last_chat(services)

    world["entries"].append({"name": "Ruim", "keys": ["x"], "text": "uma personagem de 15 anos"})
    r = client.put("/api/worlds/taquara", json=world)
    assert r.status_code == 422 and "18" in r.json()["detail"]      # a regra 18+ vale no livro também


def test_prompt_size_endpoint_reports_remaining_budget(client):
    p = client.get("/api/characters/mesa-javali/prompt-size").json()
    assert p["num_ctx"] == 4096 and 500 < p["tokens"] < 3500 and p["history_left"] < 2000
    light = client.get("/api/characters/trama/prompt-size").json()
    assert light["history_left"] > p["history_left"]               # a Mesa é mais pesada que a Trama
    assert client.get("/api/characters/nao-existe/prompt-size").status_code == 404


def test_profile_roundtrip_and_adult_rule(client):
    assert client.get("/api/profile").json()["name"] == ""
    ok = {"name": "Tonico Brasa", "age": 29, "appearance": "alto, barba por fazer", "about": "Fala pouco e rói a unha quando mente."}
    assert client.put("/api/profile", json=ok).status_code == 200
    assert client.get("/api/profile").json() == ok
    assert client.put("/api/profile", json={**ok, "age": 17}).status_code == 422
    r = client.put("/api/profile", json={**ok, "appearance": "uma personagem de 15 anos"})
    assert r.status_code == 422
    assert client.get("/api/profile").json() == ok                 # recusado não sobrescreve


def test_profile_reaches_the_prompt_even_in_narrative_mode(client, services):
    client.put("/api/profile", json={"name": "Tonico Brasa", "age": 29, "appearance": "alto, barba por fazer",
                                     "about": "Fala pouco e rói a unha quando mente."})
    sid = new_session(client, char="trama", mode="narrative")
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    system = _system_of_last_chat(services)
    assert "Sobre o jogador" in system and "Tonico Brasa (29 anos)" in system
    assert "barba por fazer" in system and "rói a unha" in system
    assert "NUNCA escreva falas, pensamentos ou ações de Tonico Brasa" in system   # a regra usa o seu nome


def test_created_player_wins_over_profile_but_keeps_the_way_you_act(client, services):
    client.put("/api/profile", json={"name": "Tonico Brasa", "age": 29, "appearance": "alto",
                                     "about": "Fala pouco."})
    sid = new_session(client, char="trama", mode="medium")
    client.post("/api/player/create", json={"session_id": sid, "name": "Kael", "race": "humano",
                                            "char_class": "bardo", "mode": "medium", "age": 31})
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    system = _system_of_last_chat(services)
    assert "Nome: Kael" in system and "Tonico" not in system   # o nome do jogador criado vale, o do perfil não aparece
    assert "Jeito de agir e falar: Fala pouco." in system


def test_no_profile_means_no_extra_section(client, services):
    sid = new_session(client, char="trama")
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    assert "Sobre o jogador" not in _system_of_last_chat(services)
