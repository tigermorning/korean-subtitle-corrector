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
