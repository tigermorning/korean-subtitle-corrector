"""사전 근거로 단어 하나를 판정하는 술어(述語)들.

`docs/DESIGN_PRINCIPLES.md`의 원리 1(조각 대조) 억제 로직이 여기 모인다 —
"이 토막을 오류로 판정하기 전에, 그것을 포함하는 최대 사전-유효 구간이 있는가".
"""

from ..dictionary import word_exists
from .text_utils import _syllable_run_len

# 국가/지역명 뒤에 붙어 "그 나라의 -" 뜻을 만드는 생산적 접미사(한자어
# 軍/人/語). 조합 자체가 사전에 개별 표제어로 없어도(예: "영국군"은 없지만
# "미군"/"독일군"은 있음 — 사전 등재가 우연히 들쭉날쭉할 뿐, 국가명+이
# 접미사 결합은 규칙적으로 항상 만들 수 있는 정상적인 표현이다), 접미사를
# 뗀 나머지가 실제 사전 단어(주로 국가/지역명)면 신조어·오탈자가 아니라
# 정상적인 파생어로 본다.
_PRODUCTIVE_DEMONYM_SUFFIXES = ("군", "인", "어")


def _is_productive_demonym_compound(word: str) -> bool:
    for suffix in _PRODUCTIVE_DEMONYM_SUFFIXES:
        if len(word) > len(suffix) and word.endswith(suffix) and word_exists(word[: -len(suffix)]):
            return True
    return False


def _is_action_noun(noun_lemma: str) -> bool:
    """명사가 동작성(행위·작용을 나타내는 성질)인지 확인한다 — "명사+하다"가
    사전에 등재되어 있으면 그 행위 자체를 가리키는 동사가 성립한다는
    뜻이므로 동작성 명사로 본다(번역가 교육자료 "동사/접사 구분법" 참고).

    이 판단은 "받다"가 그 명사 뒤에서 접사로 항상 붙어 써야 하는지
    확인하는 데 쓰인다 — "호출받다", "사랑받다", "상처받다"처럼 동작성
    명사+받다 조합 자체는 개별 표제어로 사전에 등재되어 있지 않은 경우가
    많아(교육자료의 예시 단어들도 그렇다) 사전 등재 여부만으로는 판단할
    수 없다. 반면 구체적 사물 명사(상, 만점 등)+받다는 "받다"가 독립된
    동사("받다"='건네받다')로 띄어 써야 하는데, 이런 사물 명사는 보통
    "하다"를 붙일 수 없다("*상하다"는 무관한 동형이의어 — '상처 나다/
    부패하다'라는 뜻).
    """
    return word_exists(noun_lemma + "하다")


# "받다"는 동작성 명사가 아니어도 피동 의미(누군가·무언가로부터 그 상태를
# 겪게 됨)가 있으면 접사로 붙는다(번역가 교육자료 추가 조건). "스트레스"는
# "스트레스하다"라는 말 자체가 없어 _is_action_noun()으로는 못 걸러내는
# 대표 사례라 별도 목록으로 관리한다 — "피동 의미가 있다"는 사전 API로
# 기계적으로 확인할 방법이 없어, 검증된 사례를 하나씩 추가하는 방식으로
# 다룬다(common_errors.py의 다른 목록들과 같은 방식).
_PASSIVE_ONLY_BATDA_NOUNS = {"스트레스"}


# 된소리(경음) 초성 변환: ㄱ→ㄲ, ㄷ→ㄸ, ㅂ→ㅃ, ㅅ→ㅆ, ㅈ→ㅉ (초성 인덱스 기준).
_TENSE_CHOSEONG = {0: 1, 3: 4, 7: 8, 9: 10, 12: 13}


def _tensified_headword_variant(word: str) -> str | None:
    """word의 어느 한 음절 초성을 된소리로 바꾼 형태가 표준국어대사전/우리말샘
    표제어이면 그 형태를 돌려준다 (예: '빤스'→'빤쓰'). '빤쓰'처럼 구어형이
    사전에 등재돼 있으면, 그 말을 외래어 표기('팬츠')로 자동 교정하지 않고
    말투 보존 여부를 사람이 정하도록 플래그하는 근거가 된다. 그런 변이가
    없으면(예: '초코렛') None."""
    for i, ch in enumerate(word):
        code = ord(ch)
        if not (0xAC00 <= code <= 0xD7A3):
            continue
        syllable = code - 0xAC00
        cho = syllable // 588
        if cho in _TENSE_CHOSEONG:
            tense = 0xAC00 + _TENSE_CHOSEONG[cho] * 588 + (syllable % 588)
            variant = word[:i] + chr(tense) + word[i + 1 :]
            if variant != word and word_exists(variant):
                return variant
    return None


def _is_reduplication(word: str) -> bool:
    """'건숭건숭'(사전 표제어 첩어)처럼 같은 요소가 반복된 형태는 외래어 음차가
    아니므로 미등록어 플래그에서 제외한다.
    - 완전 반복(word == 단위*n): 첩어/의성·의태어로 본다.
    - 사전 표제어의 반복 + 짧은 조사·서술격 꼬리(2음절 이하): 첩어로 본다
      (예: kiwi가 '건숭건숭이야'를 '건숭건숭이'(NNG)로 묶는 경우)."""
    n = len(word)
    if n < 2:
        return False
    for unit_len in range(1, n // 2 + 1):
        unit = word[:unit_len]
        if n % unit_len == 0 and unit * (n // unit_len) == word:
            return True
    for unit_len in range(1, n // 2 + 1):
        unit = word[:unit_len]
        if word.startswith(unit * 2) and word_exists(unit) and (n - 2 * unit_len) <= 2:
            return True
    return False


def _is_native_compound(word: str) -> bool:
    """word가 두 개의 사전 표제어가 이어 붙은 고유어 합성어인지 확인한다
    (예: '김치'+'찌갯집'='김치찌갯집'). 이런 말은 외래어 음차가 아니므로
    미등록어(외국어) 플래그 대상이 아니다. 각 조각은 2글자 이상이어야 한다
    (한 글자 조사·접사와의 우연한 일치를 피하려고)."""
    for k in range(2, len(word) - 1):
        if word_exists(word[:k]) and word_exists(word[k:]):
            return True
    return False


def _covered_by_larger_dictionary_unit(text: str, tokens: list, i: int) -> bool:
    """토큰 tokens[i]가 단독으론 표제어가 아니어도, 그것을 포함하는 '더 큰
    사전-유효 단위'의 조각이면 True. 미등록어(외국어) 오탐의 근본 원인인
    '조각 대조'(docs/DESIGN_PRINCIPLES.md 원리 1)를 막는 공유 가드다. kiwi가
    사전 표제어를 조각내는 경우들을 사전·규범 근거로만 판정한다(확률적 추측 없음):
    - 첩어('건숭건숭')·의성어('콸콸콸') 등 반복 형태
    - 두 표제어가 결합한 고유어 합성어('김치'+'찌갯집')
    - 된소리 구어형이 표제어인 경우('빤스'→'빤쓰'; 말투는 check_colloquial_loanword)
    - 미등록 명사가 바로 뒤 용언과 합쳐 표제어를 이루는 경우('얄짤'+'없다'='얄짤없다')
    """
    t = tokens[i]
    lemma = t.lemma
    if _is_reduplication(lemma):
        return True
    if _is_native_compound(lemma):
        return True
    if _tensified_headword_variant(t.form):
        return True
    if len(t.form) == 1 and _syllable_run_len(text, t.start, t.form) >= 2:
        return True
    if t.tag == "NNG" and i + 1 < len(tokens):
        nxt = tokens[i + 1]
        if nxt.tag.startswith(("VA", "VV")) and nxt.start == t.start + t.len:
            if word_exists(t.form + nxt.lemma):
                return True
    return False


def _is_verb_stem_mistagged_as_noun(tokens, i: int) -> bool:
    """tokens[i]가 명사로 태깅됐지만 실은 용언 어간인지 사전으로 확인한다.

    kiwi는 잘 쓰이지 않는 용언 어간을 명사(NNG)로 태깅하는 일이 있다. 2026-08-02
    실사용에서 '이제 여기서 덖는 겁니까'의 '덖'이 NNG로 잡혀 '덖'을 단독으로
    조회했고, 사전에 없으니 미등록어로 플래그됐다. 그런데 바로 뒤에 관형사형 어미
    '는'이 붙어 있고 `word_exists('덖다')`는 참이다 — 즉 **확인할 방법이 있는데
    확인하지 않아서** 난 오탐이다.

    판정은 결정론적이다: 명사 바로 뒤에 어미가 붙어 있으면(명사에는 어미가 붙지
    않는다) 그 명사를 어간으로 보고 '어간+다'를 사전에 조회한다. 등재돼 있으면
    미등록어가 아니다. 사전이 kiwi의 통계적 태깅보다 권위 있는 근거라는, 이
    프로젝트의 기존 원칙과 같다.
    """
    if i + 1 >= len(tokens):
        return False
    nxt = tokens[i + 1]
    if not nxt.tag.startswith("E"):
        return False
    # 어간과 어미가 붙어 있어야 한다(사이에 다른 형태소가 끼면 별개 어절이다).
    if nxt.start != tokens[i].start + tokens[i].len:
        return False
    return bool(word_exists(tokens[i].form + "다"))


def is_hada_stem(tokens, token) -> bool:
    """token 바로 뒤에 '하'(XSA/XSV)가 붙어 있고, 그 결합형이 사전 표제어인지.

    '힙하다'·'쿨하다'처럼 외래어 어근에 '-하다'가 붙어 한 낱말이 된 경우, 그 어근은
    외래어 표기 교정 대상이 아니다. 결합형이 사전에 등재됐는지까지 확인해 근거로 삼는다.
    """
    for i, candidate in enumerate(tokens):
        if candidate is not token:
            continue
        if i + 1 >= len(tokens):
            return False
        nxt = tokens[i + 1]
        if nxt.tag not in ("XSA", "XSV") or nxt.start != token.start + token.len:
            return False
        return word_exists(token.form + "하다")
    return False


# 한 어절 안에서 명사끼리 붙어 복합어를 이루는 태그.
_COMPOUND_NOUN_TAGS = ("NNG", "NNP", "SL")


def _inside_unknown_compound(text: str, tokens, token) -> bool:
    """이 외래어 토큰이 **사전에 없는 복합어의 조각**인지 — 맞으면 자동 반영하지 않는다.

    `매직블럭 제품을 샀다`에서 kiwi는 `매직`(NNP)+`블럭`(NNG)으로 쪼갠다. 그러면
    조각 `블럭`만 보고 `블록`으로 고쳐 **상표 이름이 조용히 바뀐다**(2026-08-05
    사용자 지적: "브랜드 명칭은 전부 한국 지사 공식 명칭을 확인해 줘야 한다").

    복합어 전체(`매직블럭`)가 사전에 없다는 것은 이 도구가 그 말이 무엇인지 모른다는
    뜻이다 — 상표일 수도, 신조어일 수도 있다. 모르는 말의 **일부만** 규칙으로 고치는
    것은 `docs/DESIGN_PRINCIPLES.md` 원리 1(조각 대조)이 금지하는 바로 그 동작이다.
    자동 반영 대신 확인 플래그로 넘겨 사람이 공식 표기를 확인하게 한다.

    조사·어미가 붙은 것은 복합어가 아니다(`초코렛이라도`의 `이`는 VCP) — 붙어 있는
    **명사**가 있을 때만 이 조건이 성립한다.
    """
    for i, candidate in enumerate(tokens):
        if candidate is not token:
            continue
        start, end = token.start, token.start + token.len
        left = tokens[i - 1] if i > 0 else None
        right = tokens[i + 1] if i + 1 < len(tokens) else None
        if left is not None and left.tag in _COMPOUND_NOUN_TAGS and left.start + left.len == start:
            start = left.start
        if right is not None and right.tag in _COMPOUND_NOUN_TAGS and right.start == end:
            end = right.start + right.len
        if (start, end) == (token.start, token.start + token.len):
            return False  # 붙어 있는 명사가 없다 — 이 토큰이 곧 낱말이다
        return not word_exists(text[start:end])
    return False
