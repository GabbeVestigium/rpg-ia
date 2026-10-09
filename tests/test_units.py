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
    "uma mulher de 26 anos", "a guerra de 5 anos acabou", "ela foi expulsa há 5 anos", "um homem com 40 anos",
])
def test_safety_allows_normal_text(text):
    assert find_problems(text) == []


@pytest.mark.parametrize("text", [
    "ela tem 15 anos", "uma loli", "15-year-old girl", "aged 14", "aparência infantil", "teen",
    "uma personagem de 15 anos", "garota de 17 anos", "um rapaz bem novo de 16 anos", "menina com 12 anos",
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


def test_cast_matching_by_name_alias_and_last_speaker():
    from backend.models import CastMember
    from backend.rpg_engine import cast_targets, last_speaker, match_cast
    cast = [CastMember(id="zelia", name="Zélia", aliases=["maga"]),
            CastMember(id="tui", name="Tuí"), CastMember(id="benedita", name="Benedita", aliases=["irmã"])]
    assert match_cast("obrigado, zelia!", cast) == ["zelia"]            # sem acento também casa
    assert match_cast("Tuí e a irmã vêm comigo", cast) == ["tui", "benedita"]
    assert match_cast("vamos embora", cast) == []
    reply = "**Zélia:** hmpf.\n**Tuí:** *ri alto* oi!\n**Benedita:** querido..."
    assert last_speaker(reply, cast) == "benedita"
    assert cast_targets("obrigado", reply, cast) == ["benedita"]        # sem nome: quem falou por último
    assert cast_targets("Tuí, vem", reply, cast) == ["tui"]             # com nome: só a citada


def test_slugify_avoids_windows_reserved_names():
    assert slugify("Con") == "con-1" and slugify("NUL") == "nul-1" and slugify("Com3") == "com3-1"
    assert slugify("Conan") == "conan"


def _world(*entries):
    from backend.models import World
    return World(id="w", name="W", description="d", entries=list(entries))


def test_lorebook_triggers_by_key_accent_insensitive_and_whole_word():
    from backend.lorebook import select_lore
    from backend.models import LoreEntry
    w = _world(LoreEntry(name="Cova", keys=["cova", "tarsa"], text="ruínas"),
               LoreEntry(name="Graça", keys=["graça"], text="brilho"),
               LoreEntry(name="Rei", keys=["rei"], text="ossúrio"))
    names = lambda texts: [e.name for e in select_lore(w, texts)]
    assert names(["vamos para a Cova de Tarsa"]) == ["Cova"]
    assert names(["a GRACA dele"]) == ["Graça"]                 # sem acento e em maiúscula casa
    assert names(["o reino é grande"]) == []                    # 'rei' dentro de 'reino' não conta
    assert names(["rei e cova"]) == ["Cova", "Rei"]             # a citada por último vem primeiro
    assert select_lore(None, ["cova"]) == [] and select_lore(_world(), ["cova"]) == []


def test_lorebook_most_recent_mention_first_and_budget_cut():
    from backend.lorebook import MAX_CHARS, MAX_ENTRIES, select_lore
    from backend.models import LoreEntry
    many = [LoreEntry(name=f"E{i}", keys=[f"k{i}"], text="x" * 10) for i in range(10)]
    w = _world(*many)
    got = select_lore(w, [" ".join(f"k{i}" for i in range(10))])
    assert len(got) == MAX_ENTRIES and got[0].name == "E9"       # a citada por último vem primeiro
    big = _world(LoreEntry(name="A", keys=["a"], text="x" * (MAX_CHARS - 50)),
                 LoreEntry(name="B", keys=["b"], text="y" * 200))
    # B é a mais recente e entra; A somada estouraria o orçamento de caracteres e é cortada.
    assert [e.name for e in select_lore(big, ["a b"])] == ["B"]


def test_lorebook_always_entries_are_included_without_keys():
    from backend.lorebook import select_lore
    from backend.models import LoreEntry
    w = _world(LoreEntry(name="Regra", keys=[], text="sempre vale", always=True),
               LoreEntry(name="Cova", keys=["cova"], text="ruínas"))
    assert [e.name for e in select_lore(w, ["nada a ver"])] == ["Regra"]
    assert [e.name for e in select_lore(w, ["a cova"])] == ["Regra", "Cova"]


def test_inventory_parse_is_robust_and_capped():
    from backend.inventory_ai import parse_changes
    ok = parse_changes('Claro! {"gain":[{"name":" Chave enferrujada. ","qty":"2","type":"KEY"}],"lose":[],"gold":-5} pronto')
    assert ok == {"gain": [{"name": "Chave enferrujada", "qty": 2, "type": "key"}], "lose": [], "gold": -5}
    assert parse_changes("sem json nenhum") == {"gain": [], "lose": [], "gold": 0}
    assert parse_changes("{quebrado") == {"gain": [], "lose": [], "gold": 0}
    big = parse_changes('{"gain":[' + ",".join('{"name":"i%d"}' % i for i in range(9)) + '],"gold":99999}')
    assert len(big["gain"]) == 3 and big["gold"] == 500                      # limites por troca
    assert parse_changes('{"gain":[{"name":"x","qty":9999,"type":"bomba"}]}')["gain"][0] == {"name": "x", "qty": 20, "type": "misc"}


def test_inventory_apply_revert_and_describe():
    from backend.inventory_ai import apply_changes, describe, revert_changes
    from backend.rpg_models import Inventory, Item
    inv = Inventory(items=[Item(name="Poção de cura", quantity=2)], gold=10)
    done = apply_changes(inv, {"gain": [{"name": "Chave", "qty": 1, "type": "key"}],
                               "lose": [{"name": "poção", "qty": 1}, {"name": "Espada que não tenho", "qty": 1}],
                               "gold": -50})
    assert [i.name for i in inv.items] == ["Poção de cura", "Chave"] and inv.items[0].quantity == 1
    assert inv.gold == 0 and done["gold"] == -10                              # ouro nunca fica negativo
    assert done["lose"] == [{"name": "Poção de cura", "qty": 1, "type": "misc"}]  # item que não existe é ignorado
    assert describe(done) == ["+ Chave", "- Poção de cura", "-10 ouro"]
    revert_changes(inv, done)
    assert {i.name: i.quantity for i in inv.items} == {"Poção de cura": 2} and inv.gold == 10
    assert apply_changes(inv, {"gain": [], "lose": [], "gold": 0}) is None


def test_inventory_trigger_prefilter():
    from backend.inventory_ai import looks_like_item_change
    assert looks_like_item_change("Ela te entrega uma chave", "") and looks_like_item_change("", "eu pego a espada")
    assert looks_like_item_change("Você recebeu 20 moedas", "")
    assert not looks_like_item_change("O vento sopra na torre.", "Oi, tudo bem?")


def test_detect_mood_from_the_end_of_the_reply():
    from backend.mood import detect_mood
    assert detect_mood("*Cora e desvia o olhar* \"Não é nada.\"") == "shy"
    assert detect_mood("*Sorri de leve* \"Olá, viajante.\"") == "happy"
    assert detect_mood("*Rosna e cerra os punhos* \"Saia daqui!\"") == "angry"
    assert detect_mood("*Os olhos marejados, a voz embargada*") == "sad"
    assert detect_mood("*Arregala os olhos, surpresa*") == "surprised"
    assert detect_mood("Ela atravessa a sala e abre a janela.") == "neutral"
    # vale o clima do fim: ria no começo e terminou furiosa
    assert detect_mood("*Riu muito.* " + "x " * 400 + "*Rosna, furiosa.*") == "angry"
