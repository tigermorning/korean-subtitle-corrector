"""표준국어대사전 "전 용어"(옛 용어) 동적 규칙 검증표.

test_engine.py와 같은 원칙 — 여기 기대값은 전부 실제 표준국어대사전 API를
직접 조회해 확인한 결과이고(mock 없음, .env의 STDICT_API_KEY 필요), 국립국어원이
사전을 개정하면 이 테스트도 그 변화를 그대로 반영한다.

검증된 사실(2026-07-25 API 조회):
  - "간질" — 4개 뜻(‘간질거리다’ 어근 / 곤충 / 조직 / '뇌전증'의 전 용어).
    전 용어 뜻이 있으나 다른 뜻도 있는 동형이의어 → ambiguous, 플래그만.
  - "정신분열증" — 뜻이 하나뿐이고 그것이 '조현병'의 전 용어 → 자동 교정.
  - "뇌전증"/"조현병"(현재 표준 용어) — "전 용어" 표지 없음 → 대상 아님.
"""

from subtitle_corrector.dictionary import former_term_lookup
from subtitle_corrector.engine import correct_entries, correct_former_terms
from subtitle_corrector.parsers import SubtitleEntry


class TestFormerTermLookup:
    def test_single_sense_former_term_is_unambiguous(self):
        result = former_term_lookup("정신분열증")
        assert result is not None
        assert result["target"] == "조현병"
        assert result["ambiguous"] is False
        assert result["other_meanings"] == []

    def test_polysemous_former_term_is_ambiguous(self):
        result = former_term_lookup("간질")
        assert result is not None
        assert result["target"] == "뇌전증"
        assert result["ambiguous"] is True
        # 곤충·조직·어근 뜻이 사유에 실려 사람이 문맥으로 판단할 수 있어야 한다.
        assert len(result["other_meanings"]) >= 1

    def test_current_standard_terms_not_flagged(self):
        assert former_term_lookup("뇌전증") is None
        assert former_term_lookup("조현병") is None


class TestCorrectFormerTerms:
    def test_unambiguous_autocorrected(self):
        corrected, applied, flags = correct_former_terms(0, "그는 정신분열증 진단을 받았다")
        assert corrected == "그는 조현병 진단을 받았다"
        assert applied == ["정신분열증 -> 조현병"]
        assert flags == []

    def test_ambiguous_flagged_not_changed(self):
        corrected, applied, flags = correct_former_terms(0, "환자가 간질 발작을 일으켰다")
        # 텍스트는 절대 바뀌지 않는다.
        assert corrected == "환자가 간질 발작을 일으켰다"
        assert applied == []
        assert len(flags) == 1
        assert flags[0].suggested_fix == "뇌전증"
        # 사유에 다른 뜻이 언급되어야 한다(문맥 판단 근거).
        assert "다른 뜻" in flags[0].reason

    def test_ambiguous_in_nondisease_context_still_only_flags(self):
        # 곤충/조직 등 병명이 아닌 문맥이어도 자동으로 바꾸지 않고 플래그만 한다.
        corrected, applied, flags = correct_former_terms(0, "간질과의 곤충을 관찰했다")
        assert corrected == "간질과의 곤충을 관찰했다"
        assert applied == []
        assert len(flags) == 1
        assert flags[0].suggested_fix == "뇌전증"

    def test_current_standard_terms_untouched(self):
        for word in ("뇌전증", "조현병"):
            corrected, applied, flags = correct_former_terms(0, f"그는 {word} 진단을 받았다")
            assert corrected == f"그는 {word} 진단을 받았다"
            assert applied == []
            assert flags == []


class TestCorrectEntriesIntegration:
    def _entry(self, text: str) -> SubtitleEntry:
        return SubtitleEntry(index=0, start="00:00:00,000", end="00:00:01,000", text=text)

    def test_unambiguous_autocorrected_in_pipeline(self):
        entries, flags, applied_log = correct_entries([self._entry("그는 정신분열증 진단을 받았다")])
        assert entries[0].text == "그는 조현병 진단을 받았다"
        assert any("정신분열증 -> 조현병" in line for line in applied_log)
        assert not any(f.suggested_fix == "조현병" for f in flags)

    def test_ambiguous_flagged_in_pipeline(self):
        entries, flags, applied_log = correct_entries([self._entry("환자가 간질 발작을 일으켰다")])
        # 텍스트 불변.
        assert entries[0].text == "환자가 간질 발작을 일으켰다"
        former_flags = [f for f in flags if f.suggested_fix == "뇌전증"]
        assert len(former_flags) == 1
        assert "전 용어" in former_flags[0].reason

    def test_current_standard_term_untouched_in_pipeline(self):
        entries, flags, applied_log = correct_entries([self._entry("그는 뇌전증 진단을 받았다")])
        assert entries[0].text == "그는 뇌전증 진단을 받았다"
        assert not any(f.suggested_fix in ("뇌전증", "조현병") for f in flags)
