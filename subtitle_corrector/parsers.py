"""SRT 자막 파일 파싱/저장"""

import re
from dataclasses import dataclass
from pathlib import Path

_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")


@dataclass
class SubtitleEntry:
    index: int
    start: str
    end: str
    text: str


def parse_srt(path: Path) -> list[SubtitleEntry]:
    entries = []
    blocks = Path(path).read_text(encoding="utf-8-sig").strip().split("\n\n")
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        match = _TIME_RE.match(lines[1].strip())
        if not match:
            continue
        entries.append(
            SubtitleEntry(
                index=int(lines[0].strip()),
                start=match.group(1),
                end=match.group(2),
                text="\n".join(lines[2:]),
            )
        )
    return entries


def write_srt(entries: list[SubtitleEntry], path: Path) -> None:
    blocks = [f"{e.index}\n{e.start} --> {e.end}\n{e.text}" for e in entries]
    Path(path).write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def parse_plain_text(path: Path) -> list[SubtitleEntry]:
    """자막이 아닌 일반 한국어 텍스트(.txt 등)를 한 줄씩 SubtitleEntry로 만든다.

    교정 엔진(engine.correct_entries)은 SubtitleEntry.text만 사용하고
    index/start/end는 SRT 저장에만 쓰이므로, 일반 텍스트에서는 이 필드들을
    빈 값으로 채운다. 빈 줄도 그대로 하나의 항목으로 유지해서, 원본의 줄
    구성(문단 구분 등)을 그대로 보존한다."""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    return [SubtitleEntry(index=i, start="", end="", text=line) for i, line in enumerate(lines)]


def write_plain_text(entries: list[SubtitleEntry], path: Path) -> None:
    Path(path).write_text("\n".join(e.text for e in entries) + "\n", encoding="utf-8")
