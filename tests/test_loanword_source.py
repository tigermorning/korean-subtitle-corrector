"""원어(로마자)로 국립국어원 확정 표기를 찾는 기능(§61).

외래어 음차의 정답은 **원어가 무엇이냐**로 갈린다 — '러스'는 원어가 Ruth면 '루스',
Russ면 '러스'가 맞다(§57, 7강 123번의 실제 사고). 번역가가 외래어 표기법 세칙을
직접 읽지 않고도 확정 근거로 판단할 수 있게, 원어를 받아 kornorms 용례를 돌려준다.

등급 판정(확정/일치/참고)이 이 기능의 핵심이다 — '참고'는 비슷한 원어일 뿐 정답
근거가 아니므로 화면이 반영 버튼을 주지 않는다. 다른 테스트와 마찬가지로 실시간
API를 호출한다.
"""
from fastapi.testclient import TestClient

from subtitle_corrector.api import app
from subtitle_corrector.dictionary import lookup_by_source

client = TestClient(app)


def test_exact_source_is_confirmed():
    rows = lookup_by_source("Snow")
    assert rows and rows[0]["match"] == "확정"
    assert rows[0]["korean"] == "스노"


def test_name_piece_matches_inside_full_name_entry():
    """인명 용례의 원어는 'Ruth, Babe'처럼 성·이름을 함께 담는다 — 완전 일치로는
    0건이라 조각 일치가 필요하다. 그 항목이 바로 '러스'를 '루스'로 바꾸려 했던
    근거였다."""
    rows = lookup_by_source("Ruth", token="러스")
    assert rows
    assert any(r["match"] == "일치" and r["korean"] == "루스" for r in rows)
    ruth_babe = next(r for r in rows if r["source"] == "Ruth, Babe")
    assert "러스(X)" in ruth_babe["wrong_marks"]


def test_unregistered_source_yields_no_confirmed_evidence():
    """원어가 Russ면 등재된 용례가 없다 — '참고'만 나오고 확정 근거는 없다.
    이 경우 화면은 반영 버튼을 주지 않고 사람이 발음으로 판단한다."""
    rows = lookup_by_source("Russ")
    assert all(r["match"] == "참고" for r in rows)


def test_full_name_entry_is_narrowed_to_the_token_segment():
    """한글 표기가 전체 이름이면 토막에 대응하는 조각으로 좁힌다 — 그대로 넣으면
    문장에 이름 전체가 삽입된다(`_closest_segment`와 같은 안전장치)."""
    rows = lookup_by_source("Rutherford", token="루더퍼드")
    entry = next(r for r in rows if r["korean"].startswith("러더퍼드, "))
    assert entry["segment"] == "러더퍼드"


def test_api_contract():
    res = client.get("/api/loanword-source", params={"source": "Snow", "token": "스노우"})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "Snow" and body["token"] == "스노우"
    assert body["confirmed"] is True
    first = body["candidates"][0]
    assert set(first) == {"source", "korean", "segment", "category", "wrong_marks", "match"}


def test_api_rejects_empty_source():
    assert client.get("/api/loanword-source", params={"source": "  "}).status_code == 400


def test_segment_follows_the_position_of_the_source_piece():
    """원어와 한글은 같은 순서로 나열된다 — `Dreifuss, Ruth` / `드라이푸스, 루트`에서
    `Ruth`는 둘째이므로 `루트`다. 표기 유사도로 고르면 `러스`와 가장 비슷한 `드라이푸스`
    (성)가 뽑혀 문장에 엉뚱한 이름이 들어간다(2026-08-04 로컬 서버 확인)."""
    rows = lookup_by_source("Ruth", token="러스")
    dreifuss = next(r for r in rows if r["source"] == "Dreifuss, Ruth")
    assert dreifuss["segment"] == "루트"
    # 조각이 하나뿐인 항목은 그대로다.
    babe = next(r for r in rows if r["source"] == "Ruth, Babe")
    assert babe["segment"] == "루스"

def test_segment_handles_reversed_western_name_order():
    """쉼표 없는 원어(`Ruth Kelly`)는 한글(`켈리, 루스`)과 순서가 반대다 — 자리로
    맞추기 전에 `성, 이름` 순으로 돌려놓아야 한다.

    돌려놓지 않으면 `Ruth`가 첫째라는 이유로 `켈리`가 답이 되고, 자막의 `러스`를
    그 제안으로 반영하면 **다른 사람 이름**이 대사에 박힌다(2026-08-05 실사용 감수).
    """
    rows = lookup_by_source("Ruth", token="러스")
    by_source = {r["source"].strip(): r for r in rows}
    assert by_source["Ruth Kelly"]["segment"] == "루스"
    assert by_source["Babe Ruth"]["segment"] == "루스"
    # 이름이 여러 낱말이면 덩어리 안에서 한 번 더 자리를 맞춘다('루스 마리아' -> '루스').
    assert by_source["Ruth Maria Kelly"]["segment"] == "루스"
    # 괄호 별칭이 붙은 항목도 낱말 하나로 좁혀진다.
    assert by_source["Benedict, Ruth (Fulton)"]["segment"] == "루스"


def test_entry_marking_the_token_as_wrong_comes_first():
    """자막에 쓰인 표기를 오표기로 명시한 용례가 가장 강한 근거다 — 같은 등급
    안에서 맨 앞에 놓는다. `Ruth`로 조회하면 23건이 오는데 `러스(X)`를 명시한
    `Ruth, Babe`가 셋째에 묻혀 있었다(2026-08-05 실사용 감수)."""
    rows = lookup_by_source("Ruth", token="러스")
    assert rows[0]["source"] == "Ruth, Babe"
    assert "러스(X)" in rows[0]["wrong_marks"]
