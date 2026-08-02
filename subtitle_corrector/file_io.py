"""파일 형식 판별 — 확장자를 보고 알맞은 파서·저장 함수를 고른다.

CLI와 웹 API가 같은 목록을 쓰도록 여기 한곳에 모은다. 형식을 새로 지원할 때
고칠 곳이 늘어나면 "웹에서는 열리는데 CLI에서는 안 열린다" 같은 어긋남이 생긴다.
"""

from pathlib import Path

from . import formats
from .parsers import (
    SubtitleEntry,
    parse_docx,
    parse_plain_text,
    parse_srt,
    write_plain_text,
    write_srt,
)

# 확장자 -> (파서, 저장 함수, 저장 시 원본 파일이 필요한가)
#
# 원본이 필요한 형식은 스타일·메타데이터가 파일 곳곳에 흩어져 있어(ASS의 스타일
# 절, SAMI의 CSS, TTML의 헤더) 통째로 다시 쓰지 않고 **원본에서 대사만 갈아 끼우는**
# 방식으로 저장한다. 우리가 이해하지 못하는 정보를 잃지 않기 위해서다.
_HANDLERS: dict[str, tuple] = {
    ".srt": (parse_srt, write_srt, False),
    ".vtt": (formats.parse_vtt, formats.write_vtt, False),
    ".sbv": (formats.parse_sbv, formats.write_sbv, False),
    ".sub": (formats.parse_subviewer, formats.write_subviewer, False),
    ".smi": (formats.parse_smi, formats.write_smi, True),
    ".sami": (formats.parse_smi, formats.write_smi, True),
    ".ass": (formats.parse_ass, formats.write_ass, True),
    ".ssa": (formats.parse_ass, formats.write_ass, True),
    ".ttml": (formats.parse_ttml, formats.write_ttml, True),
    ".dfxp": (formats.parse_ttml, formats.write_ttml, True),
    ".xml": (formats.parse_ttml, formats.write_ttml, True),
    ".txt": (parse_plain_text, write_plain_text, False),
    ".docx": (parse_docx, write_plain_text, False),
}

SUBTITLE_EXTENSIONS = tuple(
    ext for ext in _HANDLERS if ext not in (".txt", ".docx")
)
SUPPORTED_EXTENSIONS = tuple(_HANDLERS)


def is_supported(suffix: str) -> bool:
    return suffix.lower() in _HANDLERS


def parse_file(path: Path) -> list[SubtitleEntry]:
    """확장자에 맞는 파서로 읽는다. 지원하지 않는 확장자는 ValueError."""
    suffix = Path(path).suffix.lower()
    if suffix not in _HANDLERS:
        raise ValueError(f"지원하지 않는 형식입니다: {suffix or '(확장자 없음)'}")
    return _HANDLERS[suffix][0](Path(path))


def write_file(entries: list[SubtitleEntry], path: Path, source: Path) -> None:
    """원본과 같은 형식으로 저장한다.

    source는 원본 파일 경로다 — 대사만 갈아 끼우는 형식(ASS/SAMI/TTML)에서
    나머지 내용을 그대로 가져오기 위해 필요하다.
    """
    suffix = Path(source).suffix.lower()
    _parse, writer, needs_source = _HANDLERS.get(suffix, (None, write_plain_text, False))
    if needs_source:
        writer(entries, Path(path), Path(source))
    else:
        writer(entries, Path(path))


def output_suffix(source_name: str) -> str:
    """교정 결과 파일의 확장자. 자막은 원본 형식을 유지하고, 문서는 .txt로 준다.

    .docx는 서식까지 보존하는 새 문서를 만들지 않는다(이 도구의 범위 밖).
    """
    suffix = Path(source_name).suffix.lower()
    return suffix if suffix in SUBTITLE_EXTENSIONS else ".txt"
