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


class TestDocumentLevelDialect:
    """문서 전체 사투리 설정 — 화자 표기가 없는 일반 글(소설 등)용.

    화자별 지정이 우선이고, 없는 줄에만 문서 전체 설정이 적용된다.
    """

    def test_document_setting_applies_to_speakerless_line(self):
        assert resolve_dialect_mode(
            None, None, None, "경상도", "to_standard"
        ) == ("경상도", "to_standard")

    def test_document_mode_defaults_to_protect(self):
        """모드를 안 주면 보호 — 글 전체를 말없이 표준어로 바꿔 버리면 안 된다."""
        assert resolve_dialect_mode(None, None, None, "전라도") == ("전라도", "protect")

    def test_speaker_setting_wins_over_document(self):
        assert resolve_dialect_mode(
            "민수", {"민수": "제주도"}, {"민수": "assist"}, "경상도", "to_standard"
        ) == ("제주도", "assist")

    def test_document_setting_applies_to_unassigned_speaker(self):
        """화자 이름은 있지만 화자별 지정이 없는 줄도 문서 전체 설정을 따른다."""
        assert resolve_dialect_mode(
            "영희", {"민수": "제주도"}, {}, "충청도", "assist"
        ) == ("충청도", "assist")

    def test_no_document_setting_keeps_previous_behavior(self):
        assert resolve_dialect_mode("영희", {"민수": "제주도"}, {}) == (None, None)

    def test_prose_document_to_standard_suggests_without_changing_text(self):
        """화자 표기가 없는 일반 글도 문서 전체 설정만으로 사투리 처리가 걸린다.
        다만 2026-08-03부터 to_standard는 **자동 변환이 아니라 제안**이다
        (`dictionary/dialect.py` "사투리 표 감사")."""
        corrected, flags, applied_log = correct_entries(
            [SubtitleEntry(index=1, start="", end="", text="기냥 가자")],
            doc_type="prose",
            dialect_region="충청도",
            dialect_mode="to_standard",
        )
        assert any("[사투리 기준]" in line for line in applied_log)
        assert corrected[0].text == "기냥 가자"
        assert any(f.suggested_fix == "그냥 가자" for f in flags)

    def test_document_setting_is_logged(self):
        _, _, applied_log = correct_entries(
            [_entry(1, "밥 무라")], dialect_region="경상도", dialect_mode="to_standard"
        )
        assert any("경상도" in line and "to_standard" in line for line in applied_log)

    def test_without_document_setting_prose_is_untouched_by_dialect(self):
        """설정이 없으면 예전처럼 사투리 처리가 걸리지 않는다."""
        _, _, applied_log = correct_entries([_entry(1, "밥 무라")], doc_type="prose")
        assert not any("[사투리 기준]" in line for line in applied_log)


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
        """제안은 **사전으로 확인된 항목**에서만 나온다. 2026-08-03 감사 전에는
        근거 없는 표(경상도 '그래'->'아이가' 등)로 제안을 만들었다."""
        entries = [_entry(1, "그냥 가자")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "충청도"}, dialect_modes={"민수": "assist"},
        )
        # 텍스트는 절대 바뀌지 않는다
        assert corrected[0].text == "그냥 가자"
        # 표준어→사투리 제안 플래그가 나온다
        assert len(flags) == 1
        assert flags[0].line_index == 1
        assert flags[0].suggested_fix == "기냥 가자"
        assert "제안" in flags[0].reason

    def test_no_suggestion_when_table_has_no_verified_entry(self):
        """근거가 없으면 제안하지 않는다. '빨리'에 대응하는 경상도 표현은
        사전으로 확인된 것이 없다 — 지역어 API는 500 장애이고 우리말샘
        뜻풀이 검색으로도 찾을 수 없다(평가셋 d04)."""
        entries = [_entry(1, "빨리 와라")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "경상도"}, dialect_modes={"민수": "assist"},
        )
        assert corrected[0].text == "빨리 와라"
        assert flags == []

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
        entries = [_entry(1, "그냥 가자")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "충청도"}, dialect_modes={"민수": "to_dialect"},
        )
        assert corrected[0].text == "그냥 가자"
        assert any(f.suggested_fix == "기냥 가자" for f in flags)


class TestToStandardMode:
    """to_standard: 사투리→표준어 **제안**만 남기고 텍스트는 바꾸지 않는다
    (2026-08-03 변경, 네트워크 필요)."""

    def test_dialect_line_gets_standard_suggestion_only(self):
        entries = [_entry(1, "기냥 가자")]
        corrected, flags, _ = correct_entries(
            entries, dialect_map={"민수": "충청도"}, dialect_modes={"민수": "to_standard"},
        )
        # 텍스트는 그대로다 — 자동 변환하지 않는다
        assert corrected[0].text == "기냥 가자"
        assert any(f.suggested_fix == "그냥 가자" for f in flags)
        assert any("사투리→표준어 제안" in f.reason for f in flags)

    def test_dialect_text_is_never_rewritten_by_substring_replacement(self):
        """감사 전에는 표에 있던 '래'->'라고' 때문에 전라도 화자의 '노래'가
        '노라고'로 깨졌다. 근거 없는 항목을 지웠으므로 이제 그대로 나가야 한다."""
        entries = [_entry(1, "그래 노래를 불렀다")]
        corrected, _, _ = correct_entries(
            entries, dialect_map={"민수": "전라도"}, dialect_modes={"민수": "to_standard"},
        )
        assert "노래" in corrected[0].text
        assert "노라고" not in corrected[0].text
