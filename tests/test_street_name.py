"""도로명 '대로/로/가'를 띄어 쓴 표기를 확인 플래그한다(`docs/BACKLOG.md` 16번, §65).

16번의 질문은 "띄어 쓴 표기 자체를 플래그할지"였고, 걸림돌은 일반명사 '대로'(大路,
크고 넓은 길)와 구분할 방법이었다. **앞말이 고유명사(NNP)인지로 가른다** — 사전으로는
가를 수 없다(`종로`·`충무로`·`을지로`는 표제어인데 `세종대로`·`테헤란로`·`강남대로`는
미등재). 자동 교정은 하지 않는다. 실시간 사전 API를 호출한다.
"""
from subtitle_corrector.engine import check_street_name_spacing, correct_entries
from subtitle_corrector.parsers import SubtitleEntry


def _flag(text):
    return check_street_name_spacing(1, text)


def test_proper_noun_before_suffix_is_flagged():
    for text, suggested in (
        ("세종 대로에서 만나", "세종대로에서 만나"),
        ("테헤란 로에서 봐", "테헤란로에서 봐"),
        ("충무 로에 갔다", "충무로에 갔다"),
    ):
        flag = _flag(text)
        assert flag is not None, text
        assert flag.suggested_fix == suggested
        assert "도로명" in flag.reason


def test_evidence_says_whether_the_joined_form_is_a_headword():
    assert "사전 표제어입니다" in _flag("충무 로에 갔다").reason  # 충무로는 등재
    assert "사전에 없지만" in _flag("세종 대로에서 만나").reason  # 세종대로는 미등재


def test_common_noun_and_dependent_noun_are_not_flagged():
    assert _flag("왕복 8차선 대로") is None  # 일반명사 '대로'(大路)
    assert _flag("말한 대로 하면 된다") is None  # 의존명사 '대로'
    assert _flag("네 뜻대로 하자") is None
    assert _flag("서울로 갔다") is None  # '로'는 조사
    assert _flag("세종대로에서 만나") is None  # 이미 붙여 썼다


def test_single_letter_ga_needs_dictionary_evidence():
    """한 글자 '가'는 뜻이 많아(街·價·家) 붙임형이 표제어일 때만 묻는다."""
    assert _flag("명동 가에서") is None


def test_text_is_never_changed():
    for text in ("세종 대로에서 만나", "충무 로에 갔다"):
        entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000",
                              text=text, speaker=None)
        corrected, flags, _log = correct_entries([entry], None, None)
        assert corrected[0].text == text
        assert any("도로명" in f.reason for f in flags)
