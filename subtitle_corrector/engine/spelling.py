"""맞춤법·순화어 검사. 자동 교정하지 않고 플래그만 남긴다 —
사전에 없다는 사실만으로는 무엇이 맞는 표기인지 알 수 없기 때문이다.
"""

from ..dictionary import (
    appears_in_standard_headword,
    get_purified_terms,
    search_kornorms,
    usage_examples,
    word_exists,
)
from ..report import FlagItem
from .text_utils import _bracket_spans, _inside_any_span, _josa
from .kiwi_adapter import _SPELLING_CHECK_TAGS, _kiwi
from .lexicon import (
    _covered_by_larger_dictionary_unit,
    _is_productive_demonym_compound,
    _is_verb_stem_mistagged_as_noun,
)

# 외래어 표기에서 가장 흔하게 갈리는 모음 짝. 같은 소리로 들려 표기만 흔들리는
# 자리라('트레커'/'트래커') 사전에 있는 쪽을 후보로 제시할 근거가 된다. 뜻을 추측하는
# 것이 아니라 **표기 변이형을 사전에 물어보는 것**이므로 이 프로젝트 원칙과 어긋나지
# 않는다 — 다만 자동 교정은 하지 않고 플래그 사유에만 적는다(2026-08-03 사용자 요청).
_VOWEL_CONFUSION_PAIRS = ((1, 5), (3, 7))  # ㅐ↔ㅔ, ㅒ↔ㅖ


def _vowel_variants(word: str) -> list[str]:
    """word에서 모음 한 자리를 혼동 짝으로 바꾼 표기들을 돌려준다."""
    variants = []
    for i, ch in enumerate(word):
        code = ord(ch) - 0xAC00
        if not 0 <= code < 11172:
            continue
        initial, rest = divmod(code, 588)
        vowel, final = divmod(rest, 28)
        for a, b in _VOWEL_CONFUSION_PAIRS:
            if vowel == a:
                swapped = b
            elif vowel == b:
                swapped = a
            else:
                continue
            new_ch = chr(0xAC00 + (initial * 588) + (swapped * 28) + final)
            variants.append(word[:i] + new_ch + word[i + 1 :])
    return variants


def _dictionary_backed_variants(word: str) -> list[str]:
    """word의 표기 변이형 중 **사전에 근거가 있는 것**만 돌려준다.

    근거로 인정하는 것: 단독 표제어(word_exists), 국립국어원 표제어의 구성 요소로
    등장(appears_in_standard_headword — '트래커'는 '지피에스^트래커'로 등재됨),
    외래어 표기 용례(search_kornorms).
    """
    found = []
    for candidate in _vowel_variants(word):
        if candidate in found:
            continue
        if word_exists(candidate) or appears_in_standard_headword(candidate) or search_kornorms(candidate):
            found.append(candidate)
    return found


def _unknown_content_words(text: str) -> list[str]:
    """맞춤법 확인 대상(내용어) 중 진짜 미등록어만 돌려준다. kiwi가 사전 표제어를
    조각내는 경우의 오탐은 _covered_by_larger_dictionary_unit()(원리 1 공유 가드)로
    걸러낸다."""
    brackets = _bracket_spans(text)
    tokens = _kiwi.tokenize(text)
    unknown = []
    for i, t in enumerate(tokens):
        if t.tag not in _SPELLING_CHECK_TAGS:
            continue
        if _inside_any_span(t.start, brackets):
            continue
        lemma = t.lemma
        if word_exists(lemma) or _is_productive_demonym_compound(lemma) or search_kornorms(lemma):
            continue
        if appears_in_standard_headword(lemma):
            continue  # 단독 표제어는 없어도 국립국어원 표제어의 구성 요소로 쓰이는 말
        if _is_verb_stem_mistagged_as_noun(tokens, i):
            continue
        if _covered_by_larger_dictionary_unit(text, tokens, i):
            continue
        unknown.append(lemma)
    return unknown


def check_spelling(index: int, text: str) -> FlagItem | None:
    """사전에 없는 단어는 신조어일 수도, 외국어 음차(이름·지명 등)일 수도
    있어 이 함수만으로는 구분할 수 없다 — 그래서 고치자고 제안하지 않고,
    번역가 교육자료가 권장하는 실제 검증 방법(국립국어원 용례, 발음기호
    사전, 한글라이즈)으로 직접 확인하라고 안내만 한다."""
    unknown = _unknown_content_words(text)
    if not unknown:
        return None

    # 사전에 근거가 있는 표기 변이형이 있으면 후보로 알려 준다('트레커' -> '트래커').
    # "사전에 없다"로 끝내면 번역가가 무엇과 비교해야 하는지 알 수 없다(2026-08-03
    # 사용자 요청). 자동 교정은 하지 않는다 — 어느 쪽이 맞는지는 원어 발음이 정한다.
    hints = []
    suggested_fix = None
    for word in unknown:
        variants = _dictionary_backed_variants(word)
        if not variants:
            continue
        hints.append(
            f"'{word}'{_josa(word, '는')} '{', '.join(variants)}'일 가능성이 있습니다"
            "(사전 근거 있음)"
        )
        if suggested_fix is None and len(variants) == 1:
            suggested_fix = text.replace(word, variants[0], 1)

    reason = (
        f"사전에 없는 단어: {', '.join(unknown)} — 외국어 음차·고유명사일 수 있음. "
        # 음차라면 정답은 원어가 정한다. 아래 칸에 원어를 넣으면 국립국어원 용례로
        # 확정 표기를 찾아 주므로, 세칙을 직접 읽지 않고도 판단할 수 있다(§61).
        f"음차라면 아래 칸에 원어(로마자)를 넣어 '{unknown[0]}'의 국립국어원 확정 표기를 "
        "확인하세요. 용례에 없으면 발음기호(Longman/Collins 등), "
        "한글라이즈(hangulize.org)로 직접 확인해야 합니다. 반복 등장하는 이름·요리명이면 "
        "위쪽의 고유명사/요리명 목록에 추가하면 이후 잘못 쪼개지지 않습니다."
    )
    if hints:
        reason += " " + ". ".join(hints) + "."
    return FlagItem(
        line_index=index,
        original_text=text,
        reason=reason,
        suggested_fix=suggested_fix or "",
        source_lookup_token=unknown[0],
    )


def _usage_note(words: list[str]) -> str:
    """여러 단어에 대해 우리말샘 실제 용례를 모아 플래그 사유에 덧붙일 참고
    문구를 만든다. 번역가가 사전을 따로 찾아보지 않고도 각 단어가 실제
    문장에서 어떻게 쓰이는지 바로 비교해 볼 수 있게 하기 위함이다. 용례를
    하나도 못 찾으면 빈 문자열을 돌려주고(플래그 자체는 그대로 유지됨),
    이미 처리한 단어는 중복 조회하지 않는다."""
    notes = []
    seen = set()
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        examples = usage_examples(word, limit=1)
        if examples:
            notes.append(f"{word}: '{examples[0]}'")
    return " / ".join(notes)


def check_purified_terms(index: int, text: str) -> FlagItem | None:
    """일반 순화어(예: 반팔->반소매)가 등장하면 확인 플래그한다. 차별적
    표현과 달리 관례적 표현이 여전히 널리 쓰이는 경우가 있어(예: 유모차는
    공식 순화어 유아차보다 압도적으로 많이 쓰임) 자동으로 바꾸지 않는다.

    온용어(K-term) API에서 "다듬은 말"을 동적으로 조회하고, 정적
    목록(PURIFIED_TERMS)과 통합해 사용한다 — API가 실패하면 정적 목록만으로
    동작한다."""
    purified = get_purified_terms()
    matched = [word for word in purified if word in text]
    if not matched:
        return None
    suggestions = ", ".join(f"{word}->{purified[word]}" for word in matched)
    reason = f"순화어 확인 필요: {suggestions} (관례적 표현이 더 적절할 수도 있음)"
    note = _usage_note(matched + [purified[word] for word in matched])
    if note:
        reason += f" | 우리말샘 용례) {note}"
    return FlagItem(line_index=index, original_text=text, reason=reason)
