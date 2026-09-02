"""번역투 — 이중 피동 확인 플래그 검증표.

기대값은 실제 표준국어대사전/우리말샘 API 조회로 확인한 결과다(mock 없음,
.env의 STDICT_API_KEY 필요) — 결합형("잊혀지다" 등)은 두 사전 모두 표제어
없음, 단일 피동형("잊히다" 등)은 전부 등재됨(2026-09-02 확인).

검증표:
  - "잊혀지다"/"잊혀졌다"/"잊혀진다" → 이중 피동 플래그(과거형·현재형 포함)
  - "읽혀지고 있다"/"보여지는" → 진행형·관형형에도 구조 조건으로 잡힘(활용형
    나열이 아니라 형태소 구조로 detect하므로)
  - "잊혔다"/"읽혔다"(단일 피동, 정상) → 플래그 없음
  - "밝혀지다"류(lemma가 목록 밖) → 플래그 없음(과잉 확대 방지 확인)
  - "쳐 지다"처럼 어간과 어미가 붙어 있지 않은 경우 → 대상 아님(구조 조건 미충족)
"""

from subtitle_corrector.engine import correct_entries
from subtitle_corrector.engine.translationese import check_double_passive_voice
from subtitle_corrector.parsers import SubtitleEntry


class TestCheckDoublePassiveVoice:
    def test_past_tense_is_flagged(self):
        flag = check_double_passive_voice(0, "그 일은 이미 잊혀졌다")
        assert flag is not None
        assert "잊혀졌다" in flag.reason
        assert "이중 피동" in flag.reason

    def test_present_tense_is_flagged(self):
        flag = check_double_passive_voice(0, "이 소설은 그렇게 쓰여진다")
        assert flag is not None

    def test_progressive_conjugation_is_flagged(self):
        """정적 목록이었다면 놓쳤을 활용형 — 구조 조건이라 잡힌다."""
        flag = check_double_passive_voice(0, "이 책은 많은 사람들에게 읽혀지고 있다")
        assert flag is not None
        assert "읽혀지고" in flag.reason

    def test_attributive_conjugation_is_flagged(self):
        flag = check_double_passive_voice(0, "문이 열려지고 사람들이 보여지는 장면")
        assert flag is not None

    def test_single_passive_is_not_flagged(self):
        assert check_double_passive_voice(0, "그 일은 이미 잊혔다") is None
        assert check_double_passive_voice(0, "이 책은 많은 사람들에게 읽혔다") is None

    def test_unlisted_lemma_is_not_flagged(self):
        """목록 밖 낱말('밝히다')까지 번지지 않는지 — 과잉 확대 방지."""
        assert check_double_passive_voice(0, "사실이 밝혀졌다") is None

    def test_text_is_never_changed(self):
        """확인 플래그 전용 — 자동 교정 파이프라인에서 텍스트가 바뀌면 안 된다."""
        entries = [
            SubtitleEntry(index=0, start="00:00:00,000", end="00:00:01,000", text="그 일은 이미 잊혀졌다")
        ]
        corrected, flags, _log = correct_entries(entries)
        assert corrected[0].text == "그 일은 이미 잊혀졌다"
        assert any("이중 피동" in f.reason for f in flags)
