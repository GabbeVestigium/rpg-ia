import pytest

from backend.ollama_client import ThinkFilter, strip_think
from backend.safety import find_problems, validate_age, validate_texts
from backend.settings_manager import DEFAULTS, get_settings, update_settings
from backend.storage import is_safe_id, slugify


def run_filter(chunks):
    f = ThinkFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_think_filter_removes_block_split_across_tokens():
    assert run_filter(["<th", "ink>segredo</th", "ink>Olá ", "mundo"]) == "Olá mundo"


def test_think_filter_keeps_plain_text_and_lone_angle():
    assert run_filter(["a < b ", "e c > d"]) == "a < b e c > d"


def test_think_filter_unclosed_block_is_dropped():
    assert run_filter(["Oi <think>nunca fecha"]) == "Oi "


def test_strip_think():
    assert strip_think("<think>x</think> resposta") == "resposta"


@pytest.mark.parametrize("text", [
    "Lyra é uma maga de 26 anos", "foi expulsa há 5 anos", "a garota sorriu",
    "a guerra durou 300 anos", "Tem 3 espadas", "childhood trauma",
])
def test_safety_allows_normal_text(text):
    assert find_problems(text) == []


@pytest.mark.parametrize("text", [
    "ela tem 15 anos", "uma loli", "15-year-old girl", "aged 14", "aparência infantil", "teen",
])
def test_safety_blocks_minor_markers(text):
    assert find_problems(text)


def test_validate_age():
    validate_age(18)
    with pytest.raises(ValueError):
        validate_age(17)
    with pytest.raises(ValueError):
        validate_texts("ok", "tem 12 anos")


def test_safe_id_and_slug():
    assert is_safe_id("abc-123_x") and not is_safe_id("../x") and not is_safe_id("")
    assert slugify("Lyra Ashveil!") == "lyra-ashveil"
    assert slugify("???") == "personagem"


def test_settings_clamp_and_ignore_unknown():
    s = update_settings({"temperature": 99, "num_ctx": "abc", "response_length": "huge", "hack": 1})
    assert s["temperature"] == 2.0
    assert s["num_ctx"] == DEFAULTS["num_ctx"]
    assert s["response_length"] == DEFAULTS["response_length"]
    assert "hack" not in s
    assert get_settings()["temperature"] == 2.0


def test_window_respects_token_budget_and_keeps_last_exchange():
    from backend.memory import est_tokens, window_start
    from backend.models import Message, SessionData
    msgs = [Message(role="user" if i % 2 else "assistant", content="x" * 300) for i in range(20)]
    s = SessionData(session_id="t", character_id="c", history=msgs)
    per = est_tokens("x" * 300)
    assert window_start(s, budget=per * 5) == 20 - 5      # cabem 5 mensagens
    assert window_start(s, budget=1) == 20 - 2            # nunca menos que a última troca
    update_settings({"history_turns": 4})
    assert window_start(s, budget=10**6) == 20 - 8        # limite por turnos
