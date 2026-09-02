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

    def test_ambiguous_in_nondisease_context_is_not_flagged(self):
        """병명 문맥이 아니면 **묻지도 않는다**(2026-08-05 정책 변경, §73).

        전에는 곤충 문맥에도 '뇌전증' 제안이 붙었다. 사용자 보고("'건초'의 정의를
        말하는 문맥인데도 의학용어로 플래깅")를 계기로, 문서에 그 전문 분야 뜻으로
        읽을 근거가 하나도 없으면 플래그를 내지 않는다. 텍스트는 어느 쪽이든 바뀌지
        않으므로 이 판정이 틀려도 잃는 것은 제안 하나다."""
        corrected, applied, flags = correct_former_terms(0, "간질과의 곤충을 관찰했다")
        assert corrected == "간질과의 곤충을 관찰했다"
        assert applied == []
        assert flags == []

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
        assert any("정신분열증 -> 조현병" in note.message for note in applied_log)
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


class TestFormerTermContextEvidence:
    """동형이의 옛 용어를 **문맥 근거가 있을 때만** 묻는다(2026-08-05 사용자 보고, §73).

    `건초`는 우리말샘에 다섯 뜻이 있다 — 일반어 '베어서 말린 풀', 역사 연호 셋,
    의학 '힘줄집'(옛 용어). 정의를 그대로 말하는 문장에까지 '힘줄집' 제안이 붙었다.
    """

    def _entry(self, index: int, text: str) -> SubtitleEntry:
        return SubtitleEntry(index=index, start="00:00:00,000", end="00:00:01,000", text=text)

    def _former_flags(self, *lines: str):
        entries = [self._entry(i + 1, t) for i, t in enumerate(lines)]
        _corrected, flags, _log = correct_entries(entries)
        return [f for f in flags if "전 용어" in f.reason]

    def test_definition_context_is_not_flagged(self):
        assert self._former_flags("건초는 베어서 말린 풀이다", "주로 사료나 퇴비로 쓴다") == []

    def test_everyday_context_is_not_flagged(self):
        assert self._former_flags("건초 더미에 누웠다", "목장에는 소가 스무 마리 있다") == []

    def test_medical_context_is_flagged(self):
        flags = self._former_flags("건초에 염증이 생겼다", "힘줄 주변이 부어올랐어요")
        assert [f.suggested_fix for f in flags] == ["힘줄집"]

    def test_context_is_read_from_the_whole_document(self):
        """자막 한 줄은 짧다 — 근거가 다른 줄에 있어도 찾아야 한다."""
        flags = self._former_flags("건초가 문제라는데요", "힘줄 염증이 심하다고 합니다")
        assert [f.suggested_fix for f in flags] == ["힘줄집"]

    def test_unambiguous_former_term_ignores_context(self):
        """뜻이 하나뿐인 옛 용어는 문맥과 무관하게 지금처럼 자동 교정한다."""
        entries = [self._entry(1, "그는 정신분열증 진단을 받았다")]
        corrected, _flags, _log = correct_entries(entries)
        assert corrected[0].text == "그는 조현병 진단을 받았다"

    def test_generic_verb_overlap_does_not_support_specialist_reading(self):
        """'정수'(精髓, 흔한 뜻 — 진안중평농악의 정수)가 '양수'의 옛 용어로
        오탐지됐다(2026-09-02 실사용 감수, 뉴스 기사 묶음 텍스트). 원인은
        문서 전체 문맥에 '건강 관리를 잘하여'(양수의 다른 뜻풀이)와 우연히
        겹치는 흔한 낱말('건강'·'들다'·'올리다')이 있었던 것 — '있다' 하나
        때문에 오탐지됐던 §73 건초 사고와 같은 부류라 같은 불용어 목록에
        추가해 막았다."""
        flags = self._former_flags(
            "그 공연에서 전통 예술의 정수를 느낄 수 있었다",
            "건강을 위해 매일 아침 물을 마시고 손을 들어 스트레칭을 한다",
        )
        assert [f for f in flags if f.suggested_fix == "양수"] == []

    def test_polysemous_context_word_does_not_support_specialist_reading(self):
        """'정수' 수정을 검증하던 중 새 오탐지 둘을 더 찾았다(2026-09-02,
        같은 실사용 감수) — '방안'(→모눈, 옛 용어 뜻의 분야=수학)과 '소재'
        (→금육재, 분야=가톨릭)가 '감독'·'허가' 같은 흔한 낱말의 무관한 다른
        뜻(가톨릭 직함 등) 때문에 오탐지됐다. `sense_fields(lemma)`(그
        낱말의 모든 뜻)를 `specialist_only_fields(lemma)`(일반 뜻이 하나도
        없는 낱말만 인정)로 바꿔 근본적으로 막았다(§92) — '감독'·'허가'는
        일반 뜻이 있어 더는 분야 신호로 안 쓰인다."""
        flags = self._former_flags(
            "구청장은 주민 체감형 상생 방안을 마련해 감독 기관의 허가를 받았다",
            "영화 감독은 다음 작품 소재를 찾고 있다고 밝혔다",
        )
        assert [f for f in flags if f.suggested_fix in ("모눈", "금육재")] == []

    def test_generic_noun_overlap_does_not_support_specialist_reading(self):
        """②(뜻풀이 낱말 겹침)에서도 같은 부류 오탐지가 재발했다 — '금육재'
        (소재의 옛 용어)의 뜻풀이에 흔한 명사 '시작'이 들어 있어("사순절이
        시작되는 수요일"), '시작'이 반복 등장하는 뉴스 기사 묶음 문서
        전체에서 '소재'가 오탐지됐다(2026-09-02 실사용 감수). '있다' 하나
        때문에 오탐지됐던 §73과 같은 부류라 같은 불용어 목록에 추가해 막았다."""
        flags = self._former_flags(
            "감독은 다음 작품 소재를 찾고 있다고 밝혔다",
            "축제는 다음 달 3일 시작된다",
        )
        assert [f for f in flags if f.suggested_fix == "금육재"] == []

    def test_field_cluster_does_not_admit_unrelated_science_fields(self):
        """세 번째 잔불 — '방안'(→모눈, 분야=수학)이 무관한 '플라스틱'·'활성'
        (둘 다 화학 전용 낱말, 일반 뜻 없음) 때문에 오탐지됐다(2026-09-02
        실사용 감수). `_field_group()`이 {수학·물리·화학·천문·지구}를 한
        계열로 묶어 근거로 인정한 탓이었다 — 이 계열 묶음이 실제로 필요한
        기존 테스트는 하나도 없어서(§93·§94 확인) 안전하게 지우고 정확히
        같은 분야만 근거로 인정하게 좁혔다(§94)."""
        flags = self._former_flags(
            "구청장은 주민 체감형 상생 방안을 마련했다",
            "일회용 플라스틱 사용을 줄이고 활성 물질을 연구한다",
        )
        assert [f for f in flags if f.suggested_fix == "모눈"] == []
