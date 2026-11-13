"""로서/로써 검사 — 가짜 의미 범주 색인으로 시험한다(예문은 새로 지은 문장)."""
import json

import pytest

from subtitle_corrector.engine import rosseo
from subtitle_corrector.engine.pipeline import _correct_line

FAKE = {
    "반장": ["교육 > 교수 학습 주체"],
    "선배": ["사회 생활 > 인간관계"],
    "주인": ["사회 생활 > 인간관계", "경제 생활 > 경제 행위"],
    "망치": ["삶 > 도구"],
    "모임": ["사회 생활 > 단체"],
}


@pytest.fixture
def fake_index(tmp_path, monkeypatch):
    (tmp_path / "index").mkdir()
    (tmp_path / "index" / "krdict_semcat.json").write_text(json.dumps(FAKE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DICT_LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr(rosseo, "_CACHE", None)


def test_all_person_rosseo_is_corrected(fake_index):
    fixed, fixes = rosseo.correct_rosseo("나는 반장으로써 손을 들었다")
    assert fixed == "나는 반장으로서 손을 들었다"
    assert fixes == ["반장으로써 -> 반장으로서"]
    fixed, _ = rosseo.correct_rosseo("선배로써 한마디 할게")
    assert fixed == "선배로서 한마디 할게"


def test_pipeline_applies_and_logs_evidence(fake_index):
    fixed, _, applied = _correct_line(0, "나는 반장으로써 손을 들었다", "general", "principle")
    assert "반장으로서" in fixed
    messages = [a.message for a in applied]
    assert "반장으로써 -> 반장으로서" in messages
    assert any("지위나 신분 또는 자격" in m for m in messages)


def test_mixed_categories_flag_only(fake_index):
    text = "주인으로써 책임을 지겠다"
    assert rosseo.correct_rosseo(text) == (text, [])
    flag = rosseo.check_rosseo(3, text)
    assert flag is not None and flag.suggested_fix == "주인으로서 책임을 지겠다"


@pytest.mark.parametrize("text", [
    "망치로써 못을 박았다",      # 비사람 + 로써: 맞음
    "망치로서 못을 박았다",      # 비사람 + 로서: 표시하지 않는다(사용자 결정)
    "모임으로서 의견을 냈다",    # 단체도 자격이 될 수 있다
    "반장으로서 손을 들었다",    # 이미 맞음
    "낯선말로써 적었다",          # 색인에 없음
])
def test_nothing_happens(fake_index, text):
    assert rosseo.correct_rosseo(text) == (text, [])
    assert rosseo.check_rosseo(0, text) is None


def test_disabled_without_index(monkeypatch):
    monkeypatch.setenv("DICT_LOCAL_DIR", "")
    monkeypatch.setattr(rosseo, "_CACHE", None)
    text = "나는 반장으로써 손을 들었다"
    assert rosseo.correct_rosseo(text) == (text, [])
    assert rosseo.check_rosseo(0, text) is None
