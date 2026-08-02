"""자막 파일 형식 지원 (SRT 외 형식 파싱·저장).

이 도구가 다루는 것은 **대사 텍스트뿐**이다. 형식마다 스타일·배치·메타데이터가
붙는데(ASS의 스타일 정의, SAMI의 CSS, TTML의 속성, VTT의 큐 설정), 그런 것은
교정 대상이 아니므로 **원본 그대로 보존**해서 되돌려 준다.

보존 방식은 형식별로 다르지 않다: 각 대사의 앞뒤 원문 조각(raw_prefix/raw_suffix)을
그대로 들고 있다가, 교정된 텍스트만 그 사이에 끼워 다시 조립한다. 이렇게 하면 우리가
이해하지 못하는 속성이 있어도 잃지 않는다.

지원 형식:
  .srt              SubRip (parsers.py가 담당 — 이 모듈은 나머지)
  .vtt              WebVTT
  .smi / .sami      SAMI (한국 방송·구형 플레이어에서 흔함)
  .ass / .ssa       (Advanced) SubStation Alpha
  .sbv              YouTube 자막
  .ttml/.dfxp/.xml  TTML(Timed Text)
  .sub              SubViewer

지원하지 않는 형식은 이유가 분명할 때만 뺐다:
  .scc / .mcc       CEA-608/708 바이트 스트림. 문자를 프레임 단위로 인코딩해
                    텍스트 교정 대상이 아니다.
  .stl              EBU STL은 바이너리 규격이라 별도 라이브러리가 필요하다.
  .idx / .sup       그림(비트맵) 자막이라 텍스트가 없다. OCR이 선행되어야 한다.
"""

import re
from pathlib import Path

from .parsers import SubtitleEntry, _extract_speaker

# ---------------------------------------------------------------- 공통 도구

_TIME_UNITS = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")


def _to_hms(value: str) -> str:
    """여러 형식의 타임코드를 'HH:MM:SS,mmm'으로 맞춘다.

    읽기 속도(CPS) 계산이 이 형식을 전제로 하므로 파싱 단계에서 통일한다.
    형식을 알아볼 수 없으면 빈 문자열을 돌려준다 — 계산을 건너뛰게 하기 위함이다.
    """
    match = _TIME_UNITS.match(value.strip())
    if not match:
        return ""
    hours, minutes, seconds, millis = match.groups()
    millis = (millis or "0").ljust(3, "0")
    return f"{int(hours or 0):02d}:{int(minutes):02d}:{int(seconds):02d},{millis}"


def _rebuild(entries: list[SubtitleEntry], header: str = "", footer: str = "") -> str:
    """각 대사의 원문 앞뒤 조각 사이에 교정된 텍스트를 끼워 다시 조립한다."""
    parts = [header]
    for entry in entries:
        parts.append((entry.raw_prefix or "") + entry.text + (entry.raw_suffix or ""))
    parts.append(footer)
    return "".join(parts)


# ---------------------------------------------------------------- WebVTT

# VTT는 SRT와 두 가지가 다르다: 밀리초 구분자가 마침표이고, 한 시간 미만이면 시를
# 생략할 수 있다. 타임코드 뒤에는 큐 설정(line/position/align 등)이 붙을 수 있다.
_VTT_TIME = re.compile(
    r"((?:\d{2,}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d{2,}:)?\d{1,2}:\d{2}[.,]\d{1,3})(.*)"
)


def parse_vtt(path: Path) -> list[SubtitleEntry]:
    """WebVTT를 읽는다. 큐 식별자·큐 설정·NOTE/STYLE 블록은 보존한다."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    entries: list[SubtitleEntry] = []
    for block in raw.split("\n\n"):
        lines = block.strip().splitlines()
        if not lines:
            continue
        head = lines[0].strip().upper()
        if head.startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        time_at = 0 if "-->" in lines[0] else 1
        if time_at >= len(lines):
            continue
        match = _VTT_TIME.match(lines[time_at].strip())
        if not match:
            continue
        cue_id = lines[0].strip() if time_at == 1 else ""
        text = "\n".join(lines[time_at + 1 :])
        prefix = (f"{cue_id}\n" if cue_id else "") + lines[time_at].strip() + "\n"
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_to_hms(match.group(1)),
                end=_to_hms(match.group(2)),
                text=text,
                speaker=_extract_speaker(text.splitlines()[0].strip() if text else ""),
                raw_prefix=prefix,
                raw_suffix="\n\n",
            )
        )
    return entries


def write_vtt(entries: list[SubtitleEntry], path: Path) -> None:
    Path(path).write_text(_rebuild(entries, header="WEBVTT\n\n").rstrip("\n") + "\n", encoding="utf-8")


# ---------------------------------------------------------------- SAMI (.smi)

_SMI_SYNC = re.compile(r"(<SYNC\b[^>]*>)(.*?)(?=<SYNC\b|</BODY>|\Z)", re.IGNORECASE | re.DOTALL)
_SMI_START = re.compile(r"Start\s*=\s*(\d+)", re.IGNORECASE)
_SMI_PARA = re.compile(r"(<P\b[^>]*>)(.*)", re.IGNORECASE | re.DOTALL)


def _millis_to_hms(millis: int) -> str:
    seconds, ms = divmod(int(millis), 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def parse_smi(path: Path) -> list[SubtitleEntry]:
    """SAMI(.smi)를 읽는다. 한국 방송·구형 플레이어에서 아직 흔한 형식이다.

    SAMI는 HTML을 닮은 형식이라 <SYNC Start=1000><P Class=KRCC>대사 구조다.
    종료 시각이 따로 없고 **다음 SYNC가 시작 시각**이므로 그렇게 계산한다.
    빈 자막(&nbsp;)은 화면을 비우는 표시라 교정 대상이 아니다.
    """
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    found = list(_SMI_SYNC.finditer(raw))
    entries: list[SubtitleEntry] = []
    for order, match in enumerate(found):
        sync_tag, body = match.group(1), match.group(2)
        start_match = _SMI_START.search(sync_tag)
        para = _SMI_PARA.match(body.strip())
        if not para:
            continue
        text = para.group(2).strip()
        if not text or text.replace("&nbsp;", "").strip() == "":
            continue  # 화면을 비우는 빈 자막
        start_ms = int(start_match.group(1)) if start_match else None
        end_ms = None
        for later in found[order + 1 :]:
            later_start = _SMI_START.search(later.group(1))
            if later_start:
                end_ms = int(later_start.group(1))
                break
        leading = body[: len(body) - len(body.lstrip())]
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_millis_to_hms(start_ms) if start_ms is not None else "",
                end=_millis_to_hms(end_ms) if end_ms is not None else "",
                text=text,
                speaker=_extract_speaker(text),
                original_text=text,
                raw_prefix=sync_tag + leading + para.group(1),
                raw_suffix=body[len(leading) + len(para.group(1)) + len(text) :],
            )
        )
    return entries


def write_smi(entries: list[SubtitleEntry], path: Path, original: Path) -> None:
    """원본을 그대로 두고 대사 텍스트만 갈아 끼운다.

    SAMI는 머리말에 CSS 스타일 정의가 들어가고 우리가 다루지 않는 태그도 많다.
    통째로 다시 쓰지 않고 원문에서 대사 부분만 바꾸는 편이 안전하다.
    """
    raw = Path(original).read_text(encoding="utf-8-sig", errors="replace")
    for entry in entries:
        old = (entry.raw_prefix or "") + (entry.original_text or entry.text)
        new = (entry.raw_prefix or "") + entry.text
        if old != new and old in raw:
            raw = raw.replace(old, new, 1)
    Path(path).write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------- ASS / SSA

_ASS_DIALOGUE = re.compile(r"^(Dialogue:\s*(?:[^,]*,){9})(.*)$")


def parse_ass(path: Path) -> list[SubtitleEntry]:
    """(Advanced) SubStation Alpha를 읽는다.

    Dialogue 줄의 10번째 필드부터가 대사다. 그 앞의 레이어·시각·스타일·여백 필드와
    [Script Info]/[V4+ Styles] 절은 전부 보존한다. 대사 안의 오버라이드 태그
    ({\\i1} 등)는 텍스트의 일부로 그대로 둔다 — 우리가 판단할 대상이 아니다.
    줄바꿈은 ASS 관례대로 \\N이므로 교정 중에만 실제 줄바꿈으로 바꾼다.
    """
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    entries: list[SubtitleEntry] = []
    for line in raw.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped) :]
        match = _ASS_DIALOGUE.match(stripped)
        if not match:
            continue
        fields = stripped.split(",")
        text = match.group(2).replace("\\N", "\n")
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_to_hms(fields[1]) if len(fields) > 2 else "",
                end=_to_hms(fields[2]) if len(fields) > 2 else "",
                text=text,
                speaker=_extract_speaker(text.splitlines()[0] if text else ""),
                raw_prefix=match.group(1),
                raw_suffix=newline,
                original_text=text,
            )
        )
    return entries


def write_ass(entries: list[SubtitleEntry], path: Path, original: Path) -> None:
    raw = Path(original).read_text(encoding="utf-8-sig", errors="replace")
    for entry in entries:
        old_text = (entry.original_text or entry.text).replace("\n", "\\N")
        new_text = entry.text.replace("\n", "\\N")
        old = (entry.raw_prefix or "") + old_text
        new = (entry.raw_prefix or "") + new_text
        if old != new and old in raw:
            raw = raw.replace(old, new, 1)
    Path(path).write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------- SBV (YouTube)

_SBV_TIME = re.compile(r"^(\d+:\d{2}:\d{2}\.\d{3}),(\d+:\d{2}:\d{2}\.\d{3})$")


def parse_sbv(path: Path) -> list[SubtitleEntry]:
    """YouTube 자막(.sbv). 타임코드 두 개를 쉼표로 잇고 다음 줄부터 대사다."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    entries: list[SubtitleEntry] = []
    for block in raw.split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        match = _SBV_TIME.match(lines[0].strip())
        if not match:
            continue
        text = "\n".join(lines[1:])
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_to_hms(match.group(1)),
                end=_to_hms(match.group(2)),
                text=text,
                speaker=_extract_speaker(lines[1].strip()),
                raw_prefix=lines[0].strip() + "\n",
                raw_suffix="\n\n",
            )
        )
    return entries


def write_sbv(entries: list[SubtitleEntry], path: Path) -> None:
    Path(path).write_text(_rebuild(entries).rstrip("\n") + "\n", encoding="utf-8")


# ---------------------------------------------------------------- TTML / DFXP

_TTML_P = re.compile(r"(<p\b[^>]*>)(.*?)(</p>)", re.IGNORECASE | re.DOTALL)
_TTML_ATTR = re.compile(r'\b(begin|end)\s*=\s*"([^"]*)"', re.IGNORECASE)


def _ttml_time(value: str) -> str:
    """TTML 시각(00:00:01.000 또는 1.5s)을 HH:MM:SS,mmm으로."""
    value = value.strip()
    if value.endswith("s") and ":" not in value:
        try:
            return _millis_to_hms(int(float(value[:-1]) * 1000))
        except ValueError:
            return ""
    return _to_hms(value)


def parse_ttml(path: Path) -> list[SubtitleEntry]:
    """TTML/DFXP(.ttml/.dfxp/.xml). <p> 요소 하나가 자막 한 장이다.

    <br/>는 줄바꿈으로 바꿔 교정하고 저장할 때 되돌린다. 그 밖의 인라인 태그
    (<span> 등)는 텍스트의 일부로 그대로 두고 손대지 않는다.
    """
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    entries: list[SubtitleEntry] = []
    for match in _TTML_P.finditer(raw):
        attrs = dict((key.lower(), value) for key, value in _TTML_ATTR.findall(match.group(1)))
        text = re.sub(r"<br\s*/?>", "\n", match.group(2), flags=re.IGNORECASE).strip()
        if not text:
            continue
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_ttml_time(attrs.get("begin", "")),
                end=_ttml_time(attrs.get("end", "")),
                text=text,
                speaker=_extract_speaker(text.splitlines()[0]),
                raw_prefix=match.group(1),
                raw_suffix=match.group(3),
                original_text=text,
            )
        )
    return entries


def write_ttml(entries: list[SubtitleEntry], path: Path, original: Path) -> None:
    raw = Path(original).read_text(encoding="utf-8-sig", errors="replace")
    for entry in entries:
        old_inner = (entry.original_text or entry.text).replace("\n", "<br/>")
        new_inner = entry.text.replace("\n", "<br/>")
        if old_inner == new_inner:
            continue
        old = (entry.raw_prefix or "") + old_inner
        if old in raw:
            raw = raw.replace(old, (entry.raw_prefix or "") + new_inner, 1)
    Path(path).write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------- SubViewer (.sub)

_SUBVIEWER_TIME = re.compile(r"^(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2})$")


def parse_subviewer(path: Path) -> list[SubtitleEntry]:
    """SubViewer(.sub). 타임코드 줄 다음에 대사가 오고, 줄바꿈은 [br]다."""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    entries: list[SubtitleEntry] = []
    for block in raw.split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        match = _SUBVIEWER_TIME.match(lines[0].strip())
        if not match:
            continue
        text = "\n".join(lines[1:]).replace("[br]", "\n")
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start=_to_hms(match.group(1)),
                end=_to_hms(match.group(2)),
                text=text,
                speaker=_extract_speaker(text.splitlines()[0] if text else ""),
                raw_prefix=lines[0].strip() + "\n",
                raw_suffix="\n\n",
            )
        )
    return entries


def write_subviewer(entries: list[SubtitleEntry], path: Path) -> None:
    body = "".join(
        (entry.raw_prefix or "") + entry.text.replace("\n", "[br]") + (entry.raw_suffix or "")
        for entry in entries
    )
    Path(path).write_text(body.rstrip("\n") + "\n", encoding="utf-8")
