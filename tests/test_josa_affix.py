"""동작성 명사 + 접사(하다/시키다/당하다/받다/되다) 붙여쓰기 정답표.

근거: 번역가_교육자료_요약.md §"동사/접사 구분법" + 사용자 실사용 피드백.
핵심: 동작성 있는 명사 뒤 접사는 붙이고, 동작성 없는 명사 뒤에서는 동사라 띄운다.
동작성 신호(word_exists(N+'하다'))의 동형이의어 오탐지(상하다 등)은 제외 집합으로 막는다.
"""
from subtitle_corrector.engine import correct_action_noun_affix


def _attach(text):
    return correct_action_noun_affix(text)[0]


# --- 붙여야(동작성 명사 + 접사) ---

def test_attach_action_noun_affixes():
    """**'하다'와 '되다'만 자동으로 붙인다**(2026-08-05, §75).

    `시키다`·`받다`·`당하다`는 붙임 근거가 간접적이라 자동 교정에서 내리고 제안으로
    남겼다 — `술하다`(述하다)가 표제어인 탓에 `술 시켜요`가 `술시켜요`로 붙은 것이
    계기다. 아래 `test_indirect_affixes_are_only_suggested` 참고."""
    assert _attach("음악 하는 사람") == "음악하는 사람"
    assert _attach("해체 되다") == "해체되다"  # 되다는 붙임형이 표제어일 때만


def test_indirect_affixes_are_only_suggested():
    """`시키다`·`받다`·`당하다`는 텍스트를 바꾸지 않고 제안만 남긴다.

    근거가 **다른 낱말**(`N하다`)이라 동형이의어 하나에 뚫린다: `술하다`=述하다,
    `밥하다`=밥을 짓다. 근거를 강화하는 쪽은 막혀 있다 — 붙임형 등재를 요구하면
    `사랑받다`·`청소시키다`·`교육시키다`가 전부 미등재라 규칙이 죽는다(실측 18건 중
    등재는 `무시당하다` 하나)."""
    from subtitle_corrector.engine import check_action_noun_affix

    for text, joined in (
        ("선물 받았어", "선물받았어"),
        ("배달 시켜서 먹자", "배달시켜서 먹자"),
        ("사랑 받다", "사랑받다"),
        ("무시 당하다", "무시당하다"),
    ):
        assert _attach(text) == text
        assert check_action_noun_affix(0, text).suggested_fix == joined


def test_object_noun_is_never_joined_to_sikida():
    """사물 명사는 자동으로도, 제안으로도 붙이지 않는다 — `술하다`·`밥하다`가
    표제어라 동작성 신호는 통과하지만 `술시키다`·`밥시키다`는 낱말이 아니다."""
    from subtitle_corrector.engine import check_action_noun_affix

    assert _attach("일단 술 시켜요") == "일단 술 시켜요"
    assert _attach("밥 시켜 먹자") == "밥 시켜 먹자"
    # 제안은 남지만 사유가 "사물이면 원문이 맞다"를 분명히 말한다.
    flag = check_action_noun_affix(0, "일단 술 시켜요")
    assert flag is not None
    assert "사물을 뜻하면" in flag.reason
    assert "사전에 없습니다" in flag.reason
    # 앞말이 명사인 명사구('국어 공부')는 붙이지 않는다 — 접사 '-하다/-시키다'는
    # 단일 명사 뒤에 붙으므로 구 구성이면 띄어 쓴다(온라인가나다 qna_seq=320467).
    # 2026-08-03 이전에는 '국어 공부시키다'로 붙였다(`docs/log-archive/2026-h2.md` §53).
    assert _attach("국어 공부 시키다") == "국어 공부 시키다"


# --- 띄워야(동작성 없음 / 동형이의어 오탐지 / 되다 비피동 / 명사구) ---

def test_space_non_action_and_homonyms():
    # 동형이의어 오탐지 방지(상하다·상당하다·상되다가 있어도 상은 동작성 아님)
    assert _attach("상 받다") == "상 받다"
    assert _attach("돈 받다") == "돈 받다"
    assert _attach("벌 받다") == "벌 받다"
    assert _attach("상 하다") == "상 하다"
    # '사진하다' 표제어 3개(仕進/査陳/寫眞)가 전부 현대에 안 쓰이는 옛 뜻이라
    # 동작성 신호가 무효다(2026-08-28 사용자 실사용 보고, BACKLOG 최우선 항목)
    assert _attach("사진 하러 가") == "사진 하러 가"
    assert _attach("사진 하는 사람 맞아") == "사진 하는 사람 맞아"
    # 동작성 없는 명사
    assert _attach("짜장면 시켜서") == "짜장면 시켜서"
    assert _attach("카톡 해") == "카톡 해"
    # 되다: 붙임형이 표제어가 아니면 띄움
    assert _attach("팀장 되다") == "팀장 되다"
    assert _attach("도움 되는 자료") == "도움 되는 자료"
    # 명사구엔 접사 안 붙음(피싱은 동작성 아님)
    assert _attach("보이스 피싱 당했어") == "보이스 피싱 당했어"
    # 접사 없음
    assert _attach("밥 먹자") == "밥 먹자"


def test_onomatopoeia_stays_spaced():
    # 의성어(우당탕)는 kiwi가 부사(MAG)로 태깅하고 '잘하다'와 구별되지 않아
    # 자동 붙임하지 않는다(의성어 뒤 띄움이 원칙). 언더어태치(안전).
    assert _attach("우당탕 하는 소리") == "우당탕 하는 소리"


def test_already_joined_untouched():
    assert _attach("선물받았어") == "선물받았어"


def test_quantity_lead_keeps_noun_phrase_spaced():
    """수량 표현 뒤 명사는 그 수량을 받는 자립 명사라 뒤의 되다/하다를 붙이지 않는다.

    `250cc 정도 됩니다`가 `정도됩니다`로 붙던 과교정(`docs/BACKLOG.md` 27번).
    붙임 근거였던 `정도되다`는 定都되다(도읍이 정해지다)로 원문의 程度와 무관한
    동형이의어다 — 사전 표제어라는 사실만으로는 원문이 틀렸다는 근거가 못 된다.
    """
    assert _attach("250cc 정도 됩니다") == "250cc 정도 됩니다"
    assert _attach("3년 정도 됐어요") == "3년 정도 됐어요"
    assert _attach("세 개 정도 됩니다") == "세 개 정도 됩니다"
    # 수량이 앞에 없으면 지금까지처럼 붙인다
    assert _attach("해체 되다") == "해체되다"


# --- 관할 겹침: 붙임 규칙과 분리 규칙이 같은 경계를 서로 반대로 만진다 ---
#
# '명사 + 하'(XSV) 경계 하나를 세 규칙이 건드린다(`docs/BACKLOG.md` 29번,
# `docs/IMPLEMENTATION_LOG.md` §60).
#
#   correct_particle_spacing          '생각 해' -> '생각해'  (제41항, XSV는 앞말에 붙임)
#   correct_adnominal_noun_verb_split '생각해' -> '생각 해'  (관형어가 명사를 꾸미면 가름)
#   correct_action_noun_affix         '생각 해' -> '생각해'  (동작성 명사 + 접사)
#
# **파이프라인 순서가 정답을 정한다**(`subtitle_corrector/engine/pipeline.py`의
# 188~195줄: 붙임 -> 분리 -> 접사 붙임). 이 순서에서는 붙임 규칙이 경계를 먼저
# 붙여 놓으므로 분리 규칙이 유일한 판정자가 되고, 결과가 **원문 띄어쓰기와
# 무관해진다**. 순서를 뒤집으면 그 성질이 깨진다(코퍼스 616줄 실측: 뒤집었을 때만
# 갈리는 줄 2건). 아래 테스트가 그 성질을 고정한다 — 파이프라인 순서를 바꾸면 깨진다.

def _three_rules(text):
    """pipeline.py:188~195와 같은 순서로 세 규칙만 돌린다."""
    from subtitle_corrector.engine import (
        correct_adnominal_noun_verb_split,
        correct_particle_spacing,
    )

    text = correct_particle_spacing(text)[0]
    text = correct_adnominal_noun_verb_split(text)[0]
    return correct_action_noun_affix(text)[0]


def test_overlapping_rules_converge_regardless_of_source_spacing():
    """같은 문장을 띄어 써 왔든 붙여 써 왔든 결과가 같아야 한다."""
    # 관형형('만나+ㄹ')이 '생각'을 꾸미므로 정답은 띄움 — 양쪽 다 띄움으로 모인다.
    assert _three_rules("수더분한 여자 만날 생각 해") == "수더분한 여자 만날 생각 해"
    assert _three_rules("수더분한 여자 만날 생각해") == "수더분한 여자 만날 생각 해"
    # 관형사(MM) '무슨'도 같다.
    assert _three_rules("무슨 공부 하냐") == "무슨 공부 하냐"
    assert _three_rules("무슨 공부하냐") == "무슨 공부 하냐"
    # 관형어가 없으면(부사 수식) 정답은 붙임 — 양쪽 다 붙임으로 모인다.
    assert _three_rules("잘 생각 해") == "잘 생각해"
    assert _three_rules("잘 생각해") == "잘 생각해"


def test_overlapping_rules_reach_a_fixed_point():
    """출력을 다시 넣어도 더 바뀌지 않아야 한다(규칙끼리 진동하지 않는다).

    코퍼스 616줄에서 위반 0건임을 `tools/audit_rule_overlap.py`로 확인했다.
    """
    for text in (
        "수더분한 여자 만날 생각 해",
        "무슨 공부하냐",
        "잘 생각 해",
        "어제 청소 했다",
    ):
        once = _three_rules(text)
        assert _three_rules(once) == once


# --- 30번: kiwi가 '하'를 동사(VV)로 읽는 자리는 플래그로만 (2026-08-04 사용자 결정) ---

def _flag(text):
    from subtitle_corrector.engine import check_adnominal_noun_verb_split

    return check_adnominal_noun_verb_split(1, text)


def test_vv_reading_is_flagged_not_auto_split():
    """관형어 + 붙여 쓴 '명사+하다'에서 '하'가 VV로 태깅된 자리는 제안만 남긴다.

    자동 교정은 XSV 자리만 가른다(`docs/BACKLOG.md` 30번). VV까지 자동으로 가르면
    붙임형이 표제어인 고정 표현이 깨진다 — 실측에서 `두말하다`·`한잔하다`·
    `딴말하다`·`딴짓하다`가 전부 갈릴 후보로 잡혔다(§60).
    """
    from subtitle_corrector.engine import correct_adnominal_noun_verb_split

    for text, suggested in (
        ("이런 말했어", "이런 말 했어"),
        ("첫 방송했어", "첫 방송 했어"),
        ("여러 말했어", "여러 말 했어"),
    ):
        assert correct_adnominal_noun_verb_split(text)[0] == text  # 자동 교정 없음
        flag = _flag(text)
        assert flag is not None and flag.suggested_fix == suggested

    # 고정 표현도 제안까지는 나오지만(사람이 붙임형이 맞다고 판단하면 반영하지 않는다)
    # 텍스트는 절대 바뀌지 않는다 — 자동으로 깨지던 부류가 이것이다.
    for text in ("두말하지 마", "한잔했어", "딴말하지 마", "딴짓하지 마"):
        assert correct_adnominal_noun_verb_split(text)[0] == text


def test_no_flag_when_already_spaced_or_no_adnominal():
    assert _flag("이런 말 했어") is None  # 이미 띄어 써 있다
    assert _flag("잘 말했어") is None  # 부사 수식은 붙임이 맞다
    assert _flag("공부했어") is None  # 관형어가 없다
