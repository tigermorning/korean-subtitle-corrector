"""사투리 처리 3-모드(protect / assist / to_standard) 회귀 테스트.

PRD.md §12 "사투리 처리 원칙"의 재설계(2026-07-25)를 실행 가능한 형태로
고정한다. 핵심 불변식:
  - protect(지정 화자 기본값): 대사를 완전히 그대로 둔다. 표준화 교정도,
    어떤 플래그도 없다. 대본 속 사투리는 대부분 작가의 의도이기 때문이다.
  - assist: 텍스트는 그대로, 표준어→사투리 제안 플래그만 남긴다.
  - to_standard: 사투리→표준어 변환 후 표준화 파이프라인을 적용한다.

resolve/normalize 및 protect/assist는 정적 데이터만 쓰므로 네트워크가
필요 없다. to_standard는 correct_entries 파이프라인이 사전 API를 호출하므로
네트워크가 필요하다(이 프로젝트의 다른 통합 테스트와 동일).
"""

from subtitle_corrector.engine import (
    correct_entries,
    normalize_dialect_mode,
    resolve_dialect_mode,
)
from subtitle_corrector.parsers import SubtitleEntry


def _entry(index, text, speaker="민수"):
    return SubtitleEntry(
        index=index, start="00:00:01,000", end="00:00:04,000",
        text=text, speaker=speaker,
    )


class TestNormalizeDialectMode:
    def test_empty_defaults_to_protect(self):
        assert normalize_dialect_mode("") == "protect"
        assert normalize_dialect_mode(None) == "protect"

    def test_valid_modes_pass_through(self):
        assert normalize_dialect_mode("protect") == "protect"
        assert normalize_dialect_mode("assist") == "assist"
        assert normalize_dialect_mode("to_standard") == "to_standard"

    def test_backward_compat_aliases(self):
        # 옛 기본값 flag_only(사투리를 의심스러운 것으로 플래그) → protect
        assert normalize_dialect_mode("flag_only") == "protect"
        # 옛 자동 재작성 to_dialect → assist
        assert normalize_dialect_mode("to_dialect") == "assist"

    def test_unknown_mode_falls_back_to_protect(self):
        assert normalize_dialect_mode("garbage") == "protect"


class TestResolveDialectMode:
    def test_unassigned_speaker_returns_none(self):
        assert resolve_dialect_mode("민수", {}, {}) == (None, None)
        assert resolve_dialect_mode(None, None, None) == (None, None)

    def test_assigned_speaker_defaults_to_protect(self):
        assert resolve_dialect_mode("민수", {"민수": "경상도"}, {}) == ("경상도", "protect")

    def test_assigned_speaker_explicit_mode(self):
        assert resolve_dialect_mode(
            "민수", {"민수": "경상도"}, {"민수": "assist"}
        ) == ("경상도", "assist")

    def test_assigned_speaker_alias_normalized(self):
        assert resolve_dialect_mode(
            "민수", {"민수": "경상도"}, {"민수": "to_dialect"}
        ) == ("경상도", "assist")


class TestProtectMode:
    """protect: 대사를 완전히 그대로 둔다 — 어떤 교정도, 어떤 플래그도 없다."""

    def test_dialect_line_left_untouched_and_no_flags(self):
        entries = [_entry(1, "이거 아이가 마이시 좋다")]
        corrected, flags, applied = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "protect"},
        )
        assert corrected[0].text == "이거 아이가 마이시 좋다"
        assert flags == []
        assert applied == []

    def test_protect_is_default_without_explicit_mode(self):
        entries = [_entry(1, "이거 아이가 마이시 좋다")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={},
        )
        assert corrected[0].text == "이거 아이가 마이시 좋다"
        assert flags == []

    def test_flag_only_alias_behaves_as_protect(self):
        entries = [_entry(1, "이거 아이가 마이시 좋다")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "flag_only"},
        )
        assert corrected[0].text == "이거 아이가 마이시 좋다"
        assert flags == []


class TestAssistMode:
    """assist: 텍스트는 그대로, 표준어→사투리 제안 플래그만 남긴다."""

    def test_standard_line_gets_dialect_suggestion(self):
        entries = [_entry(1, "그래 많이 좋아")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "assist"},
        )
        # 텍스트는 절대 바뀌지 않는다
        assert corrected[0].text == "그래 많이 좋아"
        # 표준어→사투리 제안 플래그가 나온다
        assert len(flags) == 1
        assert flags[0].line_index == 1
        assert flags[0].suggested_fix == "아이가 마이시 좋아"
        assert "제안" in flags[0].reason

    def test_already_dialect_line_emits_no_suggestion(self):
        # convert_dialect(to_dialect)가 바꿀 게 없고 search_dialect도 비면 플래그 없음
        entries = [_entry(1, "이거 아이가 마이시 좋다")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "assist"},
        )
        assert corrected[0].text == "이거 아이가 마이시 좋다"
        assert all(f.suggested_fix != f.original_text for f in flags)
        # 이 줄에 대해 표준화 교정은 일어나지 않는다
        assert corrected[0].text == entries[0].text

    def test_to_dialect_alias_behaves_as_assist(self):
        entries = [_entry(1, "그래 많이 좋아")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "to_dialect"},
        )
        assert corrected[0].text == "그래 많이 좋아"
        assert any(f.suggested_fix == "아이가 마이시 좋아" for f in flags)


class TestToStandardMode:
    """to_standard: 사투리→표준어 변환 후 표준화 파이프라인 적용 (네트워크 필요)."""

    def test_dialect_line_converted_to_standard(self):
        entries = [_entry(1, "이거 아이가 마이시 좋다")]
        corrected, flags, applied = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "to_standard"},
        )
        # 사투리 어휘가 표준어로 바뀌었다
        assert "아이가" not in corrected[0].text
        assert "마이시" not in corrected[0].text
        assert "그래" in corrected[0].text
        assert "많이" in corrected[0].text
        # 변환 확인 플래그가 나온다
        assert any("사투리→표준어" in f.reason for f in flags)
        assert any("사투리→표준어 변환" in a for a in applied)
