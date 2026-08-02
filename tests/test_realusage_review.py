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


def test_e_subtitle_internal_period_becomes_comma():
    # 한 줄에 두 문장: 문장 사이 마침표는 쉼표로 자동 대체, 끝 마침표는 자동 제거
    # (2026-08-02 사용자 지정으로 플래그에서 자동 교정으로 승격).
    corrected, flags, _log = _run_mode_full("보여 주세요. 궁금해요.", "subtitle")
    assert corrected[0].text == "보여 주세요, 궁금해요"
    assert not any("쉼표" in f.reason for f in flags)


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


def test_adnominal_noun_verb_split():
    # 관형사/관형형 + '명사+하다'는 명사와 '하'를 띄운다(관형어는 명사를 꾸미므로).
    def out(t):
        e = SubtitleEntry(index=1, start="0", end="1", text=t, speaker=None)
        return correct_entries([e])[0][0].text
    assert out("뭔 생각하냐?") == "뭔 생각 하냐?"
    # '만날'은 문맥이 있어야 관형형('만나+ㄹ')으로 태깅된다(단독이면 부사 '매일'로 봄).
    assert out("수더분한 여자 만날 생각해") == "수더분한 여자 만날 생각 해"
    assert out("이런 생각하다") == "이런 생각 하다"
    # 제외: 부사 수식, 다른 명사 수식, 이미 띄어진 경우, 관형어 없음
    assert out("잘 생각한다") == "잘 생각한다"
    assert out("그 사람 사랑한다") == "그 사람 사랑한다"
    assert out("공부한다") == "공부한다"


def test_interjection_vocative_comma():
    # 감탄사·호격어는 쉼표로 구분(문맥 무관 규정).
    def out(t):
        e = SubtitleEntry(index=1, start="0", end="1", text=t, speaker=None)
        return correct_entries([e])[0][0].text
    assert out("아이고 어떻기는") == "아이고, 어떻기는"   # 시작 감탄사
    assert out("네가 싫다면 뭐") == "네가 싫다면, 뭐"     # 끝 감탄사
    assert out("먹어 준희야") == "먹어, 준희야"          # 끝 호격
    # 제외: IC+IC, 이미 쉼표, 대명사 뭐, 감탄사 단독
    assert out("거 참") == "거 참"
    assert out("먹어, 준희야") == "먹어, 준희야"
    assert out("뭐 하냐") == "뭐 하냐"


def test_e_subtitle_removes_final_period_every_line():
    # 여러 줄 자막: 각 행의 끝 마침표를 모두 자동 제거한다.
    corrected, flags, _log = _run_mode_full("안녕하세요.\n반갑습니다.", "subtitle")
    assert corrected[0].text == "안녕하세요\n반갑습니다"
    assert not any("쉼표" in f.reason for f in flags)
    # 행 중간 마침표는 쉼표로, 행 끝은 제거 — 2026-08-02부터 둘 다 자동이다.
    c2, _f2, _l2 = _run_mode_full("네. 그래.\n알겠어.", "subtitle")
    assert c2[0].text == "네, 그래\n알겠어"


# --- 2026-08-02 실사용 감수: 사전 표제어 오탐 3건 + 브래킷 연속 ---

def test_verb_stem_mistagged_as_noun_not_flagged_unknown():
    """'덖는'의 '덖'을 kiwi가 명사로 태깅해 미등록어로 플래그하던 오탐.

    명사 뒤에는 어미가 붙지 않는다 — 어미가 붙어 있으면 어간으로 보고
    '어간+다'(덖다, 사전 등재)를 확인해야 한다.
    """
    _out, flags = _run("[세윤] 스님, 이제 여기서 덖는 겁니까, 이렇게?")
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_headword_with_particle_not_split():
    """'짬짜면을'처럼 조사가 붙으면 표제어 조회가 실패해 '짬 짜면을'로 쪼개자고
    제안하던 오탐. 어절 끝 조사를 떼고 다시 확인한다."""
    out, flags = _run("짬짜면을 시켰다")
    assert out == "짬짜면을 시켰다"
    assert not any("짬 짜면" in (f.suggested_fix or "") for f in flags)


def test_adjacent_brackets_keep_no_space():
    """'[♪ 음악][대수] 대사'처럼 표시가 연달아 오면 사이를 띄우지 않는다.
    한 칸을 띄우는 것은 표시와 대사 사이지 표시끼리가 아니다."""
    from subtitle_corrector.parsers import SubtitleEntry as _E
    corrected, _f, _l = correct_entries(
        [_E(index=1, start="0", end="1", text="[♪ 박진감 넘치는 음악][대수] 가자")]
    )
    assert corrected[0].text == "[♪ 박진감 넘치는 음악][대수] 가자"


def test_headword_interjection_not_split_by_comma():
    """'에라이!'(감탄사 표제어)를 kiwi가 '에라'+'이'로 쪼갠 것을 믿고 쉼표를
    넣어 '에라,이!'로 만들던 자동 교정 버그(2026-08-02 실사용 보고).

    사용자는 이것을 "느낌표가 한 칸 띄워졌다"로 보고했는데, 실제로는 느낌표가
    아니라 그 앞 글자가 떨어져 나온 것이었다.
    """
    assert _run("에라이!")[0] == "에라이!"
    assert _run("아싸!")[0] == "아싸!"
    assert _run("에라이! 그만해")[0] == "에라이! 그만해"


def test_unresolvable_split_not_suggested():
    """'한짓골'(사극 지명, 사전 미등재)을 '한 짓골'로 쪼개자던 제안.

    쪼갠 결과인 '짓골'도 사전에 없다 — 어느 쪽으로도 사전 근거가 없는 분리라
    제안하지 않는다. 붙어 있던 원문을 근거 없이 갈라놓는 것보다 그대로 두는
    편이 낫다.
    """
    out, flags = _run("한짓골에 갔다")
    assert out == "한짓골에 갔다"
    assert not any("한 짓골" in (f.suggested_fix or "") for f in flags)


def test_dictionary_backed_splits_still_suggested():
    """근거 있는 분리 제안까지 막으면 안 된다(위 규칙의 회귀 가드).

    '안 됩니다'는 어간과 어미가 받침을 공유해 표면형으로 자를 수 없는 활용이라,
    첫 시도에서 이 제안이 함께 죽었다.
    """
    _out, flags = _run("그러면 안됩니다")
    assert any(f.suggested_fix == "그러면 안 됩니다" for f in flags)
    _out2, flags2 = _run("이것도 먹을수있다")
    assert any(f.suggested_fix == "이것도 먹을 수 있다" for f in flags2)


def test_merged_particle_not_auto_split():
    """'입구에서 봐'를 '입구에 서 봐'로 자동 교정하던 과교정(2026-08-02 보고).

    kiwi 1순위 분석이 '에'(조사)+'서'(서다)였지만, 2순위 후보는 '에서'(조사
    하나)다. 둘 다 문법적으로 가능한 문장이라 문맥이 정할 일이지 자동으로 고를
    일이 아니다. 자동 교정이라 사람이 못 보고 지나칠 위험이 컸다.
    """
    out, _flags = _run("개나리길 입구에서 봐")
    assert out == "개나리길 입구에서 봐"
    assert _run("학교에서 만나")[0] == "학교에서 만나"
    assert _run("너한테서 들었어")[0] == "너한테서 들었어"


def test_particle_attachment_still_auto_corrected():
    """조사·어미 결합 자동 교정 자체는 살아 있어야 한다(위 규칙의 회귀 가드)."""
    assert _run("오늘은날씨가좋네요")[0] == "오늘은 날씨가 좋네요"


def test_particle_before_auxiliary_not_joined():
    """'보기만 해도'를 '보기만해도'로 붙이자던 제안(2026-08-02 실사용 보고).

    한글 맞춤법 제47항 단서: 앞말에 조사가 붙으면 그 뒤의 보조 용언은 띄어 쓴다.
    '만'이 조사이므로 붙임 허용 대상이 아니다 — 사전 조회 이전에 규정으로 막는다.
    """
    out, flags = _run("보기만 해도 좋다")
    assert out == "보기만 해도 좋다"
    assert not any("보기만해도" in (f.suggested_fix or "") for f in flags)


def test_component_of_standard_headword_not_unknown():
    """'빌리지'는 단독 표제어가 없지만 '빌리지 뱅가드'·'스마트 빌리지' 등
    표준 표제어의 구성 요소다. 비표준 안내가 붙은 표제어(스노우 체인)는 근거로
    인정하지 않으므로 '스노우' 교정은 그대로 유지된다."""
    _out, flags = _run("그 빌리지에 살아")
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_field_limited_former_term_not_flagged():
    """'원통'의 옛 용어 안내는 우리말샘에서 수학 분야 뜻에만 달려 있고 일상적인
    뜻('분하고 억울함')과는 무관하다. 분야 표시가 없는 옛 용어(간질)는 계속 플래그한다."""
    _out, flags = _run("원통 모양이야")
    assert not any("전 용어" in f.reason for f in flags)
    _out2, flags2 = _run("간질 환자가 늘었다")
    assert any("전 용어" in f.reason for f in flags2)


def test_determiner_not_treated_as_interjection():
    """관형사 '그'를 감탄사로 보고 '그, 빌리지에'로 쉼표를 넣던 오교정."""
    assert _run("그 빌리지에 살아")[0] == "그 빌리지에 살아"
    assert _run("이 사람 누구야")[0] == "이 사람 누구야"
    assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"


def test_marker_content_not_merged():
    """SDH 효과음 '[탁 - 차 문]'의 '차 문'이 '차문'으로 병합되던 오탐.

    '차문'은 표제어이긴 하나 뜻이 借文(대작)·借問(물음)·조선 상소문뿐이라 자동차
    문과 무관하다. 자막 표시 안은 일반 문장 규칙의 대상이 아니므로 병합하지 않는다.
    """
    assert _run("[탁 - 차 문]")[0] == "[탁 - 차 문]"
    # 표시 밖에서는 정상 병합이 유지된다
    assert _run("노천 카페에서 만나자")[0] == "노천카페에서 만나자"


def test_historical_headword_is_not_join_evidence():
    """'미림이도 오고 했는데'를 '오고했는데'로 붙이자던 제안.

    근거였던 '오고하다'는 五考하다(역사: 벼슬아치 고과)와 제주 방언뿐이다. 사전에
    있다는 사실만으로는 현대 문장을 붙여 쓸 근거가 되지 않는다.
    """
    out, flags = _run("미림이도 오고 했는데 얼른 오라고 혀라")
    assert out == "미림이도 오고 했는데 얼른 오라고 혀라"
    assert not any("오고했는데" in (f.suggested_fix or "") for f in flags)
    # 정당한 붙임은 그대로 유지된다
    assert _run("선물 받았어")[0] == "선물받았어"
