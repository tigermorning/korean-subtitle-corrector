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
