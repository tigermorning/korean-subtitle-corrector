"""자막 구두점 규칙 회귀 테스트 (사용자 지정 2026-08-02).

자막 모드에서만 적용되는 규칙 세 가지를 고정한다.
  1. 각 행 끝의 문장 종결 마침표는 생략한다.
  2. 행 중간 문장 사이의 마침표는 쉼표로 대체한다.
  3. 말줄임표는 온점 세 개(...)로 표기한다.

세 규칙 모두 자막 관례상 정답이 하나뿐이라 자동 교정이다(확인 플래그가 아니다).
일반 글 모드는 구두점을 그대로 두므로 하나도 적용되지 않는다 — 이 대비가
"사용 목적을 자막으로 고른 경우에 한해"라는 조건의 실질이다.

correct_subtitle_* 단위 테스트는 사전 API를 쓰지 않아 네트워크가 필요 없다.
파이프라인 연동 테스트만 correct_entries를 거친다.
"""

from subtitle_corrector.engine import (
    correct_entries,
    normalize_punctuation_style,
    correct_subtitle_ellipsis,
    correct_subtitle_final_period,
    correct_subtitle_internal_period,
)
from subtitle_corrector.parsers import SubtitleEntry


class TestFinalPeriod:
    def test_removed_at_line_end(self):
        assert correct_subtitle_final_period("안녕하세요.")[0] == "안녕하세요"

    def test_removed_on_every_line(self):
        assert correct_subtitle_final_period("첫 줄.\n둘째 줄.")[0] == "첫 줄\n둘째 줄"

    def test_decimal_point_untouched(self):
        assert correct_subtitle_final_period("원주율은 3.14")[0] == "원주율은 3.14"

    def test_ellipsis_untouched(self):
        assert correct_subtitle_final_period("글쎄...")[0] == "글쎄..."


class TestInternalPeriod:
    def test_replaced_with_comma(self):
        assert correct_subtitle_internal_period("네. 그래")[0] == "네, 그래"

    def test_multiple_in_one_line(self):
        assert correct_subtitle_internal_period("안녕. 반가워. 또 봐")[0] == "안녕, 반가워, 또 봐"

    def test_line_final_period_left_to_the_other_rule(self):
        """줄 끝 마침표는 이 함수가 건드리지 않는다(제거는 다른 규칙의 몫)."""
        assert correct_subtitle_internal_period("안녕하세요.")[0] == "안녕하세요."

    def test_decimal_point_untouched(self):
        assert correct_subtitle_internal_period("원주율은 3.14 정도다")[0] == "원주율은 3.14 정도다"

    def test_ellipsis_untouched(self):
        assert correct_subtitle_internal_period("글쎄... 모르겠어")[0] == "글쎄... 모르겠어"


class TestEllipsis:
    def test_ellipsis_char_becomes_three_dots(self):
        assert correct_subtitle_ellipsis("글쎄…")[0] == "글쎄..."

    def test_repeated_ellipsis_chars_collapse(self):
        assert correct_subtitle_ellipsis("글쎄……")[0] == "글쎄..."

    def test_six_dots_become_three(self):
        assert correct_subtitle_ellipsis("글쎄......")[0] == "글쎄..."

    def test_three_dots_unchanged(self):
        assert correct_subtitle_ellipsis("글쎄...") == ("글쎄...", [])

    def test_single_and_double_dots_untouched(self):
        """온점 하나는 마침표이고, 둘은 말줄임표로 단정할 근거가 없다."""
        assert correct_subtitle_ellipsis("끝.") == ("끝.", [])
        assert correct_subtitle_ellipsis("기다려.. 잠깐") == ("기다려.. 잠깐", [])

    def test_decimal_point_untouched(self):
        assert correct_subtitle_ellipsis("3.14") == ("3.14", [])


class TestInPipeline:
    def _run(self, text, doc_type="subtitle"):
        corrected, flags, log = correct_entries(
            [SubtitleEntry(index=1, start="", end="", text=text)], doc_type=doc_type
        )
        return corrected[0].text, flags, log

    def test_two_sentences_fully_normalized(self):
        """중간 마침표는 쉼표로, 끝 마침표는 제거 — 한 번에 정리된다."""
        text, _flags, _log = self._run("보여 주세요. 궁금해요.")
        assert text == "보여 주세요, 궁금해요"

    def test_no_comma_flag_remains(self):
        """자동 교정으로 승격했으므로 같은 내용을 플래그로 또 묻지 않는다."""
        _text, flags, _log = self._run("네. 그래.")
        assert not any("쉼표" in f.reason for f in flags)

    def test_ellipsis_normalized_in_pipeline(self):
        text, _flags, log = self._run("글쎄…")
        assert text == "글쎄..."
        assert any("말줄임표" in line for line in log)

    def test_prose_mode_keeps_all_punctuation(self):
        text, _flags, _log = self._run("보여 주세요. 궁금해요…", doc_type="prose")
        assert text == "보여 주세요. 궁금해요…"


class TestPunctuationStyle:
    """말줄임표·따옴표 표기 방식 선택 (사용자 지정 2026-08-02).

    어문 규범이 하나로 정해 주지 않고 납품처마다 다르다. 기본값은 온점 세 개와
    곧은따옴표 — 자막 편집기·플레이어 호환이 가장 넓다.
    """

    def _run(self, text, style=None):
        corrected, _flags, log = correct_entries(
            [SubtitleEntry(index=1, start="", end="", text=text)], style=style
        )
        return corrected[0].text, log

    def test_default_is_dots_and_straight_quotes(self):
        assert self._run("글쎄…")[0] == "글쎄..."
        assert self._run("그가 “안녕”이라 했다")[0] == ' 그가 "안녕"이라 했다'.strip()

    def test_char_style_collapses_dots(self):
        style = normalize_punctuation_style("char", "half")
        assert self._run("글쎄...", style)[0] == "글쎄…"
        assert self._run("글쎄......", style)[0] == "글쎄…"

    def test_full_quote_style(self):
        style = normalize_punctuation_style("dots", "full")
        assert self._run('그가 "안녕"이라 했다', style)[0] == "그가 “안녕”이라 했다"

    def test_opening_or_closing_decided_by_previous_character(self):
        """여는 쪽인지 닫는 쪽인지는 앞 글자로 정한다 — 표기 관례 그대로다."""
        style = normalize_punctuation_style("dots", "full")
        assert self._run('"시작"과 끝', style)[0] == "“시작”과 끝"

    def test_unknown_value_falls_back_to_default(self):
        style = normalize_punctuation_style("이상한값", "")
        assert (style.ellipsis, style.quotes) == ("dots", "half")

    def test_not_applied_in_prose_mode(self):
        corrected, _flags, _log = correct_entries(
            [SubtitleEntry(index=1, start="", end="", text="글쎄…")], doc_type="prose"
        )
        assert corrected[0].text == "글쎄…"


class TestSpeakerInheritance:
    """화자명이 없는 줄은 직전 화자가 계속 말하는 것으로 본다(사용자 지정 2026-08-02)."""

    def _entries(self):
        return [
            SubtitleEntry(index=1, start="", end="", text="[달래] 밥은 묵었는가", speaker="달래"),
            SubtitleEntry(index=2, start="", end="", text="얼른 오라고 혀라", speaker=None),
            SubtitleEntry(index=3, start="", end="", text="[문 여는 소리]", speaker=None),
            SubtitleEntry(index=4, start="", end="", text="뭣이 그리 급하당가", speaker=None),
        ]

    def test_speaker_carries_over(self):
        corrected, _f, _l = correct_entries(self._entries())
        assert [e.speaker for e in corrected] == ["달래", "달래", None, "달래"]

    def test_marker_only_line_has_no_speaker(self):
        """효과음·지문처럼 대사가 없는 줄은 누구의 말도 아니다."""
        corrected, _f, _l = correct_entries(self._entries())
        assert corrected[2].speaker is None

    def test_inheritance_applies_dialect_setting(self):
        """승계가 없으면 같은 화자의 대사인데 첫 줄만 보호된다."""
        corrected, _f, _l = correct_entries(
            self._entries(), dialect_map={"달래": "전라도"}, dialect_modes={"달래": "protect"}
        )
        assert [e.text for e in corrected] == [
            "[달래] 밥은 묵었는가", "얼른 오라고 혀라", "[문 여는 소리]", "뭣이 그리 급하당가",
        ]

    def test_not_applied_in_prose_mode(self):
        entries = [
            SubtitleEntry(index=1, start="", end="", text="[달래] 안녕", speaker="달래"),
            SubtitleEntry(index=2, start="", end="", text="또 만나", speaker=None),
        ]
        corrected, _f, _l = correct_entries(entries, doc_type="prose")
        assert corrected[1].speaker is None
