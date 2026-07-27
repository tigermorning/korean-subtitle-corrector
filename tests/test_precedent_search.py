"""유사 판례 검색 테스트.

임베딩 모델(약 500MB)을 내려받지 않고 검증하기 위해 encode를 주입한다.
검증 대상은 모델 품질이 아니라 순위 계산·임계값·정확일치 우선 동작이다.
"""

import numpy as np
import pytest

from subtitle_corrector import precedent_search
from subtitle_corrector.precedent_search import (
    find_similar_precedents,
    format_similar_precedents,
)

FAKE_PRECEDENTS = [
    {
        "expression": "갈 만하다",
        "correct": True,
        "source": "보조용언 '만하다'는 띄어 쓰는 것이 원칙 -> 띄어 쓴 형태가 맞다",
        "verified": "2026-07-01",
    },
    {
        "expression": "볼만하다",
        "correct": True,
        "source": "'볼만하다'는 한 단어로 등재 -> 붙여 쓴 형태도 맞다",
        "verified": "2026-07-02",
    },
    {
        "expression": "김치찌개",
        "correct": True,
        "source": "합성어로 등재 -> 붙여 쓴다",
        "verified": "2026-07-03",
    },
]

# 표현별 고정 벡터. 첫 두 개(보조용언 띄어쓰기)는 서로 가깝고, 김치찌개는 멀다.
FAKE_VECTORS = {
    "갈 만하다": [1.0, 0.0, 0.0],
    "볼만하다": [0.9, 0.44, 0.0],
    "김치찌개": [0.0, 0.0, 1.0],
    "설 만하다": [0.99, 0.14, 0.0],
}


def fake_encode(texts):
    vectors = np.array([FAKE_VECTORS[text] for text in texts], dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


@pytest.fixture(autouse=True)
def fake_corpus(monkeypatch):
    monkeypatch.setattr(precedent_search, "PRECEDENTS", FAKE_PRECEDENTS)
    # 캐시가 다른 테스트의 벡터를 물고 있지 않도록 초기화한다.
    monkeypatch.setattr(precedent_search, "_cached_vectors", None)
    monkeypatch.setattr(precedent_search, "_cached_expressions", [])


def test_비슷한_판례가_유사도_순으로_나온다():
    matches = find_similar_precedents("설 만하다", encode=fake_encode)

    assert [entry["expression"] for entry in matches] == ["갈 만하다", "볼만하다"]
    assert matches[0]["similarity"] > matches[1]["similarity"]
    # 근거 원문이 그대로 실려야 감수자가 유사도가 아니라 규범 근거로 판단할 수 있다.
    assert "보조용언" in matches[0]["source"]
    assert matches[0]["verified"] == "2026-07-01"


def test_무관한_판례는_임계값에서_걸러진다():
    matches = find_similar_precedents("설 만하다", encode=fake_encode)

    assert "김치찌개" not in [entry["expression"] for entry in matches]


def test_임계값을_낮추면_먼_판례도_포함된다():
    matches = find_similar_precedents("설 만하다", min_similarity=-1.0, encode=fake_encode)

    assert [entry["expression"] for entry in matches] == ["갈 만하다", "볼만하다", "김치찌개"]


def test_top_n으로_개수를_제한한다():
    matches = find_similar_precedents("설 만하다", top_n=1, encode=fake_encode)

    assert len(matches) == 1


def test_정확일치_판례가_있으면_유사검색을_하지_않는다():
    """check_precedent()가 확정 답을 주는 경우에는 유사도가 끼어들 자리가 없다."""
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(
        precedent_search, "check_precedent", lambda expression: True
    )
    try:
        assert find_similar_precedents("갈 만하다", encode=fake_encode) == []
    finally:
        monkeypatched.undo()


def test_판례가_비어_있으면_빈_목록():
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(precedent_search, "PRECEDENTS", [])
    try:
        assert find_similar_precedents("설 만하다", encode=fake_encode) == []
    finally:
        monkeypatched.undo()


def test_출력에_판정_아님이_명시된다():
    matches = find_similar_precedents("설 만하다", encode=fake_encode)
    text = format_similar_precedents("설 만하다", matches)

    assert "규범 근거가 아니다" in text
    assert "사람이 직접 판단" in text
    assert "보조용언" in text


def test_결과가_없으면_없다고_알린다():
    assert "없음" in format_similar_precedents("설 만하다", [])


def test_모델_없으면_명확한_예외():
    """설치 안 된 환경에서 조용히 실패하지 않고 이유를 알려야 한다."""
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(precedent_search, "_model", None)
    monkeypatched.setitem(__import__("sys").modules, "sentence_transformers", None)
    try:
        with pytest.raises(precedent_search.PrecedentSearchUnavailable):
            precedent_search._load_model()
    finally:
        monkeypatched.undo()
