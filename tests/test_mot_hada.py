"""부사 뒤 '하다'가 표준어에서 '못하다'로 굳은 자리(`docs/BACKLOG.md` 24번).

`안절부절하다`는 비표준이고 `안절부절못하다`가 표준어다(표준어 규정 제25항). 낱말
치환 목록으로는 `안절부절하다` 하나만 잡히고 활용형(`안절부절했다`·`안절부절하지`·
`안절부절해`)은 놓친다 — 평가셋 g05가 그 이유로 실패했다. 그래서 형태소 경계에서
'하' 앞에 '못'을 끼운다.

근거는 **부정 근거**다: `부사+하다`가 사전에 없고 `부사+못하다`가 표제어일 때만.
다른 테스트와 마찬가지로 실시간 사전 API를 호출한다.
"""
from subtitle_corrector.engine import correct_entries, correct_mot_hada_compound
from subtitle_corrector.parsers import SubtitleEntry


def _fix(text):
    return correct_mot_hada_compound(text)[0]


def test_inserts_mot_in_every_conjugation():
    assert _fix("그는 안절부절했다") == "그는 안절부절못했다"
    assert _fix("안절부절하지 마") == "안절부절못하지 마"
    assert _fix("안절부절해") == "안절부절못해"
    assert _fix("어쩔 줄 몰라 안절부절하더라") == "어쩔 줄 몰라 안절부절못하더라"
    assert _fix("안절부절하는 그를 봤다") == "안절부절못하는 그를 봤다"
    # 띄어 쓴 원문도 한 낱말로 모은다('안절부절못하다'는 한 단어다).
    assert _fix("안절부절 했다") == "안절부절못했다"


def test_leaves_registered_adverb_hada_alone():
    """`부사+하다`가 표제어면 건드리지 않는다 — 코퍼스에서 걸린 '잘'·'그만'·'더'·
    '우당탕'이 전부 이 경우다(2026-08-04 실측)."""
    assert _fix("잘했다고 말했다") == "잘했다고 말했다"
    assert _fix("그만하자") == "그만하자"
    assert _fix("더 했다") == "더 했다"
    assert _fix("우당탕하는 소리") == "우당탕하는 소리"
    assert _fix("깜빡했다") == "깜빡했다"


def test_leaves_correct_form_and_unrelated_context_alone():
    assert _fix("안절부절못했다") == "안절부절못했다"
    # '하다'가 뒤따르지 않으면 부사 그대로다.
    assert _fix("그는 안절부절 어쩔 줄 몰랐다") == "그는 안절부절 어쩔 줄 몰랐다"


def test_applied_log_survives_edit_guard():
    """로그를 어절 단위로 남긴다 — edit_guard가 이 로그로 결과를 재구성해 검증하므로
    조각만 남기면 정당한 교정이 fail-closed로 막힌다."""
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000",
                          text="그는 안절부절했다", speaker=None)
    corrected, _flags, log = correct_entries([entry], None, None)
    assert corrected[0].text == "그는 안절부절못했다"  # 관문을 통과했다
    assert any("안절부절했다 -> 안절부절못했다" in n.message for n in log if n.is_edit)
    assert not any("붙임 불가" in n.message or "폐기" in n.message for n in log)
