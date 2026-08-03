"""SRT 자막 파일 파싱/저장"""

from .decoding import read_text as read_source_text
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
    # 자막 형식마다 대사 앞뒤에 우리가 다루지 않는 것들이 붙는다(ASS의 스타일
    # 필드, SAMI의 태그, TTML의 속성, VTT의 큐 설정). 그 조각을 원문 그대로 들고
    # 있다가 저장할 때 되돌린다 — 이해하지 못하는 정보를 잃지 않기 위해서다.
    raw_prefix: str | None = field(default=None, repr=False)
    raw_suffix: str | None = field(default=None, repr=False)
    # 교정 전 원문. 저장할 때 원본 파일에서 이 대사를 찾아 바꾸는 데 쓴다.
    original_text: str | None = field(default=None, repr=False)


def _extract_speaker(first_line: str) -> str | None:
    """SDH 브래킷에서 화자 이름을 뽑는다 ([민수], [민수/상황] 등).

    "[문 여는 소리]"처럼 브래킷만 있고 뒤에 대사가 없는 줄은 효과음·지문이므로
    화자로 잡지 않는다(그렇지 않으면 효과음이 사투리 설정 목록에 대거 섞여 온다).
    브래킷 뒤에 실제 대사가 이어질 때만 화자로 본다. SRT 외 형식(formats.py)도
    같은 규칙을 써야 하므로 함수로 분리했다.
    """
    bracket_match = _SPEAKER_BRACKET_RE.match(first_line)
    if not bracket_match:
        return None
    close_idx = first_line.find("]")
    remainder = first_line[close_idx + 1 :].strip() if close_idx != -1 else ""
    return bracket_match.group(1).strip() if remainder else None


def parse_srt(path: Path) -> list[SubtitleEntry]:
    entries = []
    blocks = read_source_text(path).strip().split("\n\n")
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        match = _TIME_RE.match(lines[1].strip())
        if not match:
            continue
        text = "\n".join(lines[2:])
        # SDH 브래킷에서 화자 이름 추출 ([민수], [민수/상황] 등).
        # 단, "[문 여는 소리]"처럼 브래킷만 있고 뒤에 대사가 없는 줄은 효과음·
        # 지문이므로 화자로 잡지 않는다(그렇지 않으면 효과음이 사투리 설정
        # 목록에 대거 섞여 들어온다). 브래킷 뒤에 실제 대사가 이어질 때만 화자.
        speaker = _extract_speaker(lines[2].strip() if len(lines) > 2 else "")
        entries.append(
            SubtitleEntry(
                index=int(lines[0].strip()),
                start=match.group(1),
                end=match.group(2),
                text=text,
                speaker=speaker,
                original_text=text,
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
    lines = read_source_text(path).splitlines()
    return [
        SubtitleEntry(index=i, start="", end="", text=line, speaker=None, original_text=line)
        for i, line in enumerate(lines)
    ]


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
    return [
        SubtitleEntry(index=i, start="", end="", text=p.text, speaker=None, original_text=p.text)
        for i, p in enumerate(doc.paragraphs)
    ]


def parse_pdf(path: Path) -> list[SubtitleEntry]:
    """PDF에서 텍스트를 뽑아 한 줄씩 SubtitleEntry로 만든다.

    도서 번역 원고 검토처럼 PDF로 받은 글을 교정하려는 경우를 위한 입력 경로다.
    **텍스트 레이어가 있는 PDF만** 읽을 수 있다 — 스캔본(그림만 있는 PDF)은
    글자가 이미지라 여기서 아무 텍스트도 나오지 않으며, 그런 경우 OCR이 선행되어야
    한다. 빈 결과가 나오면 호출부가 그 사실을 사용자에게 알린다.

    PDF는 서식·쪽 배치를 그대로 되돌릴 수 있는 형식이 아니므로(우리 범위 밖),
    교정 결과는 다른 문서와 마찬가지로 순수 텍스트로 돌려준다.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(text.splitlines())
    return [
        SubtitleEntry(index=i, start="", end="", text=line, speaker=None, original_text=line)
        for i, line in enumerate(lines)
    ]
