"""실사용 감수 수정(A·B·C)의 정답표 회귀 테스트.

실제 자막 텍스트에서 발견된 과교정/오탐 사례를 고정한다. 각 케이스의 근거는
docs/HANDOFF_realusage_review.md 및 docs/IMPLEMENTATION_LOG.md 참고. 기존
테스트들과 마찬가지로 실시간 사전 API를 호출한다.
"""
from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import SubtitleEntry


def _run(text: str):
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text, speaker=None)
    corrected, flags, _log = correct_entries([entry], None, None)
    return corrected[0].text, flags


# --- A: 합성어 자동병합 과교정 ---

def test_a1_adnominal_phrase_not_merged_or_flagged():
    # '큰 애들' = 크다의 관형형 '큰' + '애들' = 구. 준말 '큰애'로 붙이지 않고 플래그도 안 함.
    out, flags = _run("그런 케어를 받지 못하고 큰 애들은")
    assert out == "그런 케어를 받지 못하고 큰 애들은"
    assert flags == []


def test_a2_figurative_compound_flagged_not_merged():
    # 턱밑=비유어. 자동 병합하지 않고 확인 플래그.
    out, flags = _run("턱 밑이 간지럽다")
    assert out == "턱 밑이 간지럽다"
    assert any(f.suggested_fix == "턱밑이 간지럽다" for f in flags)


def test_a3_plain_compound_still_merged():
    out, _flags = _run("노천 카페에서 만나자")
    assert out == "노천카페에서 만나자"


# --- B: 모호 자동교체 -> 플래그 ---

def test_b1_colloquial_loanword_flagged_not_auto():
    out, flags = _run("빤스를 입었다")
    assert out == "빤스를 입었다"
    assert any("빤쓰" in f.reason and "팬츠" in f.reason for f in flags)


def test_b1_regression_plain_loanword_still_auto():
    out, _flags = _run("초코렛을 좋아해")
    assert out == "초콜릿을 좋아해"


def test_b2_line_final_na_flagged_not_attached():
    out, flags = _run("영화 보는 거보다 백 배 나")
    assert out == "영화 보는 거보다 백 배 나"
    assert any(f.suggested_fix == "영화 보는 거보다 백 배나" for f in flags)


# --- C: 유효 표제어 오탐 억제 ---

def test_c1_verb_lemma_fragment_not_flagged_foreign():
    # '얄짤없다' 표제어. '얄짤' 조각을 외국어로 오탐하지 않는다.
    out, flags = _run("얄짤없어")
    assert out == "얄짤없어"
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_c2_dialect_headword_not_split():
    # '껄쩍지근하다' 방언 표제어. '껄쩍 지근'으로 분리 제안하지 않는다.
    out, flags = _run("평생을 껄쩍지근하게 살았다")
    assert out == "평생을 껄쩍지근하게 살았다"
    assert not any("껄쩍 지근" in (f.suggested_fix or "") for f in flags)


def test_c3_reduplication_not_flagged_foreign():
    # '건숭'(방언 표제어) 첩어. 외국어로 오탐하지 않는다.
    _out, flags = _run("돌아 버리게 건숭건숭이야")
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_c4_onomatopoeia_not_flagged_foreign():
    out, flags = _run("콸콸콸 콸콸콸")
    assert out == "콸콸콸 콸콸콸"
    assert not any("사전에 없는 단어" in f.reason for f in flags)


# --- D: 긴 줄 자동교정 로그는 변경 부분만 축약 표시 ---

def _applied_log(text: str):
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text, speaker=None)
    _corrected, _flags, applied = correct_entries([entry], None, None)
    return applied


def test_d_long_line_log_localized():
    # 긴 대사에서 한 곳만 바뀌면 전체 라인을 다시 적지 않고 변경 부분만 '…'로 축약.
    long_text = "상용화 직전 마지막 테스트 단계래 땡큐지 갔어 뭔가 착오가있었던 것 같대"
    applied = _applied_log(long_text)
    assert applied, "띄어쓰기 자동 교정이 있어야 함"
    joined = " ".join(applied)
    assert "…" in joined
    assert long_text not in joined  # 원문 전체를 그대로 다시 싣지 않는다


def test_d_short_line_log_full():
    # 짧은 줄은 전체를 보여주는 편이 더 명확하므로 축약하지 않는다.
    applied = _applied_log("오늘은날씨가좋네요")
    assert any("오늘은날씨가좋네요 -> 오늘은 날씨가 좋네요" in a for a in applied)
