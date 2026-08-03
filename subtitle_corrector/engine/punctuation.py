"""문서 종류와 무관하게 적용하는 구두점 규칙 — 감탄사·호격 뒤 쉼표.
"""

from ..dictionary import word_exists
from ..report import FlagItem
from .text_utils import _hangul_run_bounds, _localized_change
from .kiwi_adapter import _has_determiner_reading, _is_punct_token, _kiwi

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
                f"'{joined_form}'이고, '{tokens[i].form}'이 '그런데/생각났는데'의 뜻이면 "
                f"쉼표를 넣어 '{comma_form}'입니다. 표기만으로 갈리지 않아 문맥 확인이 "
                "필요합니다(사전에 실려 있지 않으나 띄어 쓸 근거도 없다는 국립국어원 답변)."
            ),
        )
    return None
