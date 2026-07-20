"""examples/sample.srt 전체 파이프라인 회귀 테스트.

engine.py의 개별 함수 단위 테스트(test_engine.py)와 달리, 이 테스트는
correct_entries() 전체가 실제 자막 파일 하나를 어떻게 처리하는지 통째로
확인한다 — 개별 함수는 다 옳아도 correct_entries()의 호출 순서나 조합이
잘못되면(예: 한 교정이 다른 검사의 판단을 바꿔버리는 경우) 개별 테스트만
으로는 못 잡을 수 있기 때문이다.

이 파일이 실패하면 새로 회귀가 생겼거나, examples/sample.srt를 의도적으로
바꿨거나 둘 중 하나다 — 후자라면 기대값도 함께 업데이트한다.
"""

from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import parse_srt

EXPECTED_CORRECTED_TEXTS = [
    "안녕하세요 반갑습니다",
    "오늘은 날씨가 좋네요",
    "저는 초콜릿을 좋아해요",
    "스노우 기자가 발표했다",  # 고유명사는 자동 반영하지 않고 플래그만
    "노천카페에서 만나자",
    "그 일은 할 만하다",
    "그러고 나서 집에 갔다",
    "고개를 반듯이 들어라",  # 제57항 혼동 쌍 검사는 제거됨(2026-07-17) — 플래그도 자동 교정도 없음
    "그는 손모아장갑을 꼈다",
    "반팔 티셔츠를 입었다",  # 순화어는 플래그만
]


def test_sample_srt_full_pipeline():
    entries = parse_srt("examples/sample.srt")
    corrected, flags, applied = correct_entries(entries)

    assert [e.text for e in corrected] == EXPECTED_CORRECTED_TEXTS
    assert len(applied) == 6
    assert any("초코렛 -> 초콜릿" in a for a in applied)
    assert any("그 일은 할만하다 -> 그 일은 할 만하다" in a for a in applied)
    assert any("벙어리장갑 -> 손모아장갑" in a for a in applied)

    flag_line_indices = {f.line_index for f in flags}
    assert flag_line_indices == {4, 9, 10}
