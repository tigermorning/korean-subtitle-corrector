"""자막 편집 표지 회귀 테스트 (사용자 지정 2026-08-02).

자막에는 어문 규범의 대상이 아닌 **기술적 표지**가 섞인다 — 화면자막 표기,
줄바꿈 표기, 자막 위치 표기. 업계 공통 규칙이 없어 작업자·편집기마다 값이 달라서
하드코딩하지 않고 설정으로 받는다. 지정된 표지는 교정에서 제외한다.

  - 화면자막: 짝이 있는 문자면 감싸인 구간만, 짝이 없는 문자면 그 줄 전체
  - 줄바꿈: 교정할 때만 실제 줄바꿈으로 취급하고 결과에는 표지를 되돌림
  - 위치: 제어 코드라 통째로 보호

correct_entries가 사전 API를 호출하므로 네트워크가 필요하다.
"""

from subtitle_corrector.engine import correct_entries, normalize_subtitle_markers
from subtitle_corrector.parsers import SubtitleEntry


def _run(text, markers=None, doc_type="subtitle"):
    corrected, flags, log = correct_entries(
        [SubtitleEntry(index=1, start="", end="", text=text)],
        doc_type=doc_type,
        markers=markers,
    )
    return corrected[0].text, flags, log


QUOTE = normalize_subtitle_markers('"', "|", "{\\an8}")
AT = normalize_subtitle_markers("@", "|", "{\\an8}")


class TestNormalize:
    def test_blank_values_are_unset(self):
        """공백만 있는 값이 표지로 인정되면 문서 전체가 보호 구간이 된다."""
        markers = normalize_subtitle_markers("  ", "", None)
        assert not markers.any_set

    def test_values_are_trimmed(self):
        markers = normalize_subtitle_markers(' " ', " | ", " {\\an8} ")
        assert (markers.screen_text, markers.line_break, markers.position) == (
            '"', "|", "{\\an8}",
        )


class TestScreenTextMarker:
    def test_paired_marker_protects_only_the_span(self):
        text = '그 표지판엔 "초코렛. 세일중"이라고 써 있었다.'
        out, _flags, _log = _run(text, QUOTE)
        assert '"초코렛. 세일중"' in out  # 감싸인 구간은 그대로
        assert out.endswith("있었다")  # 바깥의 줄 끝 마침표는 제거

    def test_unpaired_marker_protects_the_whole_line(self):
        out, _flags, log = _run("@초코렛. 세일중", AT)
        assert out == "@초코렛. 세일중"
        assert log == []

    def test_without_marker_the_same_text_is_corrected(self):
        """표지를 지정하지 않으면 예전처럼 전부 교정한다(회귀 확인)."""
        out, _flags, _log = _run("@초코렛. 세일중")
        assert "초콜릿" in out

    def test_unclosed_paired_marker_protects_to_line_end(self):
        """열고 안 닫은 경우 그 뒤는 화면자막일 가능성이 높아 교정하지 않는다."""
        out, _flags, _log = _run('간판엔 "초코렛 세일중', QUOTE)
        assert "초코렛" in out


class TestLineBreakMarker:
    def test_treated_as_real_line_break(self):
        """표지 앞의 마침표도 '줄 끝'이므로 제거된다."""
        out, _flags, _log = _run("안녕하세요.|반갑습니다.", QUOTE)
        assert out == "안녕하세요|반갑습니다"

    def test_marker_is_restored(self):
        out, _flags, _log = _run("초코렛 좋아.|리모콘 어디 있어.", QUOTE)
        assert out == "초콜릿 좋아|리모컨 어디 있어"

    def test_without_marker_period_before_it_is_not_line_final(self):
        """표지를 지정하지 않으면 '|' 앞 마침표는 줄 끝이 아니라 그대로 남는다."""
        out, _flags, _log = _run("안녕하세요.|반갑습니다.")
        assert out == "안녕하세요.|반갑습니다"


class TestPositionMarker:
    def test_control_code_is_protected(self):
        out, _flags, _log = _run("{\\an8}안녕하세요.", QUOTE)
        assert out == "{\\an8}안녕하세요"

    def test_text_after_marker_is_still_corrected(self):
        out, _flags, _log = _run("{\\an8}초코렛 좋아", QUOTE)
        assert out == "{\\an8}초콜릿 좋아"


class TestScope:
    def test_markers_ignored_in_prose_mode(self):
        """표지는 자막 편집 관례라 일반 글에는 적용하지 않는다."""
        out, _flags, _log = _run("@초코렛 좋아", AT, doc_type="prose")
        assert "초콜릿" in out

    def test_flag_suggestion_covers_the_whole_line(self):
        """구간 단위로 교정하더라도 제안은 줄 전체여야 한다 — 조각으로 남으면
        apply-report가 그 조각으로 줄 전체를 덮어써 나머지 대사를 지운다."""
        text = '간판엔 "SALE"이라고 써 있었고 턱 밑이 간지러웠다'
        _out, flags, _log = _run(text, QUOTE)
        for f in flags:
            if f.suggested_fix:
                assert '"SALE"' in f.suggested_fix


class TestSpeakerToneBrackets:
    """화자명·어조 표기 부호. OTT마다 대괄호와 괄호가 갈려 설정으로 받는다."""

    def test_default_is_square_bracket(self):
        """기본값을 바꾸면 기존 사용자의 결과가 달라진다 — 대괄호를 유지한다."""
        out, _flags, _log = _run("[민수]안녕하세요")
        assert out == "[민수] 안녕하세요"

    def test_configured_paren_gets_the_space(self):
        markers = normalize_subtitle_markers(speaker="(")
        out, _flags, _log = _run("(민수)안녕하세요", markers)
        assert out == "(민수) 안녕하세요"

    def test_unconfigured_bracket_is_left_alone(self):
        """대괄호만 쓰는 원고에서 괄호까지 건드리면 정당한 표기를 망친다."""
        out, _flags, _log = _run("(민수)안녕하세요")
        assert out == "(민수)안녕하세요"

    def test_single_char_input_infers_the_pair(self):
        assert normalize_subtitle_markers(speaker="(").speaker == "()"
        assert normalize_subtitle_markers(speaker="()").speaker == "()"

    def test_unpaired_char_falls_back_to_default(self):
        """짝이 없는 문자는 어디까지가 화자명인지 정할 수 없다."""
        assert normalize_subtitle_markers(speaker="@").speaker == "[]"

    def test_tone_bracket_also_applies(self):
        markers = normalize_subtitle_markers(tone="(")
        out, _flags, _log = _run("(웃으며)좋아", markers)
        assert out == "(웃으며) 좋아"

    def test_both_brackets_can_differ(self):
        markers = normalize_subtitle_markers(speaker="[", tone="(")
        assert markers.tag_closers == ("]", ")")


class TestQuotedCommandComma:
    """'말라 그래'는 '말라고 해'의 준말이라 '그래'가 감탄사가 아니다.

    2026-08-02 실사용에서 '지랄하시지 말라 그래.'가 '지랄하시지 말라, 그래'로
    잘못 교정된 것을 사용자가 발견해 고쳤다.
    """

    def test_quoted_command_gets_no_comma(self):
        out, _flags, _log = _run("지랄하시지 말라 그래.")
        assert out == "지랄하시지 말라 그래"

    def test_other_quoted_endings(self):
        assert _run("오지 말라 그래")[0] == "오지 말라 그래"
        assert _run("먹자 그래.")[0] == "먹자 그래"

    def test_real_interjection_still_gets_comma(self):
        """감탄사 규칙 자체는 그대로 살아 있어야 한다(회귀 확인)."""
        assert _run("아이고 어떻기는")[0] == "아이고, 어떻기는"
        assert _run("싫다면 뭐.")[0] == "싫다면, 뭐"
        assert _run("먹어 준희야.")[0] == "먹어, 준희야"
