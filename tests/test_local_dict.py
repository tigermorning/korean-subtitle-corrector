"""내려받은 사전 색인 로컬 조회(local_dict) — 작은 가짜 데이터로 색인을 만들어 본다(실제 데이터 불필요)."""
import importlib.util
import json
from pathlib import Path

import pytest

from subtitle_corrector.dictionary import clients, local_dict

ROOT = Path(__file__).resolve().parent.parent


def _builder():
    spec = importlib.util.spec_from_file_location("build_dict_index", ROOT / "tools" / "build_dict_index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _st(code, word, definition, pos="명사", origin=None):
    info = {"word": word, "pos_info": [{"pos": pos, "comm_pattern_info": [{"sense_info": [
        {"definition": definition, "type": "일반어", "example_info": [{"example": "용례"}]}]}]}]}
    if origin:
        info["original_language_info"] = [{"original_language": origin, "language_type": "한자"}]
    return {"target_code": code, "word_info": info}


def _od(code, group, word, definition, order=1, typ="일반어", pos="명사", cat=None):
    sense = {"definition": definition, "type": typ, "pos": pos, "sense_no": f"{order:03d}"}
    if cat:
        sense["cat_info"] = [{"cat": cat}]
    return {"wordinfo": {"word": word}, "group_code": group, "group_order": order,
            "target_code": code, "senseinfo": sense}


@pytest.fixture
def index(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "stdict").mkdir(parents=True)
    (data / "opendict").mkdir()
    stdict = [
        _st(1, "가상02", "‘가상하다02’의 어근.", pos="품사 없음", origin="嘉尙"),
        _st(2, "가상01", "시렁 또는 선반의 위.", origin="架上"),
        _st(3, "생명^보험", "제12조에 따른 보험."),
        _st(4, "끝02", "→ 끗02."),
    ]
    opendict = [_od(100, 10, "보험", "보증.", 1), _od(101, 10, "보험", "제도 <FL>.", 2, cat="경제")]
    # 앞부분 일치 10건을 넘게 둔다(가나다순으로 앞 9건만 들어가야 한다).
    for i, tail in enumerate("가나다라마바사아자차"):
        opendict.append(_od(200 + i, 20 + i, f"보험^{tail}", f"뜻 {tail}", pos="품사 없음"))
    opendict += [_od(300, 40, "신청", "뜻1"), _od(301, 41, "신청", "뜻2")]  # 완전 일치 그룹 둘
    opendict += [_od(400, 50, "외톨", "뜻"), _od(401, 51, "외톨-이", "뜻")]  # 앞부분 일치가 모자람
    (data / "stdict" / "a.json").write_text(json.dumps({"channel": {"item": stdict}}, ensure_ascii=False), "utf-8")
    (data / "opendict" / "a.json").write_text(json.dumps({"channel": {"item": opendict}}, ensure_ascii=False), "utf-8")
    _builder().build(str(data), str(data / "index" / "dict_index.sqlite3"))
    monkeypatch.setenv("DICT_LOCAL_DIR", str(data))
    yield data
    if local_dict._CONN is not None:
        local_dict._CONN.close()
    local_dict._CONN = local_dict._CONN_PATH = None
    clients._local_stdict.cache_clear()
    clients._local_opendict.cache_clear()


def test_headword_key_strips_marks_and_homonym_numbers():
    assert local_dict.headword_key("각본02") == "각본"
    assert local_dict.headword_key("과학-기술001") == "과학기술"
    assert local_dict.headword_key("생명^보험") == "생명보험"
    assert local_dict.headword_key("아내 바보") == "아내 바보"


def test_off_without_setting(monkeypatch):
    monkeypatch.setenv("DICT_LOCAL_DIR", "")
    assert local_dict.stdict_search("가상") is None
    assert local_dict.opendict_search("보험") is None


def test_stdict_shape_order_and_definition_cleanup(index):
    channel = local_dict.stdict_search("가상")["channel"]
    assert channel["total"] == 2
    first, second = channel["item"]
    assert (first["word"], first["sup_no"], first["origin"]) == ("가상", "1", "架上")
    assert (second["sup_no"], second["pos"], second["sense"]["definition"]) == ("2", "품사 없음", "‘가상하다’의 어근.")
    assert second["target_code"] == "1" and second["sense"]["type"] == "일반어"
    assert local_dict.stdict_search("끝")["channel"]["item"][0]["sense"]["definition"] == "→ 끗."


def test_stdict_joined_query_matches_caret_headword_but_keeps_body_numbers(index):
    item = local_dict.stdict_search("생명보험")["channel"]["item"][0]
    assert item["word"] == "생명^보험" and item["sup_no"] == "0"
    assert item["sense"]["definition"] == "제12조에 따른 보험."


def test_missing_or_spaced_query_goes_to_api(index):
    assert local_dict.stdict_search("없는말") is None
    assert local_dict.stdict_search("생명 보험") is None
    assert local_dict.opendict_search("없는말") is None


def test_opendict_exact_then_prefix_page(index):
    items = local_dict.opendict_search("보험")["channel"]["item"]
    assert [it["word"] for it in items] == ["보험"] + [f"보험^{t}" for t in "가나다라마바사아자"]
    senses = items[0]["sense"]
    assert [s["target_code"] for s in senses] == ["100", "101"]
    assert senses[0]["type"] == "" and senses[1]["cat"] == "경제"
    assert senses[1]["definition"] == "제도 &lt;FL&gt;."
    assert items[1]["sense"][0]["pos"] == ""


def test_opendict_defers_when_order_cannot_be_reproduced(index):
    assert local_dict.opendict_search("신청") is None  # 완전 일치 그룹 둘
    assert local_dict.opendict_search("외톨") is None  # 10건이 안 차 중간 포함 항목이 끼어들 수 있다


def test_clients_use_local_first_then_api(index, monkeypatch):
    calls = []
    monkeypatch.setattr(clients, "_fetch_stdict", lambda q: calls.append(q) or {"channel": {"total": 0, "item": []}})
    assert clients.search_stdict("가상")["channel"]["total"] == 2
    assert calls == []
    clients.search_stdict("없는말")
    assert calls == ["없는말"]
