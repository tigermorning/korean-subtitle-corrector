"""자막 편집 표지(화면자막·줄바꿈·위치)를 실제 텍스트에서 찾아내는 도구.
"""

import re
from .options import SubtitleMarkers, _MARKER_PAIRS

def _after_subtitle_marker(text: str, pos: int, markers: "SubtitleMarkers | None") -> bool:
    """pos 바로 앞이 자막 표시(위치·화자명·어조)의 끝인지.

    표시와 말자막 사이에는 반드시 한 칸이 있어야 하는데(사용자 지정 2026-08-02),
    조사·어미 결합 규칙이 그 공백을 지워 버리는 일이 있었다 — '[달래] 아, 비켜!'의
    '아'를 호격조사로 보고 앞말에 붙이려 한 경우다. 뒤에 다시 한 칸을 넣어 결과는
    맞았지만, 자동 교정 로그에 하지도 않은 변경이 남아 사용자를 혼란스럽게 했다.
    """
    unit = _marker_unit_pattern(markers)
    if not unit:
        return False
    return any(m.end() == pos for m in re.finditer(unit, text))


def _is_marker_only_line(text: str, markers: "SubtitleMarkers | None") -> bool:
    """표시(효과음·지문·화자명)만 있고 대사가 없는 줄인지."""
    unit = _marker_unit_pattern(markers)
    if not unit:
        return False
    return not re.sub(unit, "", text).strip()


def _marker_unit_pattern(markers: "SubtitleMarkers | None") -> str:
    """한 덩어리로 취급할 '표시'의 정규식. 자막 위치·화자명·어조 표기를 모은다.

    이 셋은 대사가 아니라 편집·전달용 표시다. 서로 붙여 쓰고 대사와만 한 칸을
    띄운다(사용자 지정 2026-08-02).
    """
    markers = markers or SubtitleMarkers()
    units = []
    if markers.position:
        units.append(re.escape(markers.position))
    for pair in (markers.speaker, markers.tone):
        if pair and len(pair) >= 2:
            open_ch, close_ch = re.escape(pair[0]), re.escape(pair[-1])
            units.append(f"{open_ch}[^{close_ch}]*{close_ch}")
    # 중복 제거(화자명과 어조를 같은 부호로 쓰는 경우), 순서 유지
    return "|".join(dict.fromkeys(units))


def _screen_text_spans(text: str, marker: str) -> list[tuple[int, int]]:
    """화면자막 표지가 가리키는 보호 구간 [(시작, 끝)]을 돌려준다.

    짝이 있는 문자면 여는 표지와 닫는 표지 사이(표지 포함)를, 짝이 없는 문자면
    표지가 나온 자리부터 줄 끝까지를 보호한다. 닫는 짝을 못 찾으면 줄 끝까지로
    본다 — 열어 놓고 안 닫은 경우 그 뒤는 화면자막일 가능성이 높고, 교정하지
    않는 쪽이 덜 위험하다.
    """
    if not marker:
        return []
    closing = _MARKER_PAIRS.get(marker)
    spans = []
    pos = 0
    while True:
        start = text.find(marker, pos)
        if start == -1:
            return spans
        if closing is None:
            spans.append((start, len(text)))  # 짝 없는 표지 -> 그 뒤 전체
            return spans
        end = text.find(closing, start + len(marker))
        if end == -1:
            spans.append((start, len(text)))
            return spans
        end += len(closing)
        spans.append((start, end))
        pos = end


def _split_by_marker(text: str, marker: str) -> list[str]:
    """표지를 구분자로 쪼개되 표지 자체도 조각으로 남긴다(복원용)."""
    if not marker:
        return [text]
    parts = []
    for i, chunk in enumerate(text.split(marker)):
        if i:
            parts.append(marker)
        parts.append(chunk)
    return parts
