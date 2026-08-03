"""순수 문자열·한글 음절 도구. 사전도 형태소 분석기도 쓰지 않는 최하위 계층이다.
"""

import difflib
import re

# 자막의 "[이름/상황]" 같은 브래킷 표기는 실제 문장이 아니라 화자·상황을
# 표시하는 관례적 메타 표기라, 한글 맞춤법이 다루는 대상이 아니다. 이
# 안의 내용(예: "작게", "스피커")은 맞춤법·띄어쓰기 검사 대상에서 뺀다.
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")


def _bracket_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _BRACKET_TAG_RE.finditer(text)]


def _inside_any_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _word_bounds(text: str, pos: int) -> tuple[int, int]:
    """pos를 포함하는 어절(공백으로 끊기는 덩어리)의 [시작, 끝)."""
    start = pos
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    end = pos
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def _localized_change(original: str, corrected: str) -> str:
    """한 줄 전체를 다시 적는 대신, 실제로 바뀐 부분만 추려 '원문조각 -> 교정조각'
    형태로 돌려준다. 긴 대사에서 어디가 자동 교정됐는지 한눈에 보이게 하기 위함
    (앞뒤로 안 바뀐 부분이 있으면 '…'로 표시). 공통 접두/접미를 제거해 최소
    변경 구간만 남긴다. 짧은 줄은 전체를 보여주는 편이 더 명확하므로, 긴 대사
    (25자 초과)에서만 축약한다."""
    if len(original) <= 25:
        return f"{original} -> {corrected}"
    i = 0
    n = min(len(original), len(corrected))
    while i < n and original[i] == corrected[i]:
        i += 1
    jo, jc = len(original), len(corrected)
    while jo > i and jc > i and original[jo - 1] == corrected[jc - 1]:
        jo -= 1
        jc -= 1
    # 변경 구간에 앞뒤 맥락 몇 글자를 붙인다 — 순수 공백 삽입(예: '할만하다'→
    # '할 만하다')처럼 바뀐 부분만 떼면 무의미해지는(∅→' ') 경우를 막고,
    # 어느 단어에서 바뀌었는지 보이게 하기 위함이다.
    margin = 3
    ci = max(0, i - margin)
    cjo = min(len(original), jo + margin)
    cjc = min(len(corrected), jc + margin)
    pre = "…" if ci > 0 else ""
    suf = "…" if cjo < len(original) else ""
    return f"{pre}{original[ci:cjo]}{suf} -> {pre}{corrected[ci:cjc]}{suf}"


def _has_batchim(syllable: str) -> bool:
    """한글 음절 하나에 받침이 있는지 확인한다(유니코드 완성형 한글은
    코드포인트 = 0xAC00 + (초성*21+중성)*28+종성 공식을 따르므로, 그 값을
    28로 나눈 나머지가 0이면 받침이 없다는 뜻)."""
    if not syllable:
        return False
    code = ord(syllable[-1])
    if not (0xAC00 <= code <= 0xD7A3):
        return False
    return (code - 0xAC00) % 28 != 0


def _force_span(suggested: str, original_span: str, other_span: str) -> str:
    """suggested 안에서 other_span(kiwi가 밀어붙이려는 형태)을 original_span
    (실제로 채택된, 정답으로 확정된 형태)으로 되돌린다."""
    if other_span != original_span:
        return suggested.replace(other_span, original_span)
    return suggested


def _surface_span(text: str, start: int, end: int) -> str:
    """[start, end) 구간을 양쪽 어절 경계까지 넓혀 돌려준다.

    토큰 경계는 형태소 단위라 그대로 보여주면 '덤벼들어 보'처럼 어절이 잘린
    조각이 나온다. 사람이 읽는 안내문에는 어절 전체('덤벼들어 보아라')가 보여야
    어디를 말하는지 알 수 있다.
    """
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return text[start:end]


def _syllable_run_len(text: str, pos: int, ch: str) -> int:
    """text의 pos 위치를 포함해 같은 글자 ch가 연달아 몇 번 반복되는지 센다."""
    if pos < 0 or pos >= len(text) or text[pos] != ch:
        return 1
    left = pos
    while left > 0 and text[left - 1] == ch:
        left -= 1
    right = pos
    while right + 1 < len(text) and text[right + 1] == ch:
        right += 1
    return right - left + 1


def _inserted_space_ranges(original: str, suggested: str) -> list[tuple[int, int, int]]:
    """kiwi.space()가 원문에 없던 공백을 새로 끼워 넣은 지점들을 찾는다.

    반환값: (원문 상의 삽입 지점, suggested 상의 삽입 시작, suggested 상의
    삽입 끝) 목록. 원문에 이미 있던 공백을 다른 자리로 옮기는 경우는 다루지
    않는다 — 우리가 막으려는 건 "원래 붙어 있던 걸 근거 없이 갈라놓는 것"
    뿐이고, 이미 애매한 기존 공백 배치는 그대로 사람 확인으로 넘긴다."""
    matcher = difflib.SequenceMatcher(a=original, b=suggested, autojunk=False)
    points = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert" and i1 == i2 and suggested[j1:j2] and suggested[j1:j2].strip() == "":
            points.append((i1, j1, j2))
    return points


def _removed_space_points(original: str, suggested: str) -> list[tuple[int, int]]:
    """kiwi.space()가 원문에 이미 있던 공백을 지워버린(두 단어를 붙여버린)
    지점들을 찾는다. _inserted_space_ranges()와 반대 방향이다.

    반환값: (원문 상의 공백 위치, suggested 상에서 다시 공백을 끼워 넣어야
    할 위치) 목록."""
    matcher = difflib.SequenceMatcher(a=original, b=suggested, autojunk=False)
    points = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete" and original[i1:i2] == " ":
            points.append((i1, j1))
    return points


def _hangul_run_bounds(text: str, pos: int) -> tuple[int, int]:
    """text의 pos 위치를 포함하는, 공백 없이 이어진 한글 글자 런의 [시작, 끝)."""
    def is_hangul(ch: str) -> bool:
        return "가" <= ch <= "힣"

    left = pos
    while left > 0 and is_hangul(text[left - 1]):
        left -= 1
    right = pos
    while right < len(text) and is_hangul(text[right]):
        right += 1
    return left, right


# 앞에 공백을 둘 수 없는 부호. 문장부호(마침표·물음표·느낌표·쉼표·말줄임표)와 닫는
# 짝(따옴표·괄호)이다. **문맥과 무관한 규칙**이므로(2026-08-03 사용자 지정: "마침표,
# 물음표, 느낌표, 따옴표 모두 띄어쓰기 없이 사용") 판정 없이 늘 적용한다. 여는 짝
# (여는 따옴표·괄호)은 앞에 공백이 오는 것이 정상이라 넣지 않는다.
_NO_SPACE_BEFORE = ".,!?…)]}’”》›"


def _strip_space_before_punctuation(text: str) -> str:
    """구두점 바로 앞의 공백을 없앤다('지랄 !' -> '지랄!').

    kiwi의 띄어쓰기 제안은 문장부호를 하나의 토막으로 보아 앞에 공백을 넣자고 할 때가
    있다. 어느 규범도 그렇게 쓰지 않으므로 제안 단계에서 걸러 낸다.
    """
    out = []
    for ch in text:
        if ch in _NO_SPACE_BEFORE:
            while out and out[-1] in " 	":
                out.pop()
        out.append(ch)
    return "".join(out)
