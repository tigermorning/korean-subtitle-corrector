"""문서 종류와 무관하게 적용하는 구두점·표기 규칙 — 감탄사·호격 뒤 쉼표, 쌍점
띄어쓰기, '&' 기호, 단위 대소문자.
"""

import re

from ..dictionary import word_exists
from ..report import FlagItem
from .text_utils import _hangul_run_bounds, _josa, _localized_change
from .kiwi_adapter import (
    _has_adnominal_phrase_reading,
    _has_content_word_reading,
    _has_determiner_reading,
    _has_predicate_reading,
    _is_punct_token,
    _kiwi,
)

# 간접인용 축약에서 '그래' 앞에 오는 어미. "말라 그래"는 "말라고 해"의 준말이라
# '그래'가 감탄사가 아니라 인용을 받는 서술어다(2026-08-02 실사용에서 발견).
# kiwi는 문장부호가 붙으면("말라 그래.") 이 '그래'를 IC로 태깅해, 감탄사 규칙이
# "말라, 그래"라는 엉뚱한 쉼표를 넣었다.
_QUOTED_COMMAND_ENDINGS = {"라", "으라", "자", "냐", "마", "래"}


# 표준어 '그래'의 사투리형. kiwi는 이들을 감탄사(IC)로 태깅하지만, 실제로는
# '그렇다/그리하다'의 사투리 활용형(서술어)으로 쓰이는 경우가 많다 — 2026-08-02
# 실사용에서 '어디 있는디 그려?'가 '어디 있는디, 그려?'로 잘못 교정됐다. 표준어
# 감탄사가 아니므로 쉼표 규칙의 대상에서 아예 뺀다.
_DIALECT_AGREEMENT_FORMS = {"그려", "그랴", "기여", "그라", "그자"}


# 사전에 없지만 한 감탄사로 붙여 쓰기로 정한 말. 근거는 온라인가나다 답변이다 —
# "'참나'가 사전에 실려 있지 않은데, 이를 띄어 쓸 근거도 분명하지 않습니다. …
# '참나'가 하나의 감탄사로 쓰인다면 앞으로 사전에 실릴 수도 있다"(사용자 제공,
# 2026-08-03). 띄어 쓸 근거가 없으므로 붙여 쓰는 쪽으로 정했다(사용자 결정).
# 이 목록은 **쉼표를 그 안에 넣지 않기 위한** 것이다. 늘릴 때는 같은 수준의 근거를
# 함께 적을 것 — 사전에 없는 말을 한 단어로 못 박는 결정이라 근거 없이 늘리면 안 된다.
_JOINED_INTERJECTIONS = {"참나"}


def _splits_joined_interjection(text: str, tokens, ic_pos: int) -> bool:
    """감탄사 뒤에 쉼표를 넣으면 한 덩어리로 쓰는 감탄사를 가르는지.

    '참 나 어이없네'는 '참'(IC) 다음이 '나'라서 쉼표 규칙이 '참, 나 어이없네'로
    만들었다. '참나'를 한 감탄사로 보기로 했으므로 그 사이를 가르지 않는다.
    """
    if ic_pos + 1 >= len(tokens):
        return False
    joined = tokens[ic_pos].form + tokens[ic_pos + 1].form
    return joined in _JOINED_INTERJECTIONS


def _is_quoted_command(tokens, ic_pos: int) -> bool:
    """tokens[ic_pos]의 '그래'가 감탄사가 아니라 간접인용 축약의 서술어인지.

    바로 앞이 인용 축약에 쓰이는 어미(-라/-자/-냐 등)일 때만 참이다. 동의의
    '그래'("밥 먹자, 그래")와 형태가 겹치는 경계 사례가 남지만, 애매하면 자동
    수정하지 않는다는 원칙에 따라 쉼표를 넣지 않는 쪽을 택한다 — 안 넣어서 생기는
    손해(사람이 직접 넣음)가 잘못 넣어서 생기는 손해(대사 뜻이 바뀜)보다 작다.
    """
    if tokens[ic_pos].form in _DIALECT_AGREEMENT_FORMS:
        return True  # 사투리 서술어일 수 있어 문맥 없이 쉼표를 넣지 않는다
    if tokens[ic_pos].form not in ("그래", "그러래"):
        return False
    prev = tokens[ic_pos - 1]
    return prev.tag.startswith("E") and prev.form in _QUOTED_COMMAND_ENDINGS


def _inside_headword(text: str, pos: int) -> bool:
    """pos가 사전 표제어 한 단어의 '내부'인지 — 그렇다면 거기를 갈라선 안 된다.

    pos를 사이에 둔 한글 런(공백·문장부호로 끊기는 덩어리)을 통째로 사전에
    조회한다. 런이 표제어면 kiwi가 그 안을 어떻게 쪼갰든 한 단어다.
    """
    if pos <= 0 or pos >= len(text):
        return False
    start, end = _hangul_run_bounds(text, pos - 1)
    if end <= pos:  # pos가 런 바깥(경계)이면 단어 내부가 아니다
        return False
    run = text[start:end]
    return len(run) >= 2 and bool(word_exists(run))


def correct_interjection_vocative_comma(text: str) -> tuple[str, list[str]]:
    """감탄사(IC)와 호격어(체언+호격조사 JKV)는 문장에서 쉼표로 구분한다.
    문맥과 무관하게 규정상 정답이 정해져 있어 자동으로 쉼표를 넣는다:
    - 문장 맨 앞 감탄사 + 내용어: '아이고 어떻기는' → '아이고, 어떻기는'
    - 문장 맨 끝 감탄사(내용어 뒤): '싫다면 뭐' → '싫다면, 뭐'
    - 문장 맨 끝 호격어: '먹어 준희야' → '먹어, 준희야'

    이미 쉼표 등으로 구분돼 있으면 넣지 않는다. '거 참'(IC+IC)처럼 감탄사끼리
    이어진 경우, 감탄사만 있고 내용어가 없는 경우는 대상이 아니다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    if len(tokens) < 2:
        return text, []

    def is_content(tok) -> bool:
        return not _is_punct_token(tok) and tok.tag != "IC"

    def already_delimited_before(pos: int) -> bool:
        j = pos - 1
        while j >= 0 and text[j] == " ":
            j -= 1
        return j < 0 or text[j] in ",.!?…"

    insert_positions = set()

    # 1) 문장 맨 앞 감탄사 + 내용어 → 감탄사 뒤에 쉼표
    if (
        tokens[0].tag == "IC"
        and is_content(tokens[1])
        and tokens[0].form not in _DIALECT_AGREEMENT_FORMS
        and not _has_determiner_reading(text, tokens[0])
        and not _has_content_word_reading(text, tokens[0])
        and not _has_adnominal_phrase_reading(text, tokens[0])
        and not _splits_joined_interjection(text, tokens, 0)
    ):
        pos = tokens[0].start + tokens[0].len
        if pos < len(text) and text[pos - 1] != "," and text[pos] not in ",.!?…":
            insert_positions.add(pos)

    # 문장 맨 끝(문장부호 제외) 토큰 찾기
    last = len(tokens) - 1
    while last >= 0 and _is_punct_token(tokens[last]):
        last -= 1

    if last >= 1:
        lt = tokens[last]
        # 2) 문장 맨 끝 감탄사(내용어 뒤) → 감탄사 앞에 쉼표.
        #    **앞말이 조사면 넣지 않는다.** 조사 뒤는 서술어나 체언이 오는 자리이므로
        #    그 자리의 IC 태그는 오분석이다 — '그건 내 잘못이 아냐'에서 '아냐'
        #    ('아니야'의 준말, 서술어)를 kiwi가 감탄사로 읽어 '잘못이, 아냐'로
        #    쉼표를 넣어 서술어를 잘라 버렸다(2026-08-03 사용자 보고). 보격 조사
        #    '이'(JKC) 뒤라면 '아니다/되다'가 와야 하는 자리라는 것이 규정상 확실하다.
        if (
            lt.tag == "IC"
            and is_content(tokens[last - 1])
            and not tokens[last - 1].tag.startswith("J")
            and not _is_quoted_command(tokens, last)
            and not _has_predicate_reading(text, lt)
        ):
            j = lt.start
            while j > 0 and text[j - 1] == " ":
                j -= 1
            if not already_delimited_before(j):
                insert_positions.add(j)
        # 3) 문장 맨 끝 호격어(체언+JKV) → 호격 체언 앞에 쉼표
        elif lt.tag == "JKV" and last >= 2:
            noun = tokens[last - 1]
            # 호격어는 별개 어절이다. 어절 **중간**에 쉼표를 넣으면 이름이 쪼개진다 —
            # 2026-08-02 실사용에서 '연실아'가 '연,실아'로 잘렸다(kiwi가 '연'을
            # 관형사로, '실'을 명사로 태깅했다). 앞이 공백이거나 줄 시작일 때만 넣는다.
            starts_word = noun.start == 0 or text[noun.start - 1].isspace()
            if noun.tag in ("NNP", "NNG") and is_content(tokens[last - 2]) and starts_word:
                j = noun.start
                while j > 0 and text[j - 1] == " ":
                    j -= 1
                if not already_delimited_before(j):
                    insert_positions.add(j)

    # **쉼표는 어절 경계에만 넣는다.** 이 가드가 없으면 kiwi가 한 어절을 쪼갠
    # 분석을 그대로 믿고 낱말 한가운데를 갈라 버린다 — 2026-08-02 실사용에서
    # '연실아'가 '연,실아'로, '정말 미안햐'가 '정말 미안,햐'로 바뀌었다. 원본을
    # 왜곡하는 유형이라 개별 규칙마다 막지 않고 삽입 지점 전체에 한 번에 건다.
    # (삽입 자리 앞이나 뒤 중 하나는 공백이거나 텍스트 끝이어야 한다.)
    def at_word_boundary(pos: int) -> bool:
        if pos <= 0 or pos >= len(text):
            return True
        return text[pos - 1].isspace() or text[pos].isspace()

    insert_positions = {pos for pos in insert_positions if at_word_boundary(pos)}

    # 사전에 등재된 한 단어 안에는 쉼표를 넣지 않는다. kiwi는 '에라이'(감탄사,
    # 표제어)를 '에라'(IC)+'이'로, '아싸'를 '아'(IC)+'싸'로 쪼개는데, 그 분석을
    # 믿고 쉼표를 넣으면 '에라,이!'라는 없는 말이 된다(2026-08-02 실사용에서 발견).
    # 사전이 kiwi의 통계적 분석보다 권위 있다는 이 프로젝트의 기존 원칙 그대로다.
    insert_positions = {
        pos for pos in insert_positions if not _inside_headword(text, pos)
    }

    if not insert_positions:
        return text, []
    corrected = text
    # 쉼표 뒤에는 한 칸을 띄운다. 어절 중간이 아니라 경계에만 넣으므로 대개 이미
    # 공백이 뒤따르지만, 그렇지 않은 경우를 대비해 명시적으로 보장한다.
    for pos in sorted(insert_positions, reverse=True):
        corrected = corrected[:pos] + "," + corrected[pos:]
    return corrected, [_localized_change(text, corrected)]


def check_joined_interjection_spacing(index: int, text: str) -> FlagItem | None:
    """한 덩어리로 쓰는 감탄사를 띄어 쓴 것을 플래그한다('참 나' -> '참나').

    자동으로 붙이지 않는 이유: 뒤 낱말이 감탄사의 일부인지('참 나 어이없네') 다음
    문장 성분인지('참 나는 그렇게 생각해') 표면으로 갈린다고 단정할 수 없다. 뒤 낱말이
    조사 없이 한 어절로 끝날 때만 후보로 보고, 판단은 사람에게 남긴다.
    """
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 1):
        if tokens[i].tag != "IC":
            continue
        nxt = tokens[i + 1]
        joined = tokens[i].form + nxt.form
        if joined not in _JOINED_INTERJECTIONS:
            continue
        if text[tokens[i].start + tokens[i].len : nxt.start] != " ":
            continue  # 이미 붙어 있다
        end = nxt.start + nxt.len
        if end < len(text) and text[end] not in " ,.!?…":
            continue  # 뒤에 조사·어미가 붙어 있으면 감탄사의 일부로 볼 수 없다
        joined_form = text[: tokens[i].start] + joined + text[nxt.start + nxt.len :]
        comma_form = (
            text[: tokens[i].start + tokens[i].len] + "," + text[tokens[i].start + tokens[i].len :]
        )
        # 자동 적용 후보(suggested_fix)를 일부러 주지 않는다. 두 읽기 중 어느 쪽인지는
        # 문맥이 정하고, 하나를 후보로 내놓으면 리포트 적용 기능이 그쪽으로 굳힌다
        # (2026-08-03 사용자 지정: "헷갈린다면 자동교정하지 말고 플래깅할 것").
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{joined}'(기가 막히고 어이없다는 감탄사)로 쓴 것이면 붙여 써 "
                f"'{joined_form}'이고, '{tokens[i].form}'{_josa(tokens[i].form, '이')} "
                f"'그런데/생각났는데'의 뜻이면 "
                f"쉼표를 넣어 '{comma_form}'입니다. 표기만으로 갈리지 않아 문맥 확인이 "
                "필요합니다(사전에 실려 있지 않으나 띄어 쓸 근거도 없다는 국립국어원 답변)."
            ),
        )
    return None


def check_ambiguous_interjection_comma(index: int, text: str) -> FlagItem | None:
    """감탄사 쉼표를 **자동으로 넣지 못한 자리**를 제안으로 남긴다.

    같은 낱말이 명사·용언으로도 읽히면(kiwi 대안 분석) 쉼표를 자동으로 넣지 않는다 —
    '아이 심장이 선천적으로'가 '아이, 심장이'로 갈라지는 사고를 막기 위한 것이다
    (2026-08-04 사용자 제공 자막 5강). 다만 정말 감탄사인 경우('야 이리 와')도 같은
    조건에 걸리므로, 그냥 버리지 않고 사람이 판단할 후보로 넘긴다.
    """
    tokens = _kiwi.tokenize(text)
    if len(tokens) < 2:
        return None
    first = tokens[0]
    if first.tag != "IC" or _is_punct_token(tokens[1]):
        return None
    if first.form in _DIALECT_AGREEMENT_FORMS:
        return None
    if _has_determiner_reading(text, first) or _splits_joined_interjection(text, tokens, 0):
        return None  # 관형어 읽기·붙여 쓰는 감탄사는 쉼표 자체가 대상이 아니다
    if not (_has_content_word_reading(text, first) or _has_adnominal_phrase_reading(text, first)):
        return None  # 애매하지 않으면 이미 자동으로 넣었다
    position = first.start + first.len
    if position >= len(text) or text[position] in ",.!?…":
        return None
    suggested = text[:position] + "," + text[position:]
    return FlagItem(
        line_index=index,
        original_text=text,
        suggested_fix=suggested,
        reason=(
            f"'{first.form}'{_josa(first.form, '이')} 감탄사라면 뒤에 쉼표를 넣습니다. "
            "같은 표기가 명사·용언으로도"
            " 읽혀(예: '아이 심장이'의 '아이') 자동으로 넣지 않았습니다 — 문맥 확인이"
            " 필요합니다."
        ),
    )


# 한글 맞춤법 문장부호 규정, 쌍점(:): (1) 표제 다음에 자세한 설명·보기를 들 때는
# 앞은 붙이고 뒤는 띄어 쓴다("주제: 맞춤법"). (2) 시와 분, 대비되는 두 대상 등을
# 나타낼 때는 앞뒤를 다 붙여 쓴다("12:30", "3:3"). 두 규정을 가르는 신호는 콜론
# 양옆이 전부 숫자인지 여부다 — 숫자 대 숫자가 아니면 (1), 맞으면 (2)로 본다.
_COLON_DIGIT_GAP = re.compile(r"(?<=\d)[ \t]*:[ \t]*(?=\d)")
# 이 뒤에 (공백을 사이에 두고서라도) 숫자나 한글이 와야 "표제:" 자리로 본다 —
# 그렇지 않으면 이모티콘(':)' , ':D')이나 URL·포트 표기까지 건드리게 된다.
_COLON_SPACE_BEFORE = re.compile(r"[ \t]+:(?=[ \t]*[\d가-힣])")
# 콜론 뒤에 공백을 강제로 넣는 자리는 한글(단어 내용)이 바로 뒤따를 때로 한정한다.
# (?!\d)는 위 숫자:숫자 자리(이미 붙어 있어야 함)를 다시 벌리지 않기 위함이다.
_COLON_NEEDS_SPACE_AFTER = re.compile(r":(?!\d)[ \t]*(?=[가-힣])")


def correct_colon_spacing(text: str) -> tuple[str, list[str]]:
    """쌍점(:) 앞뒤 공백을 문장부호 규정대로 맞춘다.

    - 숫자:숫자(시각 '12:30', 대비 '3:3')는 양옆을 붙인다.
    - 그 외(표제: 설명)는 앞을 붙이고 뒤에 한 칸을 둔다 — 단, 뒤따르는 것이
      한글이 아니면(이모티콘·URL 등) 건드리지 않는다.
    """
    fixed = _COLON_DIGIT_GAP.sub(":", text)
    fixed = _COLON_SPACE_BEFORE.sub(":", fixed)
    fixed = _COLON_NEEDS_SPACE_AFTER.sub(": ", fixed)
    if fixed == text:
        return text, []
    return fixed, [f"쌍점 띄어쓰기: {_localized_change(text, fixed)}"]


# '&'는 한국어 문장부호가 아니다 — 문맥에 따라 '및'(나열)·'겸'(겸직)·쉼표로
# 바꿔 쓴다. 다만 'P&G'·'AT&T'·'H&M'처럼 로마자에 바로 붙어 있으면 그 자체가
# 고유명사(상표명)의 일부이므로 건드리지 않는다 — 어느 쪽으로 바꿀지는 뜻에
# 달려 있어 자동으로 정하지 않고 사람에게 확인만 받는다.
_AMPERSAND = re.compile(r"&")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_HANGUL = re.compile(r"[가-힣]")


def check_ampersand_usage(index: int, text: str) -> FlagItem | None:
    """'&'가 로마자 약칭(상표명 등)이 아니라 한글 문맥에서 접속 기호로
    쓰였으면 확인 플래그를 낸다(예: '감독 & 작가' -> '감독 및 작가')."""
    for m in _AMPERSAND.finditer(text):
        left = text[: m.start()].rstrip(" ")
        right = text[m.end() :].lstrip(" ")
        left_char = left[-1:] or None
        right_char = right[:1] or None
        # 양옆이 전부 로마자에 바로 붙어 있으면(공백 없이) 상표명 약칭으로 본다.
        if (
            left_char and _LATIN_LETTER.match(left_char)
            and right_char and _LATIN_LETTER.match(right_char)
            and text[m.start() - 1] != " "
            and text[m.end() : m.end() + 1] != " "
        ):
            continue
        # 어느 한쪽이라도 한글이면 번역 과정에서 '&'가 그대로 남은 것으로 본다.
        if (left_char and _HANGUL.match(left_char)) or (right_char and _HANGUL.match(right_char)):
            return FlagItem(
                line_index=index,
                original_text=text,
                reason=(
                    "'&'는 한국어 문장부호가 아닙니다 — 뜻에 따라 '및'(나열)·'겸'(겸직)·"
                    "쉼표 중 하나로 바꿔 쓰세요. 로마자 상표명(예: 'P&G')의 일부라면 "
                    "그대로 두세요."
                ),
            )
    return None


# 「국제단위계(SI)」접두어 '킬로'는 10³을 뜻하며 항상 소문자 k다(대문자 K는
# 273.15가 기준인 절대온도 단위 켈빈이다). 자막 번역에서 거리·무게 단위 앞에
# 실수로 대문자를 쓰는 경우(마일→km, 파운드→kg 환산)만 좁혀서 고친다 — 단위
# 표기 전체(바이트 계열의 K/k처럼 관행상 대문자를 쓰는 예외가 있는 자리, §31
# `docs/LOANWORD_TRANSCRIPTION_RULES.md`와 별개 사안)까지 넓히지 않는다.
_UNIT_CASE_FIX = {"Km": "km", "KM": "km", "Kg": "kg", "KG": "kg"}
# 숫자 바로 뒤, 또는 숫자+공백 한 칸 뒤만 대상으로 한다 — 공백 자체는 매치에
# 넣지 않고 유지한다(가변폭 lookbehind를 못 쓰는 대신 두 폭을 나란히 둔다).
_UNIT_CASE_RE = re.compile(r"(?:(?<=\d)|(?<=\d ))(Km|KM|Kg|KG)(?![A-Za-z])")


def correct_unit_case(text: str) -> tuple[str, list[str]]:
    """숫자 뒤에 오는 거리·무게 단위의 '킬로' 대소문자를 소문자로 통일한다
    (Km/KM -> km, Kg/KG -> kg). 숫자 바로 뒤가 아니면(고유명사·이니셜일 수
    있음) 건드리지 않는다."""

    def _fix(m: re.Match) -> str:
        return _UNIT_CASE_FIX[m.group(1)]

    fixed = _UNIT_CASE_RE.sub(_fix, text)
    if fixed == text:
        return text, []
    return fixed, [f"단위 대소문자: {_localized_change(text, fixed)}"]
