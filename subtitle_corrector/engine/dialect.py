"""사투리 처리(protect/assist/to_standard). 모드 정규화는 options.py에 있다.
"""

from ..dictionary import convert_dialect, DIALECT_MARKERS, detect_dialect_ratio, search_dialect
from ..report import FlagItem

def check_dialect(
    index: int,
    text: str,
    region: str | None,
    mode: str | None,
) -> tuple[str, list[FlagItem]]:
    """resolve_dialect_mode()로 이미 결정된 (region, mode)에 따라 사투리를 처리한다.

    - region이 None(사투리 미지정 화자): 자동 감지 후 플래그만 남긴다(비율 >= 0.15).
      표준어로 간주하지만 어미가 표준이 아니어도 자동교정하지 않는다.
    - mode == "assist": 텍스트는 그대로 두고, 표준어→사투리 제안 플래그만 만든다.
      convert_dialect(to_dialect)가 바꿀 게 없고 search_dialect도 비면 플래그 없음.
    - mode == "to_standard": 사투리→표준어 **제안 플래그만**. 2026-08-03 이전에는
      자동 변환이었으나, 표지 사전 감사에서 근거 없는 항목이 원고를 깨뜨리는 것을
      확인해 제안으로 내렸다(`dictionary/dialect.py` 상단 "사투리 표 감사").

    "protect" 모드는 이 함수를 호출하지 않는다(호출부에서 통째로 건너뛴다).

    반환값: (처리된 텍스트, 플래그 목록)
    """
    # 사투리 미지정 화자 — 자동 감지 (항상 플래그만)
    if region is None:
        from .dictionary import DIALECT_MARKERS
        for detected in DIALECT_MARKERS:
            if detect_dialect_ratio(text, detected) >= 0.15:
                return text, [FlagItem(
                    line_index=index,
                    original_text=text,
                    reason=(
                        f"사투리 패턴 감지 ({detected}) — "
                        f"이 화자가 {detected} 사투리를 쓰는 것 같습니다. "
                        "사투리 설정이 필요하면 화자별 사투리를 지정해 주세요."
                    ),
                )]
        return text, []

    if mode == "to_standard":
        # 2026-08-03부터 **자동으로 바꾸지 않는다**. 표지 사전 27개 항목을 우리말샘으로
        # 전수 조회했더니 검증되는 것이 3개뿐이었고(자세한 내용은 dictionary/dialect.py
        # 상단 "사투리 표 감사"), 이 표는 단어 경계 없이 문자열을 치환하기 때문에
        # 근거 없는 항목 하나가 원고를 조용히 깨뜨렸다 — '그래 노래를 불렀다'가
        # '그라고 노라고를 불렀다'가 되는 식이다. 남은 항목은 사전으로 확인된
        # 것뿐이지만, 표를 다시 채울 때 같은 사고가 재발하지 않도록 **경로 자체를
        # 제안으로 내렸다**. 사람이 보고 채택하는 것까지 막지는 않는다.
        converted = convert_dialect(text, region, "to_standard")
        if converted != text:
            return text, [FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=converted,
                reason=(
                    f"사투리→표준어 제안 ({region}) — 자동으로 바꾸지 않습니다. "
                    "표지 사전의 근거가 항목마다 고르지 않아 확인 후 직접 반영하세요."
                ),
            )]
        return text, []

    if mode == "assist":
        # 텍스트는 절대 바꾸지 않는다. 표준어 표현을 사투리로 바꾸는 제안만 남긴다.
        suggested = convert_dialect(text, region, "to_dialect")
        if suggested != text:
            return text, [FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=suggested,
                reason=(
                    f"사투리 제안 ({region}) — 이 화자는 {region} 사투리를 쓰도록 "
                    "지정돼 있습니다. 표준어 표현을 사투리로 바꾸는 제안이며, "
                    "자동 반영하지 않으니 검토 후 채택하세요."
                ),
            )]
        # convert가 바꿀 게 없으면 지역어 종합 정보 API로 대응 사투리를 조회한다.
        api_results = []
        try:
            api_results = search_dialect(text.split()[-1] if text.split() else "")
        except Exception:
            pass
        for result in api_results:
            dialect_word = result.get("word", "")
            if dialect_word:
                std_word = result.get("std_word", "")
                std_note = f" (표준어: {std_word})" if std_word else ""
                return text, [FlagItem(
                    line_index=index,
                    original_text=text,
                    reason=(
                        f"사투리 제안 ({region}) — 참고 사투리 표현: "
                        f"{dialect_word}{std_note}. 검토 후 직접 반영하세요."
                    ),
                )]
        # 제안할 사투리가 없으면 플래그를 남기지 않는다.
        return text, []

    # 알 수 없는 모드는 안전하게 보호로 간주한다(플래그 없음).
    return text, []
