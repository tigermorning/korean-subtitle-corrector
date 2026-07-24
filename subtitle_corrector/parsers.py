"""SRT 자막 파일 파싱/저장"""

import re
from dataclasses import dataclass, field
from pathlib import Path

_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")

# SDH 브래킷에서 화자 이름 추출
# 지원 형식: [이름], [이름/상황], [이름: 상황], [이름 (상황)]
_SPEAKER_BRACKET_RE = re.compile(
    r"^\[([^\]/(:]+)"  # 첫 번째 브래킷 안에서 이름만 추출
)


@dataclass
class SubtitleEntry:
    index: int
    start: str
    end: str
    text: str
    speaker: str | None = field(default=None, repr=False)


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
        text = "\n".join(lines[2:])
        # SDH 브래킷에서 화자 이름 추출 ([민수], [민수/상황] 등)
        speaker = None
        first_line = lines[2].strip() if len(lines) > 2 else ""
        bracket_match = _SPEAKER_BRACKET_RE.match(first_line)
        if bracket_match:
            speaker = bracket_match.group(1).strip()
        entries.append(
            SubtitleEntry(
                index=int(lines[0].strip()),
                start=match.group(1),
                end=match.group(2),
                text=text,
                speaker=speaker,
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
    return [SubtitleEntry(index=i, start="", end="", text=line, speaker=None) for i, line in enumerate(lines)]


def write_plain_text(entries: list[SubtitleEntry], path: Path) -> None:
    Path(path).write_text("\n".join(e.text for e in entries) + "\n", encoding="utf-8")


def parse_docx(path: Path) -> list[SubtitleEntry]:
    """Word 문서(.docx)의 문단을 한 줄씩 SubtitleEntry로 만든다.

    서식(볼드체 등)까지 그대로 보존하는 건 이 도구의 범위를 넘어선다 —
    parse_plain_text와 동일하게 문단의 순수 텍스트만 다루고, 교정 결과도
    일반 텍스트로 돌려준다(write_plain_text 재사용). 표 안의 텍스트는
    다루지 않는다(본문 문단만)."""
    from docx import Document

    doc = Document(str(path))
    return [SubtitleEntry(index=i, start="", end="", text=p.text, speaker=None) for i, p in enumerate(doc.paragraphs)]
