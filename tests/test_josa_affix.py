"""동작성 명사 + 접사(하다/시키다/당하다/받다/되다) 붙여쓰기 정답표.

근거: 번역가_교육자료_요약.md §"동사/접사 구분법" + 사용자 실사용 피드백.
핵심: 동작성 있는 명사 뒤 접사는 붙이고, 동작성 없는 명사 뒤에서는 동사라 띄운다.
동작성 신호(word_exists(N+'하다'))의 동형이의어 오탐(상하다 등)은 제외 집합으로 막는다.
"""
from subtitle_corrector.engine import correct_action_noun_affix


def _attach(text):
    return correct_action_noun_affix(text)[0]


# --- 붙여야(동작성 명사 + 접사) ---

def test_attach_action_noun_affixes():
    assert _attach("선물 받았어") == "선물받았어"
    assert _attach("배달 시켜서 먹자") == "배달시켜서 먹자"
    assert _attach("전화 받다") == "전화받다"
    assert _attach("사랑 받다") == "사랑받다"
    assert _attach("심부름 시키다") == "심부름시키다"
    assert _attach("무시 당하다") == "무시당하다"
    assert _attach("음악 하는 사람") == "음악하는 사람"
    assert _attach("해체 되다") == "해체되다"  # 되다는 붙임형이 표제어일 때만
    # 앞말이 명사인 명사구('국어 공부')는 붙이지 않는다 — 접사 '-하다/-시키다'는
    # 단일 명사 뒤에 붙으므로 구 구성이면 띄어 쓴다(온라인가나다 qna_seq=320467).
    # 2026-08-03 이전에는 '국어 공부시키다'로 붙였다(`docs/IMPLEMENTATION_LOG.md` §53).
    assert _attach("국어 공부 시키다") == "국어 공부 시키다"


# --- 띄워야(동작성 없음 / 동형이의어 오탐 / 되다 비피동 / 명사구) ---

def test_space_non_action_and_homonyms():
    # 동형이의어 오탐 방지(상하다·상당하다·상되다가 있어도 상은 동작성 아님)
    assert _attach("상 받다") == "상 받다"
    assert _attach("돈 받다") == "돈 받다"
    assert _attach("벌 받다") == "벌 받다"
    assert _attach("상 하다") == "상 하다"
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
