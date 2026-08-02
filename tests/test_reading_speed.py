"""자막 읽기 속도(CPS) 회귀 테스트.

어문 규범이 아니라 **사람이 글을 읽는 속도**라는 물리적 제약이다. 글자 수 상한이
배급사마다 갈리는 것과 달리 이 값은 크게 벌어지지 않는다 — 성인 17자/초, 아동물
13자/초가 널리 쓰이고 20자/초를 넘으면 사실상 읽을 수 없다고 본다.

자동으로 고치지 않는다. 해결책은 표현을 줄이거나(번역을 고치는 일) 표시 시간을
늘리는 것(타임코드를 고치는 일)이라 둘 다 사람 몫이다.

사전 API를 쓰지 않으므로 check_reading_speed 단위 테스트는 네트워크가 필요 없다.
"""

from subtitle_corrector.engine import (
    check_reading_speed,
    correct_entries,
    normalize_subtitle_markers,
)
from subtitle_corrector.parsers import SubtitleEntry


def _check(text, start="00:00:01,000", end="00:00:03,000", **kwargs):
    return check_reading_speed(1, text, start, end, **kwargs)


class TestCheckReadingSpeed:
    def test_within_limit_returns_none(self):
        # 2초에 20자 = 10자/초
        assert _check("가" * 20) is None

    def test_exactly_at_limit_is_not_flagged(self):
        """상한은 '초과'부터 문제다 — 딱 맞는 자막까지 잡으면 오탐이 된다."""
        assert _check("가" * 34) is None  # 2초에 34자 = 17.0자/초

    def test_over_limit_is_flagged(self):
        flag = _check("가" * 40)  # 2초에 40자 = 20.0자/초
        assert flag is not None
        assert "20.0자/초" in flag.reason
        assert "40자" in flag.reason

    def test_no_suggested_fix(self):
        """표현을 줄일지 시간을 늘릴지는 사람이 정한다."""
        assert not _check("가" * 40).suggested_fix

    def test_custom_limit(self):
        """아동물은 13자/초를 쓴다."""
        assert _check("가" * 30, max_cps=13) is not None  # 15자/초
        assert _check("가" * 30, max_cps=17) is None

    def test_zero_disables(self):
        assert _check("가" * 200, max_cps=0) is None

    def test_missing_timecode_skips(self):
        """일반 텍스트에는 타임코드가 없다 — 계산할 근거가 없으면 검사하지 않는다."""
        assert _check("가" * 200, start="", end="") is None
        assert _check("가" * 200, start="이상한 값", end="00:00:03,000") is None

    def test_zero_or_negative_duration_skips(self):
        assert _check("가" * 200, start="00:00:03,000", end="00:00:03,000") is None
        assert _check("가" * 200, start="00:00:05,000", end="00:00:03,000") is None

    def test_spaces_are_counted(self):
        """공백도 화면에서 자리를 차지하고 읽는 시간에 들어간다(업계 CPS 계산과 동일)."""
        assert _check("가 " * 18) is not None  # 36자 / 2초 = 18자/초

    def test_line_break_not_counted(self):
        """줄바꿈은 글자가 아니다."""
        assert _check("가" * 17 + "\n" + "가" * 17) is None  # 34자 = 17.0자/초

    def test_editing_markers_excluded(self):
        """줄바꿈 표기·자막 위치 표기는 편집용 기호라 화면에 보이지 않는다."""
        markers = normalize_subtitle_markers(line_break="|", position="{\\an8}")
        text = "{\\an8}" + "가" * 17 + "|" + "가" * 17
        assert check_reading_speed(1, text, "00:00:01,000", "00:00:03,000", markers=markers) is None
        # 표지를 지정하지 않으면 그 기호들도 글자로 세어 상한을 넘는다
        assert check_reading_speed(1, text, "00:00:01,000", "00:00:03,000") is not None

    def test_speaker_label_is_counted(self):
        """SDH의 화자명은 화면에 실제로 나오므로 읽는 시간에 포함된다."""
        flag = _check("[민수] " + "가" * 30)  # 36자 / 2초 = 18자/초
        assert flag is not None


class TestInPipeline:
    def _entry(self, text, start="00:00:01,000", end="00:00:03,000"):
        return [SubtitleEntry(index=1, start=start, end=end, text=text)]

    def test_flagged_in_subtitle_mode(self):
        _c, flags, _l = correct_entries(self._entry("가" * 40))
        assert any("읽기 속도 초과" in f.reason for f in flags)

    def test_not_checked_in_prose_mode(self):
        _c, flags, _l = correct_entries(self._entry("가" * 40), doc_type="prose")
        assert not any("읽기 속도 초과" in f.reason for f in flags)

    def test_disabled_by_zero(self):
        _c, flags, _l = correct_entries(self._entry("가" * 40), max_cps=0)
        assert not any("읽기 속도 초과" in f.reason for f in flags)

    def test_plain_text_entries_unaffected(self):
        """타임코드가 없는 일반 텍스트 입력에서는 조용히 건너뛴다."""
        _c, flags, _l = correct_entries(self._entry("가" * 40, start="", end=""))
        assert not any("읽기 속도 초과" in f.reason for f in flags)


class TestLineLength:
    """한 줄 글자 수 상한(사용자 지정 2026-08-02).

    읽기 속도와 달리 이 상한은 매체·배급사마다 달라 기본값을 두지 않는다.
    사용자가 값을 넣을 때만 검사한다.
    """

    def _entry(self, text):
        return [SubtitleEntry(index=1, start="00:00:01,000", end="00:00:09,000", text=text)]

    def test_not_checked_by_default(self):
        _c, flags, _l = correct_entries(self._entry("가" * 50))
        assert not any("한 줄 글자 수" in f.reason for f in flags)

    def test_flagged_over_user_limit(self):
        _c, flags, _l = correct_entries(self._entry("가" * 20), max_line_chars=16)
        assert any("1번째 줄 20자" in f.reason or "한 줄 20자" in f.reason for f in flags)

    def test_exactly_at_limit_is_not_flagged(self):
        _c, flags, _l = correct_entries(self._entry("가" * 16), max_line_chars=16)
        assert not any("한 줄 글자 수" in f.reason for f in flags)

    def test_each_line_checked_separately(self):
        _c, flags, _l = correct_entries(self._entry("가" * 20 + "\n" + "나" * 5), max_line_chars=16)
        reasons = [f.reason for f in flags if "한 줄 글자 수" in f.reason]
        assert len(reasons) == 1
        assert "1번째 줄" in reasons[0] and "2번째" not in reasons[0]

    def test_line_break_marker_counts_as_a_line_boundary(self):
        markers = normalize_subtitle_markers(line_break="|")
        _c, flags, _l = correct_entries(
            self._entry("가" * 20 + "|" + "나" * 5), markers=markers, max_line_chars=16
        )
        assert any("1번째 줄 20자" in f.reason for f in flags)

    def test_not_checked_in_prose_mode(self):
        _c, flags, _l = correct_entries(
            self._entry("가" * 50), doc_type="prose", max_line_chars=16
        )
        assert not any("한 줄 글자 수" in f.reason for f in flags)
