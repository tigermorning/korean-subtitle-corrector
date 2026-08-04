"""'몇' + 수사 자리의 원문 표기를 지킨다(`docs/BACKLOG.md` 4번, §64).

4번은 "제44항 수 표기(`몇만`/`몇백만`) 자동교정 승격"이었는데, 조사 결과 **승격할
근거가 없었다**. `몇만`·`몇십`·`몇백`·`몇천`·`몇억`·`몇백만`은 표준국어대사전·
우리말샘에 전부 미등재이고(접두사 '수-' 파생어 `수만`·`수백만`·`수십만`은 등재),
제44항은 수의 자릿수 띄어쓰기 조항이라 '몇'과 수사의 결합을 직접 답하지 않는다.

대신 kiwi가 붙여 쓴 `몇만 원`을 `몇 만 원`으로 갈라 쓰자고 제안하던 것을 막았다 —
근거가 토큰 경계뿐인 제안이다. 실시간 사전 API를 호출한다.
"""
from subtitle_corrector.engine import check_spacing, correct_entries
from subtitle_corrector.parsers import SubtitleEntry


def _suggestion(text):
    flag = check_spacing(1, text)
    return flag.suggested_fix if flag else None


def test_joined_number_is_left_alone():
    """붙여 쓴 표기를 갈라 쓰자고 제안하지 않는다(막연한 큰 수 표기)."""
    assert _suggestion("몇만 원이나 들었어") is None
    assert _suggestion("몇백만 명이 봤다") is None
    assert _suggestion("몇십 명이 왔다") is None


def test_spaced_number_is_left_alone():
    """띄어 쓴 표기도 붙이자고 제안하지 않는다 — '몇'이 정확한 수를 묻는 의문일 때는
    띄어 쓰는 자리다('정확히 몇 만 번'). 텍스트만으로는 어느 쪽인지 가릴 수 없다."""
    assert _suggestion("몇 만 원이나 들었어") is None
    assert _suggestion("정확히 몇 만 번 했습니까") is None
    assert _suggestion("몇 백만 명이 봤다") is None


def test_unrelated_number_expressions_unaffected():
    assert _suggestion("몇 명이 왔어") is None  # 의존명사 '명'은 원래 띄어 쓴다
    assert _suggestion("20만 명이 왔다") is None
    assert _suggestion("수백만 명이 봤다") is None  # '수-' 파생어는 표제어다


def test_text_is_never_changed_by_this_class():
    """자동 교정은 하지 않는다 — 원문 표기가 그대로 나가야 한다."""
    for text in ("몇만 원이나 들었어", "몇 만 원이나 들었어", "몇백만 명이 봤다"):
        entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000",
                              text=text, speaker=None)
        corrected, _flags, _log = correct_entries([entry], None, None)
        assert corrected[0].text == text
