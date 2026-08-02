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
    - mode == "to_standard": 사투리→표준어 자동 변환 + 확인 플래그.

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
        converted = convert_dialect(text, region, "to_standard")
        if converted != text:
            return converted, [FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=converted,
                reason=(
                    f"사투리→표준어 자동 변환 ({region}) — "
                    "변환된 텍스트를 확인해 주세요."
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
