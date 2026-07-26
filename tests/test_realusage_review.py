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


# --- E: 사용목적 모드(자막 vs 일반 글) — 문장 부호 ---

def _run_mode_full(text: str, doc_type: str):
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text, speaker=None)
    return correct_entries([entry], None, None, doc_type)


def test_e_subtitle_removes_final_period():
    # 줄 끝 문장 종결 마침표는 자막 관례상 자동으로 제거한다(플래그 아님).
    corrected, flags, _log = _run_mode_full("안녕하세요.", "subtitle")
    assert corrected[0].text == "안녕하세요"
    assert not any(f.suggested_fix and f.suggested_fix.endswith(".") for f in flags)


def test_e_subtitle_internal_period_to_comma_flag():
    # 한 줄에 두 문장: 끝 마침표는 자동 제거, 문장 사이 마침표는 쉼표로 바꾸자고 플래그.
    corrected, flags, _log = _run_mode_full("보여 주세요. 궁금해요.", "subtitle")
    assert corrected[0].text == "보여 주세요. 궁금해요"  # 끝 마침표만 제거
    assert any(f.suggested_fix == "보여 주세요, 궁금해요" for f in flags)


def test_e_prose_keeps_periods():
    corrected, flags, _log = _run_mode_full("보여 주세요. 궁금해요.", "prose")
    assert corrected[0].text == "보여 주세요. 궁금해요."  # 일반 글은 구두점 유지
    assert not any("쉼표" in f.reason for f in flags)


def test_e_subtitle_bracket_gets_one_space():
    # 자막 관례: '[...]' 뒤에는 항상 한 칸을 띄운다(자동 교정).
    c1, _f, _l = _run_mode_full("[민수]안녕하세요", "subtitle")
    assert c1[0].text == "[민수] 안녕하세요"
    c2, _f2, _l2 = _run_mode_full("[민수]  안녕하세요", "subtitle")
    assert c2[0].text == "[민수] 안녕하세요"
    # 효과음처럼 브래킷만 있는 줄은 건드리지 않는다.
    c3, _f3, _l3 = _run_mode_full("[문 여는 소리]", "subtitle")
    assert c3[0].text == "[문 여는 소리]"


def test_e_prose_bracket_untouched():
    c, _f, _l = _run_mode_full("[민수]안녕", "prose")
    assert c[0].text == "[민수]안녕"


def test_e_default_mode_is_subtitle():
    # doc_type 인자를 생략하면 자막 모드 — 끝 마침표를 자동 제거한다.
    corrected, _flags, _log = correct_entries(
        [SubtitleEntry(index=1, start="0", end="1", text="맞아요.", speaker=None)]
    )
    assert corrected[0].text == "맞아요"


def test_e_subtitle_ignores_decimal_and_ellipsis():
    # 소수점(3.14)·말줄임표(...)는 문장 종결 마침표가 아니므로 건드리지 않는다.
    corrected, _f, _l = _run_mode_full("원주율은 3.14다", "subtitle")
    assert corrected[0].text == "원주율은 3.14다"
    corrected2, _f2, _l2 = _run_mode_full("글쎄...", "subtitle")
    assert corrected2[0].text == "글쎄..."


# --- 효과음 브래킷을 화자로 오인하지 않기 ---

def test_sound_effect_brackets_not_speakers(tmp_path):
    from subtitle_corrector.parsers import parse_srt

    srt = (
        "1\n00:00:01,000 --> 00:00:03,000\n[민수] 안녕하세요\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n[문 여는 소리]\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\n[웃음]\n\n"
        "4\n00:00:10,000 --> 00:00:12,000\n[영희] 어서 와\n"
    )
    path = tmp_path / "sfx.srt"
    path.write_text(srt, encoding="utf-8")
    entries = parse_srt(path)
    speakers = {e.speaker for e in entries if e.speaker}
    # 브래킷만 있는 효과음 줄([문 여는 소리], [웃음])은 화자가 아니다.
    assert speakers == {"민수", "영희"}


def test_native_compound_not_flagged_foreign():
    # '김치찌갯집' = '김치'+'찌갯집'(둘 다 표제어) 고유어 합성어 — kiwi가 문맥에
    # 따라 통짜 NNG로 태깅해도 외래어 음차로 오탐하지 않는다.
    entry = SubtitleEntry(index=1, start="0", end="1", text="여기 김치찌갯집이 유명해", speaker=None)
    _c, flags, _l = correct_entries([entry])
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_headword_derived_word_not_split_by_spacing():
    # '샘나'(샘나다)는 kiwi.space가 '샘 나'로 쪼개도 사전 표제어라 되돌린다.
    entry = SubtitleEntry(index=1, start="0", end="1", text="샘나 미쳐 버려", speaker=None)
    corrected, _flags, _l = correct_entries([entry])
    assert corrected[0].text == "샘나 미쳐 버려"


def test_no_dialect_auto_recommendation_for_unassigned_speaker():
    # 사투리는 작업자가 직접 지정한다 — dialect_map에 없는 화자에게는 사투리
    # 자동 감지 '추천' 플래그를 띄우지 않는다(지문/효과음 오탐 방지).
    entry = SubtitleEntry(index=1, start="0", end="1", text="아이고 마 그래 가꼬", speaker="늘어지며")
    _corrected, flags, _log = correct_entries([entry])  # dialect_map 없음
    assert not any("사투리" in f.reason for f in flags)


def test_common_dialect_endings_to_standard():
    # 노인 말투 공통 어미 사투리(믄→면, 겄→겠)를 to_standard 변환에서 처리한다.
    from subtitle_corrector.dictionary import convert_dialect
    assert convert_dialect("먹으믄", "전라도", "to_standard") == "먹으면"
    assert convert_dialect("맛나겄냐", "전라도", "to_standard") == "맛나겠냐"
    assert convert_dialect("방이라믄서", "충청도", "to_standard") == "방이라면서"
    # 역방향(표준어→사투리)에는 넣지 않아 '화면'의 '면'을 건드리지 않는다.
    assert convert_dialect("화면", "전라도", "to_dialect") == "화면"
