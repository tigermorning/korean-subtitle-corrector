"""자막 교정 엔진 — v0: 사전 미등재 단어 탐지

주의: 이건 PRD의 3단계 판단 엔진(사전/규범 -> 온라인가나다 아카이브 -> 사람) 중
1단계의 아주 축소된 버전이다. 현재는 "표준국어대사전에 없는 단어"를 찾아 플래그할
뿐, 실제 띄어쓰기 오류(형태소 분석 필요)는 아직 판단하지 않는다.
"""

import re

from .dictionary import word_exists
from .parsers import SubtitleEntry
from .report import FlagItem

_TOKEN_RE = re.compile(r"[가-힣]+")


def check_line(index: int, text: str) -> FlagItem | None:
    tokens = _TOKEN_RE.findall(text)
    unknown = [t for t in tokens if not word_exists(t)]
    if unknown:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=f"사전에 없는 단어: {', '.join(unknown)}",
        )
    return None


def check_entries(entries: list[SubtitleEntry]) -> list[FlagItem]:
    return [flag for e in entries if (flag := check_line(e.index, e.text))]
