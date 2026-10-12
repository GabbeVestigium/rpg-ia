"""Correções do núcleo da narração: resposta cortada, regenerar que falha, edição antiga e modelo."""

from test_api import _inventory, _medium_session, new_session, sse_events


def test_reply_cut_mid_stream_is_saved_marked_and_not_sent_back(client, services):
    sid = new_session(client)
    services["reply"] = "*Ela abre a porta devagar e olha para o corredor escuro.* \"Quem está aí?\""
    services["error_mid_stream"] = True
    events = sse_events(client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"}))
    errors = [e["message"] for e in events if e["type"] == "error"]
    assert errors and "runner crashed" in errors[0] and errors[0].startswith("O Ollama deu erro")
    saved = client.get(f"/api/session/{sid}").json()["history"][-1]["content"]
    assert saved.endswith("*(resposta interrompida)*")              # não passa por resposta final
    assert any(e["type"] == "replace" and e["text"] == saved for e in events)

    services["error_mid_stream"] = False
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Sou eu"})
    sent = " ".join(m["content"] for m in services["chat_calls"][-1]["messages"])
    assert "interrompida" not in sent                               # a marca não volta para o modelo


def test_failed_regenerate_puts_the_inventory_back(client, services):
    sid = _medium_session(client)
    services["inventory_reply"] = '{"gain":[{"name":"Chave","qty":1,"type":"key"}],"lose":[],"gold":0}'
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Pego a chave"})
    assert _inventory(client, sid)[0]["Chave"] == 1
    services["fail_chat"] = True
    client.post("/api/chat/regenerate", json={"session_id": sid, "character_id": "trama"})
    assert _inventory(client, sid)[0].get("Chave") == 1             # a resposta antiga voltou, e a chave também
    services["fail_chat"] = False
    client.post("/api/chat/undo", json={"session_id": sid, "character_id": "trama"})
    assert "Chave" not in _inventory(client, sid)[0]                # e desfazer ainda tira a chave


def test_editing_old_message_redoes_summary_from_scratch(client, services):
    sid = new_session(client)
    for i in range(3):
        client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": f"mensagem {i}"})
    from backend.session_manager import load_session, save_session
    s = load_session(sid)
    s.summary, s.summarized_upto = "Resumo antigo", 5
    save_session(s)
    client.post("/api/session/edit", json={"session_id": sid, "index": 2, "content": "Texto corrigido"})
    mem = client.get(f"/api/session/{sid}/memory").json()
    assert mem["summary"] == "" and mem["summarized_upto"] == 0   # o resumo antigo tinha o texto velho


def test_summary_chunk_fits_the_context():
    from backend.memory import _chunk_end
    from backend.models import Message, MessageRole, SessionData
    long = "palavra " * 600   # ~1800 tokens estimados por mensagem
    s = SessionData(session_id="x", character_id="y",
                    history=[Message(role=MessageRole.USER, content=long) for _ in range(40)])
    end = _chunk_end(s, 40)
    assert 1 <= end < 40                                             # nunca 40 mensagens de uma vez


def test_status_says_when_configured_model_is_missing(client):
    client.put("/api/settings", json={"model": "modelo-apagado:7b"})
    d = client.get("/api/status").json()
    assert d["status"] == "online" and "não instalado" in d["active_model"]


def test_auto_pick_prefers_rp_models_and_skips_thinking_ones():
    from backend.ollama_client import pick_model
    installed = ["qwen3:4b", "deepseek-r1:7b", "nomic-embed-text", "dolphin-mistral:7b",
                 "huihui_ai/qwen3-abliterated:4b-instruct-2507-q4_K_M", "llama3.1:8b"]
    assert pick_model(installed) == "huihui_ai/qwen3-abliterated:4b-instruct-2507-q4_K_M"
    assert pick_model(["qwen3:4b", "deepseek-r1:7b", "llama3.1:8b"]) == "llama3.1:8b"
    assert pick_model(["qwen3.5:2b", "deepseek-r1:7b"]) == "llama3.1:8b"   # nunca cai num de raciocínio


def test_chat_payload_turns_thinking_off_and_stops_at_player_turn(client, services):
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    call = services["chat_calls"][-1]
    stops = call["options"]["stop"]
    assert call["think"] is False and "\nVocê:" in stops and "<|eot_id|>" in stops and "<|im_end|>" in stops
    assert call["options"]["repeat_last_n"] == 128


def test_internal_calls_have_no_repeat_penalty_and_think_off(client, services):
    client.put("/api/settings", json={"auto_choices": True})
    sid = new_session(client)
    client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"})
    side = [c for c in services["chat_calls"] if not c.get("stream", True)]
    assert side and all(c["think"] is False and c["options"]["repeat_penalty"] == 1.0 for c in side)


def test_empty_reply_gives_a_portuguese_error_and_drops_the_message(client, services):
    sid = new_session(client)
    before = len(client.get(f"/api/session/{sid}").json()["history"])
    services["reply"] = "<think>só pensando</think>"
    events = sse_events(client.post("/api/chat", json={"session_id": sid, "character_id": "trama", "message": "Oi"}))
    assert any(e["type"] == "error" and "não respondeu" in e["message"] for e in events)
    assert len(client.get(f"/api/session/{sid}").json()["history"]) == before


def test_guard_cuts_copies_player_turn_and_reminder_without_false_positives():
    from backend.loop_guard import guard, reuse_pool
    para = "A chuva batia forte na janela da taverna enquanto ela secava os copos devagar."
    pool = reuse_pool([para + "\n\nOutra coisa qualquer que ela disse antes."])
    text, stop = guard(para + "\n\nAgora algo novo acontece.", pool)
    assert text == "Agora algo novo acontece." and not stop          # trecho reciclado sai, o resto segue
    other = "Ela pega a chave do balcão e entrega sem dizer uma palavra sequer."
    text, stop = guard(f"{other} Um gato mia lá fora. {other} Fim", frozenset())
    assert stop and text.startswith(other) and text.count(other) == 1  # A, X, A no mesmo texto
    assert guard("\"Oi.\"\n**Kael:** eu saio", frozenset(), "Kael") == ("\"Oi.\"", True)
    assert guard("Ela sorri.\n(OOC: instruções", frozenset())[0] == "Ela sorri."
    assert guard("\"Não. Não. Não.\" Ela vira o rosto", frozenset()) == ("\"Não. Não. Não.\" Ela vira o rosto", False)


def test_choices_parser_recovers_broken_json_and_labels():
    from backend.choices import parse_choices
    assert parse_choices('["Abro a porta"], \n["Chamo Lia"], \n["Fujo pela janela"]') == [
        "Abro a porta", "Chamo Lia", "Fujo pela janela"]
    assert parse_choices('["Ousada: Beijo ela", "Cuidadosa:", "*Abro o baú*", "Lia: Vem comigo"]', "Lia") == [
        "Beijo ela", "Abro o baú"]
    assert parse_choices('["Pergunto o preço", "Pago em ouro", "Vou emb') == ["Pergunto o preço", "Pago em ouro"]


def test_think_without_opening_tag_is_dropped():
    from backend.ollama_client import strip_think
    assert strip_think("raciocínio em inglês</think>Resposta.") == "Resposta."


def test_reply_cut_by_token_limit_ends_on_last_sentence():
    from backend.loop_guard import trim_unfinished
    assert trim_unfinished("Ela sorri e olha a porta por um bom tempo. Depois diz que") ==         "Ela sorri e olha a porta por um bom tempo."


def test_history_budget_counts_reply_and_reminder():
    from backend.memory import est_tokens, history_budget
    s = {"num_ctx": 4096, "num_predict": 900, "response_length": "medium"}
    assert history_budget("x" * 2700, s) == 4096 - 550 - est_tokens("x" * 2700) - 100


def test_models_that_ignore_think_off_get_thinking_separated():
    from backend.ollama_client import _think_fields, THINK_EXTRA_TOKENS
    opts = {"num_predict": 500}
    assert _think_fields("qwen3:4b", opts) == {"think": True} and opts["num_predict"] == 500 + THINK_EXTRA_TOKENS
    for m in ("huihui_ai/qwen3-abliterated:4b-instruct-2507-q4_K_M", "qwen3.5:2b", "llama3.1:8b"):
        opts = {"num_predict": 500}
        assert _think_fields(m, opts) == {"think": False} and opts["num_predict"] == 500
