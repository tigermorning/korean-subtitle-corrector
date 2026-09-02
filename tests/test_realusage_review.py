"""실사용 감수 수정(A·B·C)의 정답표 회귀 테스트.

실제 자막 텍스트에서 발견된 과교정/오탐지 사례를 고정한다. 각 케이스의 근거는
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


def test_a3_plain_compound_becomes_a_candidate():
    """2026-08-04부터 합성어 병합은 자동이 아니라 후보(확인 항목)다."""
    out, flags = _run("노천 카페에서 만나자")
    assert out == "노천 카페에서 만나자"
    assert any(f.suggested_fix == "노천카페에서 만나자" for f in flags)


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


# --- C: 유효 표제어 오탐지 억제 ---

def test_c1_verb_lemma_fragment_not_flagged_foreign():
    # '얄짤없다' 표제어. '얄짤' 조각을 외국어로 오탐지하지 않는다.
    out, flags = _run("얄짤없어")
    assert out == "얄짤없어"
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_c2_dialect_headword_not_split():
    # '껄쩍지근하다' 방언 표제어. '껄쩍 지근'으로 분리 제안하지 않는다.
    out, flags = _run("평생을 껄쩍지근하게 살았다")
    assert out == "평생을 껄쩍지근하게 살았다"
    assert not any("껄쩍 지근" in (f.suggested_fix or "") for f in flags)


def test_c3_reduplication_not_flagged_foreign():
    # '건숭'(방언 표제어) 첩어. 외국어로 오탐지하지 않는다.
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
    return [n.text() for n in applied]


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
    # 따라 통짜 NNG로 태깅해도 외래어 음차로 오탐지하지 않는다.
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
    # 자동 감지 '추천' 플래그를 띄우지 않는다(지문/효과음 오탐지 방지).
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


# --- 2026-08-02 실사용 감수: 사전 표제어 오탐지 3건 + 브래킷 연속 ---

def test_verb_stem_mistagged_as_noun_not_flagged_unknown():
    """'덖는'의 '덖'을 kiwi가 명사로 태깅해 미등록어로 플래그하던 오탐지.

    명사 뒤에는 어미가 붙지 않는다 — 어미가 붙어 있으면 어간으로 보고
    '어간+다'(덖다, 사전 등재)를 확인해야 한다.
    """
    _out, flags = _run("[세윤] 스님, 이제 여기서 덖는 겁니까, 이렇게?")
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_headword_with_particle_not_split():
    """'짬짜면을'처럼 조사가 붙으면 표제어 조회가 실패해 '짬 짜면을'로 쪼개자고
    제안하던 오탐지. 어절 끝 조사를 떼고 다시 확인한다."""
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


def test_particle_before_auxiliary_split_is_kept():
    """반대 방향 — 조사+보조용언을 붙여 쓴 줄에 kiwi가 공백을 넣자고 하는 경우.

    제47항 단서상 이 공백은 정답이므로 되돌리지 않는다. 이 분기는 2026-08-02까지
    다른 함수의 변수 이름을 잘못 옮겨 적어 NameError로 터졌다 — 이런 줄 하나가
    파일 전체 교정을 무너뜨렸다. 크래시 회귀 고정.
    """
    for text, expected in (
        ("보고는싶다", "보고는 싶다"),
        ("알고는있다", "알고는 있다"),
        ("먹고는싶다", None),  # _protect_unresolvable_splits가 '먹고는'을 사전으로 확인하지 못해 보류
    ):
        out, flags = _run(text)  # 크래시 회귀 고정 — 여기서 예외가 나면 안 된다
        # 띄어쓰기는 자동 적용하지 않고 플래그로만 제안한다.
        assert out == text
        suggestions = [f.suggested_fix for f in flags if f.suggested_fix]
        if expected is None:
            assert text not in suggestions
        else:
            assert expected in suggestions, (text, suggestions)


def test_component_of_standard_headword_not_unknown():
    """'빌리지'는 단독 표제어가 없지만 '빌리지 뱅가드'·'스마트 빌리지' 등
    표준 표제어의 구성 요소다. 비표준 안내가 붙은 표제어(스노우 체인)는 근거로
    인정하지 않으므로 '스노우' 교정은 그대로 유지된다."""
    _out, flags = _run("그 빌리지에 살아")
    assert not any("사전에 없는 단어" in f.reason for f in flags)


def test_field_limited_former_term_not_flagged():
    """'원통'의 옛 용어 안내는 우리말샘에서 수학 분야 뜻에만 달려 있고 일상적인
    뜻('분하고 억울함')과는 무관하다.

    2026-08-05(§73)부터는 분야 표시가 없는 옛 용어도 같은 원칙을 따른다 — 문서에
    그 전문 분야 뜻으로 읽을 근거가 없으면 묻지 않는다. **`간질 환자가 늘었다`처럼
    사람이 보기에 분명한 병명 문맥도 놓친다**(`환자`는 우리말샘 분야가 경제·역사이고
    `뇌전증` 뜻풀이에도 나오지 않는다). 근거가 없을 때 묻지 않는 쪽을 택한 대가이며,
    `docs/KNOWN_LIMITATIONS.md`에 적어 두었다."""
    _out, flags = _run("원통 모양이야")
    assert not any("전 용어" in f.reason for f in flags)
    _out2, flags2 = _run("간질 환자가 늘었다")
    assert not any("전 용어" in f.reason for f in flags2)
    # 사전이 근거를 주는 문맥에서는 그대로 묻는다.
    _out3, flags3 = _run("간질 발작을 일으켰다")
    assert any("전 용어" in f.reason for f in flags3)
    # '원통'은 수학 분야 낱말과 함께 쓰여도 여전히 묻지 않는다 — 분야가 달린
    # 옛 용어는 의도적으로 보수적으로 억제한다(2026-09-02, §90·BACKLOG 34번).
    # `sense_fields()`가 표제어의 모든 뜻을 OR로 합쳐서, 문맥 낱말('감독'·'허가'
    # 같은 흔한 말의 무관한 다른 뜻) 쪽에서도 같은 오염이 재발했기 때문이다 —
    # 자세한 경위는 `correct_former_terms()`의 해당 분기 주석 참고.
    _out4, flags4 = _run("원통의 반지름을 구해 보자")
    assert not any("전 용어" in f.reason for f in flags4)


def test_determiner_not_treated_as_interjection():
    """관형사 '그'를 감탄사로 보고 '그, 빌리지에'로 쉼표를 넣던 오교정."""
    assert _run("그 빌리지에 살아")[0] == "그 빌리지에 살아"
    assert _run("이 사람 누구야")[0] == "이 사람 누구야"
    assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"


def test_marker_content_not_merged():
    """SDH 효과음 '[탁 - 차 문]'의 '차 문'이 '차문'으로 병합되던 오탐지.

    '차문'은 표제어이긴 하나 뜻이 借文(대작)·借問(물음)·조선 상소문뿐이라 자동차
    문과 무관하다. 자막 표시 안은 일반 문장 규칙의 대상이 아니므로 병합하지 않는다.
    """
    assert _run("[탁 - 차 문]")[0] == "[탁 - 차 문]"
    # 표시 안에서는 병합 후보조차 만들지 않는다(표시 밖은 후보로 제안된다)
    assert not any("차문" in (f.suggested_fix or "") for f in _run("[탁 - 차 문]")[1])
    assert any("노천카페" in (f.suggested_fix or "") for f in _run("노천 카페에서 만나자")[1])


def test_historical_headword_is_not_join_evidence():
    """'미림이도 오고 했는데'를 '오고했는데'로 붙이자던 제안.

    근거였던 '오고하다'는 五考하다(역사: 벼슬아치 고과)와 제주 방언뿐이다. 사전에
    있다는 사실만으로는 현대 문장을 붙여 쓸 근거가 되지 않는다.
    """
    out, flags = _run("미림이도 오고 했는데 얼른 오라고 혀라")
    assert out == "미림이도 오고 했는데 얼른 오라고 혀라"
    assert not any("오고했는데" in (f.suggested_fix or "") for f in flags)
    # 정당한 붙임은 그대로 유지된다('하다'는 붙임형이 표제어라 자동 교정을 유지한다.
    # '선물 받았어'류는 2026-08-05에 제안으로 내렸다 — §75)
    assert _run("청소 했다")[0] == "청소했다"


def test_comma_never_splits_a_word():
    """쉼표를 어절 한가운데 넣어 원본을 왜곡하던 오류 (2026-08-02 실사용 2건).

    '정말 미안햐' -> '정말 미안,햐', '연실아' -> '연,실아'. 둘 다 kiwi가 한 어절을
    쪼갠 분석('미안'+'햐'/IC, '연'+'실'+'아'/JKV)을 그대로 믿은 결과다. 규칙마다
    막지 않고 삽입 지점 전체에 어절 경계 조건을 걸었다 — 원본 왜곡은 교정 도구가
    저지를 수 있는 가장 나쁜 실패라 개별 대응으로는 부족하다.
    """
    assert _run("정말 미안햐")[0] == "정말 미안햐"
    assert _run("[민수] 연실아")[0] == "[민수] 연실아"
    assert _run("얼른 오라고 혀라")[0] == "얼른 오라고 혀라"
    # 어절 경계에 넣는 정당한 쉼표는 그대로 유지된다
    assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"
    assert _run("먹어 준희야.")[0] == "먹어, 준희야"


def test_noun_phrase_before_hada_is_not_merged():
    """'나물 타령 하셨어'를 '나물 타령하셨어'로 붙여 버리던 과교정
    (2026-08-03 사용자 보고).

    명사가 명사를 꾸며 명사구를 이루면('나물 타령', '수학 공부') 그 뒤의 '하다'는
    접사가 아니라 동사이므로 띄어 쓴 표기가 맞다 — 온라인가나다 qna_seq=320467
    "'순간 이동을 하다'처럼 구 구성이면 띄어 씁니다".
    """
    assert _run("나물 타령 하셨어")[0] == "나물 타령 하셨어"
    assert _run("수학 공부 하다")[0] == "수학 공부 하다"
    # 앞 명사가 없으면 예전처럼 붙인다
    assert _run("청소 했다")[0] == "청소했다"
    # 앞말이 부사로도 읽히면('어제') 수식 관계가 아니므로 붙임을 유지한다
    assert _run("어제 청소 했다")[0] == "어제 청소했다"


def test_sentence_final_contraction_is_not_split_by_comma():
    """'그건 내 잘못이 아냐'가 '그건 내 잘못이, 아냐'로 잘리던 오류
    (2026-08-03 사용자 보고).

    '아냐'는 '아니야'의 준말(서술어)인데 kiwi가 감탄사(IC)로 태깅한다. 조사 뒤는
    서술어나 체언이 오는 자리이므로 그 자리의 IC는 오분석으로 본다.
    """
    assert _run("그건 내 잘못이 아냐")[0] == "그건 내 잘못이 아냐"
    assert _run("네 책임이 아냐")[0] == "네 책임이 아냐"  # '네' = 너+의(관형어)
    # 문장 맨 앞·맨 끝의 진짜 감탄사에는 그대로 쉼표를 넣는다
    assert _run("아냐 그건 아니고")[0] == "아냐, 그건 아니고"
    assert _run("싫다면 뭐")[0] == "싫다면, 뭐"


def test_contraction_gets_full_form_flag_only():
    """준말 '아냐'는 표준이므로 자동으로 바꾸지 않고 본말 후보만 플래그한다."""
    text, flags = _run("그건 내 잘못이 아냐")
    assert text == "그건 내 잘못이 아냐"
    assert any(f.suggested_fix == "그건 내 잘못이 아니야" for f in flags)


def test_honorific_dependent_noun_spacing():
    """성명 뒤 '님'·'씨'는 의존명사라 띄어 쓴다(2026-08-03 사용자 보고).

    근거: 표준국어대사전 '님'(의존 명사) "그 사람을 높여 이르는 말",
    온라인가나다 — '김 씨', '길동 씨', '홍길동 씨'로 띄어 쓰고, 성씨 자체·가문을
    뜻하는 접미사 '-씨'는 붙여 쓴다(김해 김씨).
    """
    assert _run("홍길동님 안녕하세요")[0] == "홍길동 님 안녕하세요"
    assert _run("민수씨 왔어요")[0] == "민수 씨 왔어요"
    # 직위·관계 뒤의 '-님'은 접미사 — 붙여 쓴 채로 둔다
    assert _run("사장님 계세요")[0] == "사장님 계세요"
    assert _run("고객님 반갑습니다")[0] == "고객님 반갑습니다"
    # 성 한 글자 + 씨는 두 가지로 읽혀 자동 교정하지 않고 플래그만 남긴다
    text, flags = _run("김씨는 밥을 차려 줬다")
    assert text == "김씨는 밥을 차려 줬다"
    assert any(f.suggested_fix == "김 씨는 밥을 차려 줬다" for f in flags)


def test_intensive_prefix_cheo():
    """접두사 '처-'를 '쳐'로 적은 것을 고친다(2026-08-03 사용자 보고).

    근거: 표준국어대사전 '처-먹다'("'먹다'를 속되게 이르는 말"), '처-넣다'
    ("마구 집어넣다")는 등재, '쳐먹다'·'쳐넣다'는 두 사전 모두 없음.
    """
    assert _run("쳐먹어라")[0] == "처먹어라"
    assert _run("쳐 먹어라")[0] == "처먹어라"
    assert _run("쳐넣었다")[0] == "처넣었다"
    # 쳐-형 자체가 표제어인 말은 건드리지 않는다
    assert _run("쳐다봤다")[0] == "쳐다봤다"
    assert _run("쳐들어갔다")[0] == "쳐들어갔다"
    # 보조 용언 자리는 '치다'의 활용일 수 있어 자동 교정하지 않는다
    assert _run("박수를 쳐 줘")[0] == "박수를 쳐 줘"
    # '하다' 자리는 **제안도 하지 않는다** — 붙임형 '처하다'는 한자어 處하다뿐이라
    # 대안이 못 된다(2026-08-04 사용자 지적, §64). 아래 전용 테스트 참고.
    text, flags = _run("이딴 거 너나 실컷 쳐 하든가")
    assert text == "이딴 거 너나 실컷 쳐 하든가"
    assert [f.suggested_fix for f in flags] == [""]


def test_punctuation_never_gets_a_space_before_it():
    """구두점 앞에는 공백을 두지 않는다 — 문맥과 무관한 규칙(2026-08-03 사용자 지정).

    '지랄!'을 '지랄 !'로 제안하던 것을 막는다. 띄어쓰기 제안은 문장부호를 하나의
    토막으로 보아 앞에 공백을 넣자고 할 때가 있다.
    """
    for line in ("지랄!", "이런 지랄!", "뭐라고?", "그래…", '"안녕"이라고 했다'):
        text, flags = _run(line)
        for f in flags:
            assert " !" not in (f.suggested_fix or "")
            assert " ?" not in (f.suggested_fix or "")
            assert " ." not in (f.suggested_fix or "")


def test_line_final_period_before_closing_quote():
    """닫는 따옴표 앞의 줄 끝 마침표는 지우고, 따옴표는 붙여 쓴다.

    2026-08-03 사용자 제공 자막: '"지영아, 나는 너를 좋아해. "'가 '좋아해, "'로
    바뀌었다 — 마침표 뒤에 공백과 따옴표가 있어 문장이 이어진다고 본 탓이다.
    """
    entry = SubtitleEntry(
        index=1, start="00:00:00,000", end="00:00:02,000", text='"지영아, 나는 너를 좋아해. "'
    )
    corrected, _flags, _log = correct_entries([entry], None, None, doc_type="subtitle")
    assert corrected[0].text == '"지영아, 나는 너를 좋아해"'


def test_subtitle_marker_needs_one_space_before_dialogue():
    """[] · () 뒤에 말자막이 오면 한 칸 띄운다(설정과 무관한 규칙)."""
    def _sub(text: str) -> str:
        entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text)
        return correct_entries([entry], None, None, doc_type="subtitle")[0][0].text

    assert _sub("[지영]꺼져") == "[지영] 꺼져"
    assert _sub("(민수)안녕하세요") == "(민수) 안녕하세요"
    assert _sub("(철수) 왜 그래?") == "(철수) 왜 그래?"


def test_joined_interjection_chamna():
    """'참나'는 한 감탄사로 붙여 쓴다(2026-08-03 사용자 결정).

    근거: 온라인가나다 — "'참나'가 사전에 실려 있지 않은데, 이를 띄어 쓸 근거도
    분명하지 않습니다. … 하나의 감탄사로 쓰인다면 앞으로 사전에 실릴 수도 있다."
    """
    # 띄어 쓴 것을 쉼표로 가르지 않는다(예전에는 '참, 나 어이없네'가 됐다)
    assert _run("참 나 어이없네")[0] == "참 나 어이없네"
    # 붙여 쓴 것은 그대로 둔다. 쉼표는 자동으로 넣지 않는다 — '참나'가 명사(眞我)로도
    # 읽혀(kiwi 대안 분석) 애매한 자리이므로 제안으로만 남긴다(2026-08-04 변경).
    text, flags = _run("참나 어이없네")
    assert text == "참나 어이없네"
    assert any(f.suggested_fix == "참나, 어이없네" for f in flags)
    # 띄어 쓴 것은 플래그만 남긴다. 두 읽기를 함께 알리고 **자동 적용 후보는 주지
    # 않는다** — '참나'(기막힘)와 '참, 나'(그런데/생각났는데)가 표기만으로 갈리지
    # 않기 때문이다(2026-08-03 사용자 지정).
    text, flags = _run("참 나 어이없네")
    assert len(flags) == 1
    assert not flags[0].suggested_fix
    assert "참나 어이없네" in flags[0].reason and "참, 나 어이없네" in flags[0].reason
    # 뒤에 조사가 붙으면 감탄사의 일부로 보지 않는다
    assert _run("참 나는 그렇게 생각해") == ("참 나는 그렇게 생각해", [])


def test_cheo_prefix_derivative_is_not_split():
    """'처맞고'를 '처 맞고'로 가르지 않는다(2026-08-03 사용자 보고).

    '처-'는 접두사이므로 뒤 용언에 붙여 쓴다. 파생어가 사전에 없어도(처맞다 미등재)
    띄어 쓸 근거는 없는데, kiwi는 이 '처'를 명사로 읽어 가르자고 제안했다.
    """
    text, flags = _run("처맞고 들어오는 것보다 낫다고 칭찬 날렸지")
    assert text == "처맞고 들어오는 것보다 낫다고 칭찬 날렸지"
    assert not any("처 맞고" in (f.suggested_fix or "") for f in flags)


def test_undocumented_cheo_derivative_is_corrected():
    """붙여 쓴 '쳐맞고'는 '처맞고'로 고친다(2026-08-03 사용자 지정: 쳐맞고는 틀린 표기).

    파생어가 사전에 없어도('처맞다' 미등재) 붙여 쓴 '쳐+본용언'은 접두사 결합밖에 될
    수 없다 — '맞다'는 보조 용언이 아니므로 '치어 + 맞다'를 한 어절로 붙여 쓸 근거가
    없다. 반면 **띄어 쓴** '쳐 맞고'는 건드리지 않는다: 사전에 없는 파생어라 '박수를
    쳐 웃었다'(치다 + 웃다, 두 동작)처럼 정당한 두 용언 연결과 구분할 수 없다.
    """
    assert _run("쳐맞고 들어왔다") == ("처맞고 들어왔다", [])
    assert _run("쳐 맞고 들어왔다")[0] == "쳐 맞고 들어왔다"


def test_real_manuscript_overcorrections_2026_08_03():
    """사용자 제공 자막(4강 과제)에서 발견한 과교정 4건 (2026-08-03).

    네 건 모두 원인이 같다 — **사전에 표제어가 있다는 이유로 문맥을 무시한 자동 적용**
    (`docs/DESIGN_PRINCIPLES.md` 원리 3, 우연한 사전 충돌).
    """
    # '힙하다'(우리말샘 표제어)의 어근을 kornorms 용례(hip -> 히프)로 치환했다
    assert _run("새롭고 힙한 동네에서 일하게 돼서 신나네요")[0] == (
        "새롭고 힙한 동네에서 일하게 돼서 신나네요"
    )
    # '예산안'(예산 案)이 표제어라 '예산 안(內)에서'를 붙여 버렸다
    assert _run("예산 안에서 5m 정도 늘리고")[0] == "예산 안에서 5m 정도 늘리고"
    assert _run("집 밖으로 나갔다")[0] == "집 밖으로 나갔다"
    # '더하다'가 표제어라 부사 '더' + '하다' 구성을 붙였다
    assert _run("증축을 더 해도 되겠네요")[0] == "증축을 더 해도 되겠네요"
    # 병합은 후보로만 나오고(2026-08-04), 조사 결합 교정은 그대로 자동이다
    assert any("노천카페" in (f.suggested_fix or "") for f in _run("노천 카페에서 만났다")[1])
    assert _run("오늘은날씨가 좋다")[0] == "오늘은 날씨가 좋다"


def test_interjection_comma_not_inserted_when_word_can_be_a_noun():
    """'아이 심장이 선천적으로'가 '아이, 심장이'로 갈라지던 오류
    (2026-08-04 사용자 제공 자막 5강 123·131·245번).

    kiwi가 명사 '아이'(어린아이)를 감탄사로 태깅해 쉼표 규칙이 걸렸다. 같은 낱말이
    명사·용언으로도 읽히면(kiwi 대안 분석, 같은 길이) 자동으로 넣지 않고 제안만 남긴다 —
    정말 감탄사인 경우('야 이리 와')도 같은 조건에 걸리므로 버리지 않고 넘긴다.
    """
    text, flags = _run("아이 심장이 선천적으로")
    assert text == "아이 심장이 선천적으로"
    assert any(f.suggested_fix == "아이, 심장이 선천적으로" for f in flags)

    text, flags = _run("야 이리 와")
    assert text == "야 이리 와"
    assert any(f.suggested_fix == "야, 이리 와" for f in flags)

    # 대안 읽기가 없는 감탄사는 예전처럼 자동으로 넣는다
    assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"


def test_predicate_reading_blocks_sentence_final_comma():
    """'무슨 일인데 그래?'가 '무슨 일인데, 그래?'로 바뀌던 오류(5강 334번).

    '그래'는 '그렇다'의 활용(서술어)으로도 읽힌다. 문장 끝 자리에서는 **용언 읽기만**
    근거로 쓴다 — 대명사까지 넓히면 '싫다면 뭐'처럼 이미 정답으로 확정한 교정이 막힌다.
    """
    assert _run("무슨 말이야, 무슨 일인데 그래?")[0] == "무슨 말이야, 무슨 일인데 그래?"
    assert _run("싫다면 뭐")[0] == "싫다면, 뭐"


def test_no_space_before_punctuation_in_auto_correction():
    """'하지만...'이 '하지만 ...'으로 벌어지던 오류(5강 401·402번).

    연결부사(MAJ) 뒤에 공백을 강제하는 규칙이 문장부호 앞에서도 걸렸다. 구두점 앞에는
    공백을 두지 않는다는 규칙은 문맥과 무관하다(2026-08-03 사용자 지정).
    """
    assert _run("다 해 볼 겁니다, 하지만...")[0] == "다 해 볼 겁니다, 하지만..."
    assert _run("'하지만'이라뇨?")[0] == "'하지만'이라뇨?"


def test_person_name_is_not_rewritten_by_loanword_rule():
    """등장인물 '러스'(Russ)가 '루스'로 바뀌던 오류
    (2026-08-04 사용자 제공 자막 7강 123번).

    kornorms에 'Ruth, Babe'·'Luce, Henry Robinson'의 오표기로 '러스(X)'가 등재돼 있어
    정답이 하나로 모인 것처럼 보였다. 사람 이름의 정답은 원어를 알아야 갈리는데 텍스트만
    으로는 알 수 없다 — 인명·지명 용례만 근거이면 자동 반영하지 않고 플래그한다.
    kiwi 1순위 태그도 믿을 수 없어(같은 이름이 문장에 따라 NNG로 태깅된다) 대안 분석에
    고유명사 읽기가 있으면 고유명사로 본다.
    """
    text, flags = _run("- 연락 안 했다고? 세상에, 러스\n- 당신이랑 같이 하려고 했지")
    assert "러스" in text and "루스" not in text
    assert flags  # 확인 항목으로는 남는다
    # 일반 용어 외래어 교정은 그대로 자동이다
    assert _run("저는 초코렛을 좋아해요")[0] == "저는 초콜릿을 좋아해요"
    assert _run("리모콘 어디 있어")[0] == "리모컨 어디 있어"


def test_possessive_adnominal_blocks_affix_join():
    """'내 탓 하지 마'가 '내 탓하지 마'로 붙던 오류(7강 147번).

    '내'를 kiwi가 '나'(NP)+'의'(JKG)로 읽어 MM/ETM 조건에 걸리지 않았다. 관형격 조사도
    관형어를 만들므로 그 뒤 명사에 붙는 '하다'는 띄어 쓴다.
    """
    assert _run("내 탓 하지 마")[0] == "내 탓 하지 마"
    assert _run("네 탓 하지 마")[0] == "네 탓 하지 마"
    # 관형어가 없으면 예전처럼 붙인다
    assert _run("청소 했다")[0] == "청소했다"


def test_adnominal_reading_interjection_is_flagged_not_auto_comma():
    """'빌어먹을 차 안 세우면'이 '빌어먹을, 차 안 세우면'으로 갈라지던 오류
    (2026-08-04 사용자 제공 자막 7강 374번, 사용자 판정: 플래깅 대상).

    '빌어먹을'은 감탄사(욕)로도, '빌어먹다'의 관형사형(그 망할)으로도 읽힌다. 관형어면 뒤
    체언을 꾸미므로 쉼표를 넣으면 문장이 갈라진다. 대안 분석이 두 토큰('빌어먹'+'을')이라
    같은 길이 한 토큰만 보는 기존 가드로는 잡히지 않았다.
    """
    text, flags = _run("빌어먹을 차 안 세우면 뛰어내릴 줄 알아")
    assert text == "빌어먹을 차 안 세우면 뛰어내릴 줄 알아"
    assert any(
        f.suggested_fix == "빌어먹을, 차 안 세우면 뛰어내릴 줄 알아" for f in flags
    )
    # 관형어 읽기가 없는 감탄사는 예전처럼 자동으로 넣는다
    assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"


def test_loanword_flag_carries_source_lookup_token():
    """외래어 음차 플래그는 **원어 입력칸**을 띄울 토막을 함께 실어야 한다(§61).

    음차의 정답은 원어가 무엇이냐로 갈린다 — '러스'는 원어가 Ruth면 '루스',
    Russ면 '러스'가 맞다(7강 123번). 화면이 그 자리에서 원어를 받아
    `/api/loanword-source`로 확인할 수 있게 토막을 내보낸다.
    """
    _text, flags = _run("- 연락 안 했다고? 세상에, 러스\n- 당신이랑 같이 하려고 했지")
    lookup_flags = [f for f in flags if f.source_lookup_token]
    assert lookup_flags, "외래어 음차 플래그에 원어 조회 토막이 없다"
    assert any(f.source_lookup_token == "러스" for f in lookup_flags)
    # 사유 문구가 "무엇을 확인해야 하는지"를 말해 준다(`docs/BACKLOG.md` 28번).
    assert any("원어가 무엇인지 확인" in f.reason for f in lookup_flags)


def test_cheo_hada_has_no_valid_joined_form():
    """'쳐 하다'·'쳐하다'는 **둘 다 비표준**이고 대안도 없다(2026-08-04 사용자 지적, §64).

    전에는 `쳐 하든가`에 `처하든가`를 제안했다. 그 표제어는 한자어 處하다(어떤 형편에
    놓이다)여서 접두사 '처-'(마구/속되게) 용법이 아니다 — 붙임형이 표제어라는 사실만
    근거로 삼은 긍정 근거 사고다(§58). 이제 제안 없이 사유만 알린다.
    """
    from subtitle_corrector.engine import check_intensive_prefix_cheo

    for text in ("알아서 쳐 하든가", "쳐하든가", "쳐 하지 마"):
        flag = check_intensive_prefix_cheo(1, text)
        assert flag is not None, text
        assert not flag.suggested_fix  # 대안을 만들 수 없다
        assert "處하다" in flag.reason and "표준 표기가 아닙니다" in flag.reason
        # 텍스트는 절대 바뀌지 않는다.
        assert _run(text)[0] == text

    # 고유어 파생어(처먹다·처박다)는 지금까지처럼 자동 교정한다.
    assert _run("쳐먹어라")[0] == "처먹어라"
    assert _run("쳐 먹어라")[0] == "처먹어라"
    assert _run("쳐박혀 있어")[0] == "처박혀 있어"
    # '치다'의 활용 자리는 건드리지 않는다.
    assert _run("박수를 쳐 줘")[0] == "박수를 쳐 줘"
    assert _run("공을 쳐 봐")[0] == "공을 쳐 봐"


def test_term_usage_headword_blocks_person_name_suggestion():
    """`쉴러병`을 `실러병`으로 바꾸자고 제안하던 오류(2026-08-05 사용자 보고, §66).

    kornorms에 인명 Schiller의 오표기로 `쉴러(X)`가 등재돼 있어 `실러`를 제안했다.
    그런데 우리말샘에는 `쉴러^검사`·`쉴러^플랜`·`한트·쉴러·크리스찬-병`이 표준
    표제어로 있다 — 전문 용어·복합 명칭에서는 '쉴러'가 쓰인다. 인명 용례 하나로 그
    표기를 갈아 치울 수 없으므로 한쪽을 정답이라고 말하지 않고 **두 근거를 나란히 보여 주며 확인을 구한다**(제안은 기본 미채택으로 남긴다).
    """
    for line in ("쉴러병 진단을 받았다", "쉴러 검사 결과가 나왔다", "쉴러 플랜을 도입했다"):
        text, flags = _run(line)
        assert text == line  # 자동 교정은 하지 않는다
        related = [f for f in flags if "쉴러" in f.reason]
        assert related, line
        # 한쪽을 정답이라고 말하지 않는다 — 두 근거를 나란히 보여 주고 확인을 구한다
        # (2026-08-05 사용자 지시: Schiller가 실러인지 쉴러인지 알 수 없으므로 확인할 것).
        assert all("둘 다 근거가 있습니다" in f.reason for f in related)
        assert all("확인해 주세요" in f.reason for f in related)
        assert all("우리말샘에는" in f.reason for f in related)
        # 제안은 남긴다(기본 미채택) — 인명으로 판단되면 체크 한 번으로 반영한다.
        assert all(f.suggested_fix == line.replace("쉴러", "실러", 1) for f in related)
        assert all(f.source_lookup_token == "쉴러" for f in related)  # 원어 확인 칸도 유지

    # 표제어 구성 요소가 아닌 표기는 지금까지처럼 제안한다.
    _text, flags = _run("스노우 기자가 왔다")
    assert any(f.suggested_fix == "스노 기자가 왔다" for f in flags)
    # 일반 용어 자동 교정도 그대로다.
    assert _run("저는 초코렛을 좋아해요")[0] == "저는 초콜릿을 좋아해요"


# --- 2026-08-05 원어 입력칸 실사용 감수(§68) ---

def test_no_flag_when_another_rule_already_fixed_the_spelling():
    """제안이 원문과 똑같은 플래그를 내보내지 않는다.

    `correct_loanwords()`는 고유명사 읽기가 있으면 자동 반영하지 않고 제안만 남기는데
    (`러스` 사고), 뒤에 오는 `correct_nonstandard_terms()`가 같은 자리를 자동으로
    고친다. 그러면 이 플래그의 제안이 원문과 글자 하나 다르지 않아 번역가는 무엇을
    확인하라는 것인지 알 수 없다."""
    out, flags = _run("앰블런스 소리 들려? 정문 쪽이야")
    assert out == "앰뷸런스 소리 들려? 정문 쪽이야"
    assert not [f for f in flags if f.suggested_fix == f.original_text]


def test_flag_wording_picks_the_right_particle_allomorph():
    """받침 없는 낱말 뒤에 '이'를 박아 두어 "'루스'이 맞고"가 나갔다 — 맞춤법
    교정기가 내는 문구라 특히 눈에 띈다."""
    _out, flags = _run("러스, 자료실 열쇠 어디 있어?")
    reason = next(f.reason for f in flags if f.source_lookup_token == "러스")
    assert "'루스'가 맞고" in reason
    assert "'러스'가 맞을 수 있습니다" in reason
    assert "'루스'이" not in reason and "'러스'이" not in reason


# --- 2026-08-05 사용자 보고 3건(§73) ---

def test_adnominal_modified_noun_is_not_joined_to_hada():
    """관형어가 꾸미는 명사 뒤의 '하'는 접미사가 아니라 동사라 띄어 쓴다.

    `마음의 준비 해`가 `마음의 준비해`로 붙었다 — 붙인 것은 제41항 접사 규칙
    (`_mechanical_respace`)이었고 거기에만 관형어 가드가 없었다. 관형격 조사(JKG)
    자리는 가르는 규칙에도 빠져 있었다."""
    for text in ("마음의 준비 해", "떨어지면 받을 준비 해", "내 탓 하지 마"):
        assert _run(text)[0] == text
    # 이미 붙여 쓴 것은 갈라 준다.
    assert _run("마음의 준비해")[0] == "마음의 준비 해"


def test_term_spacing_is_unified_when_principle_is_chosen():
    """2단계에서 '원칙'을 골랐으면 제49·50항 혼용은 묻지 않고 맞춘다."""
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    lines = ["무게 중심이 앞으로 쏠린다", "무게중심을 낮춰라",
             "무게 중심을 잡아", "무게중심이 중요하다"]
    entries = [SubtitleEntry(index=i + 1, start="", end="", text=t) for i, t in enumerate(lines)]
    corrected, flags, log = correct_entries(entries, spacing_mode="principle")
    assert [e.text for e in corrected] == ["무게 중심이 앞으로 쏠린다", "무게 중심을 낮춰라",
                                           "무게 중심을 잡아", "무게 중심이 중요하다"]
    assert not [f for f in flags if "혼용" in f.reason]
    assert any("제49·50항 통일" in note.message for note in log)


def test_term_spacing_unifies_toward_joined_when_allowance_is_chosen():
    """'허용'을 고르면 붙여 쓴 변이형으로 통일한다(2026-08-05 사용자 지적으로 바로잡음)."""
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    lines = ["무게 중심이 앞으로 쏠린다", "무게중심을 낮춰라"]
    entries = [SubtitleEntry(index=i + 1, start="", end="", text=t) for i, t in enumerate(lines)]
    corrected, flags, _log = correct_entries(entries, spacing_mode="allowance")
    assert [e.text for e in corrected] == ["무게중심이 앞으로 쏠린다", "무게중심을 낮춰라"]
    assert not [f for f in flags if "혼용" in f.reason]


def test_loanword_evidence_states_which_side_is_settled():
    """인명 표기는 심의를 거친 확정 표기이고 사전 표제어 쪽은 미확정이다 —
    두 근거를 같은 무게로 제시하면 안 된다(2026-08-05 사용자 지적)."""
    _out, flags = _run("쉴러병 환자 기록을 다시 뒤지려고")
    reason = next(f.reason for f in flags if "외래어 표기 확인" in f.reason)
    assert "심의를 거쳐 확정된" in reason
    assert "규범으로 확정된 것이 아니어서" in reason
    assert "교정할 때마다 사전을 다시 조회합니다" in reason


def test_honorific_aux_verb_follows_the_plain_form_headword():
    """'봐드리다'는 미등재지만 '봐주다'가 표제어다 — 높임형이라고 갈라 쓰지 않는다.

    제47항 해설의 "'도와드리다'는 '도와주다'가 사전 표제어인 것에 맞춰 항상 붙임"을
    특정 낱말이 아니라 관계로 일반화한 것이다(2026-08-05 사용자 보고)."""
    assert _run("오늘은 좀 봐드릴게요")[0] == "오늘은 좀 봐드릴게요"
    assert _run("들어드릴게요")[0] == "들어드릴게요"
    assert _run("도와드릴게요")[0] == "도와드릴게요"
    # 낮춤형도 미등재면 제47항 원칙대로 띄어 쓴다 — 사전이 정한다.
    assert _run("읽어드릴게요")[0] == "읽어 드릴게요"


def test_negation_aux_is_not_treated_as_optional_spacing():
    """'-지 않다'는 제47항 붙임 허용 대상이 아니라 언제나 띄어 쓴다.

    보조 용언 태그만 보고 세다가 "'않' 띄어쓰기가 섞였다"는 플래그를 냈다 —
    규정이 인정하지 않는 표기를 선택지로 내놓은 것이라 판정 자체가 틀렸다
    (2026-08-05 사용자 지적)."""
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    lines = ["그렇지 않아요", "가지 않았다", "먹지 않는다", "그렇잖아요"]
    entries = [SubtitleEntry(index=i + 1, start="", end="", text=t) for i, t in enumerate(lines)]
    _corrected, flags, _log = correct_entries(entries)
    assert not [f for f in flags if "보조 용언 '않'" in f.reason]


def test_real_aux_verb_mixture_is_still_flagged():
    """진짜 붙임 허용 구성('-아/-어 + 보조 용언')의 혼용은 그대로 잡는다."""
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    lines = ["한번 해 보자", "다시 해보자"]
    entries = [SubtitleEntry(index=i + 1, start="", end="", text=t) for i, t in enumerate(lines)]
    _corrected, flags, _log = correct_entries(entries)
    assert [f for f in flags if "보조 용언 '보'" in f.reason]


def test_brand_name_flag_points_to_the_official_korean_spelling():
    """상표·브랜드는 표기법보다 한국 지사 공식 표기가 우선이다(2026-08-05 사용자 지적).
    자동 반영하지 않는 것은 전부터 그랬고, 무엇을 근거로 확인할지 문구가 말해 준다."""
    _out, flags = _run("파이롯트 만년필을 샀다")
    reason = next(f.reason for f in flags if "고유명사 외래어 표기" in f.reason)
    assert "상표·브랜드" in reason
    assert "한국 지사 공식 표기가 우선" in reason


def _unify(lines, mode):
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    entries = [SubtitleEntry(index=i + 1, start="", end="", text=t) for i, t in enumerate(lines)]
    corrected, flags, log = correct_entries(entries, spacing_mode=mode)
    return [e.text for e in corrected], flags, log


def test_term_spacing_is_unified_in_both_directions():
    """2단계 선택이 곧 답이다 — 원칙이면 띄우고 허용이면 붙인다.

    처음에는 띄우는 방향만 자동으로 했다가 사용자 지적으로 바로잡았다("붙임도
    허용이므로 2단계 지정에 따라 달라질 수 있다"). 혼용이라는 말 자체가 붙여 쓴
    표기도 문서에 있다는 뜻이라 붙이는 쪽도 경계를 추측할 일이 없다."""
    lines = ["무게 중심이 앞으로 쏠린다", "무게중심을 낮춰라", "무게 중심을 잡아"]
    joined, flags, _ = _unify(lines, "allowance")
    assert joined == ["무게중심이 앞으로 쏠린다", "무게중심을 낮춰라", "무게중심을 잡아"]
    assert not [f for f in flags if "혼용" in f.reason]


def test_partial_join_is_not_spread_under_allowance():
    """부분만 붙인 변이형밖에 없으면 허용에서도 통일하지 않는다 — 제50항의 전문
    용어 붙임은 전부 붙이거나 전부 띄어야 한다."""
    lines = ["만성 골수성 백혈병 진단", "만성골수성 백혈병 치료"]
    kept, flags, _ = _unify(lines, "allowance")
    assert kept == lines
    assert [f for f in flags if "혼용" in f.reason]


def test_dictionary_confirmed_term_phrase_joins_under_allowance():
    """혼용이 아니어도 사전이 전문 용어(명사구)로 확인해 준 구간은 허용에서 붙인다.
    표준국어대사전의 캐럿 표기(`무게^중심`)가 제50항 대상이라는 확인이다."""
    joined, _flags, _log = _unify(["무게 중심이 쏠린다", "예방 접종을 받았다"], "allowance")
    assert joined == ["무게중심이 쏠린다", "예방접종을 받았다"]
    # 원칙에서는 띄어 쓴 원문이 이미 정답이다.
    kept, _f, _l = _unify(["무게 중심이 쏠린다", "예방 접종을 받았다"], "principle")
    assert kept == ["무게 중심이 쏠린다", "예방 접종을 받았다"]


def test_brand_compound_is_not_partially_corrected():
    """사전에 없는 복합어의 조각만 고치면 상표 이름이 조용히 바뀐다.

    `매직블럭`이 `매직`+`블럭`으로 쪼개져 `매직블록`이 됐다(2026-08-05 사용자 지적:
    "브랜드 명칭은 전부 한국 지사 공식 명칭을 확인해 줘야 한다")."""
    out, flags = _run("매직블럭 제품을 샀다")
    assert out == "매직블럭 제품을 샀다"
    assert [f for f in flags if "외래어" in f.reason]
    # 조사가 붙은 것은 복합어가 아니므로 정상 교정은 그대로다.
    assert _run("초코렛이라도 좀 먹어")[0] == "초콜릿이라도 좀 먹어"


def test_quantity_expression_not_merged_with_hada_via_particle_spacing():
    """수량 표현 뒤 '하다'는 조사·어미 규칙(제41항) 경로로도 붙이면 안 된다.

    2026-09-02 실사용 감수(인터뷰 전사)에서 '20번 했어'가 '20번했어'로 붙었다.
    kiwi가 '하'를 XSV(파생접미사)로 태깅해 `correct_particle_spacing`이 무조건
    붙였는데, '번하다'가 우연히 표준국어대사전 표제어라서다("어두운 가운데 밝은
    빛이 비치어 조금 훤하다" — 원문의 '20번 하다'와 무관한 동형이의어, 원리3).
    `correct_action_noun_affix`(affix.py)에는 같은 수량 가드가 이미 있었지만,
    실제로 이 사고를 낸 건 별개 경로인 이 함수였다(§60 부류)."""
    assert _run("20번 했어")[0] == "20번 했어"
    assert _run("3세트 해라")[0] == "3세트 해라"
