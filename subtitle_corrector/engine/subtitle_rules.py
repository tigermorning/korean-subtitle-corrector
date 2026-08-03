"""자막 모드 전용 부호 규칙. 일반 글(prose) 모드에서는 하나도 적용하지 않는다.
"""

import re
from .text_utils import _localized_change
from .options import PunctuationStyle, SubtitleMarkers
from .markers import _marker_unit_pattern

# 줄 끝에서 마침표 뒤에 올 수 있는 닫는 부호. 마침표 뒤에 이 부호(와 공백)만 남았으면
# 문장이 이어지는 것이 아니라 줄 끝 마침표다(2026-08-03 사용자 제공 자막에서 발견:
# '"지영아, 나는 너를 좋아해. "'가 '좋아해, "'로 바뀌었다).
_CLOSING_MARKS = "\"'’”)]}》›"


def _is_sentence_period(text: str, i: int) -> bool:
    """text[i]의 '.'가 문장 종결 마침표인지 판정한다(소수점 3.14, 말줄임표
    ... 제외)."""
    if i < 0 or i >= len(text) or text[i] != ".":
        return False
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if prev == "." or nxt == ".":
        return False  # 말줄임표(...)의 일부
    if prev.isdigit() and nxt.isdigit():
        return False  # 소수점
    return True


def correct_subtitle_final_period(text: str) -> tuple[str, list[str]]:
    """자막 관례상 '각 행'의 맨 끝(문장 종결) 마침표는 쓰지 않는다 — 정답이
    하나뿐이라 자동으로 제거한다. 여러 줄 자막이면 줄바꿈(\\n)으로 구분되는
    모든 행의 끝 마침표를 각각 제거한다. 소수점·말줄임표는 건드리지 않는다.

    반환값: (마침표를 뺀 텍스트, 적용 로그)."""
    new_lines = []
    changed = False
    for line in text.split("\n"):
        stripped = line.rstrip()
        trailing_ws = line[len(stripped) :]
        # 줄 끝이 닫는 따옴표·괄호면 그 앞의 마침표가 줄 끝 마침표다
        # ('좋아해. "' -> '좋아해"'). 닫는 부호는 공백 없이 붙여 되돌린다 — 구두점
        # 앞에는 공백을 두지 않는다(2026-08-03 사용자 지정 규칙).
        core = stripped.rstrip(_CLOSING_MARKS + " \t")
        closing = "".join(ch for ch in stripped[len(core) :] if ch not in " \t")
        if (
            core.endswith(".")
            and not core.endswith("..")
            and _is_sentence_period(core, len(core) - 1)
        ):
            new_lines.append(core[:-1] + closing + trailing_ws)
            changed = True
        else:
            new_lines.append(line)
    if not changed:
        return text, []
    corrected_text = chr(10).join(new_lines)
    return corrected_text, [
        f"문장 끝 마침표 제거 (자막): {_localized_change(text, corrected_text)}"
    ]


def correct_subtitle_bracket_spacing(
    text: str, markers: "SubtitleMarkers | None" = None
) -> tuple[str, list[str]]:
    """자막 표시의 띄어쓰기를 관례에 맞춘다(사용자 지정 2026-08-02).

    두 규칙뿐이고 둘 다 정답이 하나라 자동 교정한다:
      1. **표시끼리는 붙여 쓴다.** 자막 위치·화자명·어조 표기가 연달아 오면
         사이에 공백이 없어야 한다 — `{\\an8} [민수]`는 `{\\an8}[민수]`로.
      2. **표시와 말자막 사이는 정확히 한 칸.** 붙어 있거나 여러 칸이면 한 칸으로
         맞춘다 — `[민수]안녕`은 `[민수] 안녕`으로.

    표시만 있고 뒤에 대사가 없는 줄(효과음 등)은 건드리지 않는다. 어떤 부호를 쓰는지는
    작업마다 다르므로 설정에서 받은 것만 표시로 본다.

    반환값: (교정된 텍스트, 적용 로그)."""
    unit = _marker_unit_pattern(markers)
    if not unit:
        return text, []

    joined = re.sub(rf"({unit})[ \t]+(?={unit})", r"\1", text)  # 규칙 1
    spaced = re.sub(rf"({unit})[ \t]*(?=[^\s])", r"\1 ", joined)  # 규칙 2
    # 규칙 2는 표시 뒤 모든 비공백에 한 칸을 넣으므로, 규칙 1로 붙여 놓은 표시
    # 경계까지 다시 벌어진다. 표시가 이어지는 자리만 도로 붙인다.
    corrected = re.sub(rf"({unit})[ \t]+(?={unit})", r"\1", spaced)

    if corrected == text:
        return text, []
    logs = []
    if joined != text:
        logs.append(
            f"연달아 오는 자막 표시 사이 공백 제거 (자막): {_localized_change(text, joined)}"
        )
    if corrected != joined:
        logs.append(
            f"자막 표시와 대사 사이 한 칸 띄움 (자막): {_localized_change(joined, corrected)}"
        )
    return corrected, logs


def correct_subtitle_internal_period(text: str) -> tuple[str, list[str]]:
    """자막에서 한 줄에 두 문장이 이어질 때, 문장 사이의 마침표는 쉼표(,)로
    바꾼다(자막 관례, 사용자 지정 2026-08-02). 문장 종결 마침표 뒤에 공백을 두고
    다른 문장이 이어지는 지점만 대상이다 — 줄 맨 끝 마침표는
    correct_subtitle_final_period()가 따로 제거하고, 소수점(3.14)과
    말줄임표(...)는 _is_sentence_period()가 걸러 낸다.

    예전에는 확인 플래그로만 제안했으나, 자막에서는 이 자리에 쉼표를 쓰는 것이
    정답 하나로 정해져 있어 자동 교정으로 올렸다.

    반환값: (쉼표로 바꾼 텍스트, 적용 로그)."""
    positions = []
    for i, ch in enumerate(text):
        if ch != "." or not _is_sentence_period(text, i):
            continue
        nxt = text[i + 1] if i + 1 < len(text) else ""
        # 뒤에 남은 것이 닫는 따옴표·괄호뿐이면 문장이 이어지는 것이 아니라 줄 끝
        # 마침표다 — correct_subtitle_final_period()가 지운다. 여기서 쉼표로 바꾸면
        # '좋아해. "'가 '좋아해, "'가 된다(2026-08-03 사용자 보고).
        if nxt == " " and text[i + 1 :].strip().strip(_CLOSING_MARKS):
            positions.append(i)
    if not positions:
        return text, []
    drop = set(positions)
    fixed = "".join("," if i in drop else ch for i, ch in enumerate(text))
    return fixed, [f"문장 사이 마침표를 쉼표로 (자막): {_localized_change(text, fixed)}"]


_STRAIGHT_TO_CURLY_OPEN = {'"': "“", "'": "‘"}


_STRAIGHT_TO_CURLY_CLOSE = {'"': "”", "'": "’"}


_CURLY_TO_STRAIGHT = {"“": '"', "”": '"', "‘": "'", "’": "'"}


def correct_subtitle_quotes(text: str, style: PunctuationStyle | None = None) -> tuple[str, list[str]]:
    """따옴표를 지정한 표기 방식으로 통일한다.

    half(기본): 둥근따옴표를 곧은따옴표로 바꾼다. 어느 쪽이 여는 것인지 판단할 필요가
    없어 안전하다.
    full: 곧은따옴표를 둥근따옴표로 바꾼다. 여는 쪽인지 닫는 쪽인지는 **앞 글자**로
    정한다 — 줄 시작이거나 앞이 공백·여는 괄호면 여는 따옴표, 그 밖에는 닫는 따옴표.
    이건 추측이 아니라 표기 관례를 그대로 옮긴 것이다.
    """
    style = style or PunctuationStyle()
    if style.quotes == "half":
        fixed = "".join(_CURLY_TO_STRAIGHT.get(ch, ch) for ch in text)
    else:
        out = []
        for i, ch in enumerate(text):
            if ch in _STRAIGHT_TO_CURLY_OPEN:
                prev = text[i - 1] if i else ""
                opening = (not prev) or prev.isspace() or prev in "([{“‘"
                out.append((_STRAIGHT_TO_CURLY_OPEN if opening else _STRAIGHT_TO_CURLY_CLOSE)[ch])
            else:
                out.append(ch)
        fixed = "".join(out)
    if fixed == text:
        return text, []
    return fixed, [f"따옴표 표기 통일 (자막): {_localized_change(text, fixed)}"]


# 말줄임표. 한글 맞춤법은 가운뎃점 여섯(……)을 원칙으로 하고 셋(…)·마침표
# 여섯(......)·셋(...)을 허용하지만, 이 도구의 자막 표기는 온점 세 개로
# 통일한다(사용자 지정 2026-08-02).
_ELLIPSIS_CHAR_RE = re.compile(r"…+")


_ELLIPSIS_DOTS_RE = re.compile(r"\.{4,}")


def correct_subtitle_ellipsis(
    text: str, style: "PunctuationStyle | None" = None
) -> tuple[str, list[str]]:
    """말줄임표를 온점 세 개(...)로 통일한다.

    바꾸는 것은 두 가지뿐이다: 말줄임표 문자(…, 연속이면 하나로)와 온점 네 개
    이상(......). 온점 하나·둘은 건드리지 않는다 — 하나는 마침표이고, 둘은
    말줄임표로 단정할 근거가 없어 사람이 볼 영역이다.

    반환값: (통일된 텍스트, 적용 로그)."""
    style = style or PunctuationStyle()
    if style.ellipsis == "char":
        # 온점 세 개 이상을 한 글자짜리 말줄임표로 모은다.
        fixed = re.sub(r"\.{3,}", "…", text)
        fixed = _ELLIPSIS_CHAR_RE.sub("…", fixed)
    else:
        fixed = _ELLIPSIS_CHAR_RE.sub("...", text)
        fixed = _ELLIPSIS_DOTS_RE.sub("...", fixed)
    if fixed == text:
        return text, []
    # 무엇이 어떻게 바뀌었는지 함께 남긴다. '…'(U+2026)는 폰트에 따라 '...'와
    # 구별되지 않아, 결과만 보면 왜 고쳤는지 알 수 없다 — 2026-08-02 사용자가
    # "이미 온점 세 개인데 왜 로그가 뜨냐"고 물은 지점이다.
    return fixed, [f"말줄임표를 온점 세 개로 (자막): {_localized_change(text, fixed)}"]
