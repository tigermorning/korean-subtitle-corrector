"""한글 맞춤법 제42항 의존명사(들/뿐/만/지/차/판)의 정답표 회귀 테스트.

판정 규칙과 근거는 `docs/GRAMMAR_PRECEDENTS_TABLE.md`, 구현 경위는 §69.
인용한 온라인가나다 답변은 2026-08-05에 다시 열어 살아 있는지 확인했다.

**맞게 쓴 문장을 건드리지 않는 것이 이 표의 절반**이다 — 이 여섯 낱말은 같은 글자가
조사·접미사·어미로도 쓰여, 규칙이 한쪽으로 쏠리면 바로 오교정이 된다.
"""
from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import SubtitleEntry


def _run(text: str):
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text)
    corrected, flags, _log = correct_entries([entry], None, None)
    return corrected[0].text, [f.suggested_fix for f in flags if f.suggested_fix]


class TestBun:
    """'뿐' — 체언 뒤면 조사(붙임), 관형사형 어미 뒤면 의존명사(띄움).
    앞말의 품사가 정답을 정하므로 자동 교정한다(qna_seq=310591)."""

    def test_after_body_word_is_joined(self):
        assert _run("남은 건 너 뿐이야")[0] == "남은 건 너뿐이야"

    def test_after_adnominal_ending_is_spaced(self):
        assert _run("그냥 웃을뿐이다")[0] == "그냥 웃을 뿐이다"

    def test_correct_spellings_are_untouched(self):
        for text in ("너뿐이야", "믿을 건 실력뿐이었다", "학생이 셋뿐이야",
                     "그냥 웃을 뿐이다", "소문으로 들었을 뿐이네"):
            assert _run(text)[0] == text


class TestCha:
    """'차' — 기간 명사구 뒤는 의존명사(띄움, qna_seq=309642), 명사 뒤 '목적'은
    접미사(붙임, qna_seq=319170), 관형사형 뒤는 의존명사(띄움)."""

    def test_duration_phrase_is_spaced(self):
        assert _run("입사 3년차입니다")[0] == "입사 3년 차입니다"

    def test_purpose_suffix_is_flagged_not_joined(self):
        """붙임 방향은 자동 교정하지 않는다 — 가르는 신호가 kiwi 태그뿐이라
        茶·車를 잘못 붙일 위험이 남는다."""
        out, suggestions = _run("인사 차 들렀습니다")
        assert out == "인사 차 들렀습니다"
        assert "인사차 들렀습니다" in suggestions

    def test_drink_and_vehicle_readings_are_untouched(self):
        for text in ("회사 차 타고 가자", "따뜻한 차 한 잔", "커피랑 차 좀 내와"):
            out, suggestions = _run(text)
            assert out == text
            assert not [s for s in suggestions if "차" in s and " 차" not in s]

    def test_correct_spellings_are_untouched(self):
        for text in ("인사차 들렀습니다", "사업차 서울에 왔어요",
                     "고향에 갔던 차에 들렀어", "입사 3년 차입니다", "임신 8주 차예요"):
            assert _run(text)[0] == text


class TestPan:
    """'판' — 승부를 세는 단위면 띄우고(수 관형사+의존명사), 어휘화된 '한판'이면
    붙인다. 표기만으로 갈리지 않아 플래그만 남긴다(qna_seq=326715)."""

    def test_counting_reading_is_flagged(self):
        out, suggestions = _run("한판 더 하자")
        assert out == "한판 더 하자"
        assert "한 판 더 하자" in suggestions

    def test_lexicalized_compound_is_untouched(self):
        out, suggestions = _run("한판 잔치를 벌였다")
        assert out == "한판 잔치를 벌였다"
        assert "한 판 잔치를 벌였다" not in suggestions

    def test_already_spaced_is_untouched(self):
        assert _run("한 판 더 하자")[0] == "한 판 더 하자"


class TestAlreadyCoveredByExistingRules:
    """'만'·'지'·'들'은 기존 규칙과 kiwi가 이미 처리한다 — 새로 만들지 않았다는
    사실을 고정한다(2026-08-05 실측). 여기가 깨지면 §69의 "구현하지 않음" 판단
    자체를 다시 봐야 한다."""

    def test_man_duration_is_suggested(self):
        assert "십 년 만의 귀국이다" in _run("십 년만의 귀국이다")[1]

    def test_ji_duration_is_suggested(self):
        assert "떠난 지 삼 년이 됐다" in _run("떠난지 삼 년이 됐다")[1]

    def test_deul_plural_suffix_is_joined(self):
        assert _run("사람 들이 모였다")[0] == "사람들이 모였다"

    def test_man_and_ji_endings_are_untouched(self):
        for text in ("잠만 자다 왔어", "눈만 감으면 보여",
                     "얼마나 지난지 모르겠지만", "큰지 작은지 모르겠다",
                     "세 번 만에 합격했다", "그 사람 만난 지 오래됐어",
                     "사과, 배, 감 들을 먹었다"):
            assert _run(text)[0] == text
