"""맞춤법·순화어 검사. 대부분 자동 교정하지 않고 플래그만 남긴다 —
사전에 없다는 사실만으로는 무엇이 맞는 표기인지 알 수 없기 때문이다.
예외는 `correct_gumeon_ending()`처럼 사전 존재가 아니라 kiwi 구조
태그로 문맥과 무관하게 근거가 확정되는 자리뿐이다.
"""

from ..dictionary import (
    appears_in_standard_headword,
    ending_redirect,
    one_syllable_headword_variant,
    get_purified_terms,
    search_kornorms,
    spelling_norm_note,
    usage_examples,
    word_exists,
)
from ..report import FlagItem
from .text_utils import _bracket_spans, _inside_any_span, _josa, _localized_change
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
    조각내는 경우의 오탐지은 _covered_by_larger_dictionary_unit()(원리 1 공유 가드)로
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


def correct_gumeon_ending(text: str) -> tuple[str, list[str]]:
    """종결 어미 '-구먼'을 잘못 적은 '-구만'을 고친다('좋구만' -> '좋구먼').

    표준국어대사전: '구먼'은 '-군'의 본말로 등재된 표제어다. '구만'에도
    표제어가 있지만 뜻이 전혀 다르다(두려워하며 애를 태움의 어근, 지명
    둘) — 어미 뜻은 없다. 그래서 사전 등재 여부가 아니라 **kiwi가 그
    자리를 실제로 종결 어미(EF)로 태깅했는가**를 근거로 삼는다: 지명·
    어근 뜻이면 kiwi가 NNG/NNP로 태깅하지 EF로 태깅하지 않는다(실측
    확인, 2026-09-02 — '구만리'는 NNG, '구만면'은 NNP, 용언 어간 뒤
    '좋구만'만 EF). EF로 태깅된 자리는 문맥과 무관하게 항상 오표기다.

    '는구만'·'겠구만'처럼 다른 어미와 결합해 '구만'이 통째로 어미 뒤쪽에
    붙어 있어도(kiwi가 결합형 전체를 한 토큰으로 묶어 돌려줌) 그 끝
    두 글자만 '구먼'으로 바꾼다."""
    tokens = _kiwi.tokenize(text)
    edits = []  # (구만 시작, 구만 끝)
    for t in tokens:
        if t.tag == "EF" and t.form.endswith("구만"):
            end = t.start + t.len
            edits.append((end - 2, end))
    if not edits:
        return text, []
    corrected = text
    for start, end in sorted(edits, reverse=True):
        corrected = corrected[:start] + "구먼" + corrected[end:]
    return corrected, [_localized_change(text, corrected)]


def check_negation_reply_spelling(index: int, text: str) -> FlagItem | None:
    """줄 맨 앞 '아니오'가 대답(감탄사)이면 '아니요'로 확인 플래그한다.

    표준국어대사전: '아니요'는 감탄사 표제어("윗사람이 묻는 말에 부정하여 대답할
    때 쓰는 말")다. '아니오'도 감탄사로 등재돼 있지만 뜻풀이가 "→ 아니요"(비표준,
    규범 표기로 넘겨줌)다. 반면 '아니오'는 형용사 '아니다'의 어간 '아니'+하오체
    종결 어미 '-오'가 결합한 서술어로도 쓰인다("이건 사과가 아니오") — 이 자리는
    활용형이라 표제어가 아니지만 표기는 그대로 맞다.

    kiwi 자체의 형태소 분석은 둘을 안정적으로 갈라내지 못한다(`docs/BACKLOG.md`
    w16 — 겉보기엔 같은 "아니오 + 뒷문장" 구조인데 "아니오 그건 아니야"는 '아니오'
    통짜를 IC로, "아니오 저는 모릅니다"는 VCN('아니')+EC('오')로 실측에서 다르게
    갈랐다). 그 대신 **위치**로 가른다: 서술어라면 반드시 앞에 주어(체언+조사)가
    있어야 하므로, 줄 맨 앞(문장부호·인용부호·대사 기호 제외) '아니오'는 주어가
    붙을 자리가 없어 대답(감탄사)일 수밖에 없다 — 이 신호는 위 두 예문 모두에서
    일관되게 성립한다(둘 다 문장 맨 앞).

    **자동 교정하지 않는다.** 자막은 한 문장이 여러 줄로 쪼개진다 — 앞 줄이
    "그건 사과가"로 끝나고 이 줄이 "아니오"로 이어받으면, 이 줄만 보고는 주어가
    없어 보여도 실제로는 서술어다. 이 도구는 앞 줄의 문맥까지 보지 않으므로 사람이
    확인해야 한다(`check_dependent_noun_sentence_start`와 같은 이유·같은 처리)."""
    tokens = _kiwi.tokenize(text)
    content = [t for t in tokens if not t.tag.startswith("S")]
    if not content:
        return None

    first = content[0]
    if first.tag == "IC" and first.form in ("아니오", "아니요"):
        surface = first.form
    elif (
        first.tag == "VCN"
        and first.form == "아니"
        and len(content) > 1
        and content[1].tag in ("EC", "EF")
        and content[1].form in ("오", "요")
    ):
        surface = first.form + content[1].form
    else:
        return None

    if surface != "아니오":
        return None

    return FlagItem(
        line_index=index,
        original_text=text,
        reason=(
            "줄 맨 앞 '아니오'는 대답(감탄사)이면 '아니요'가 맞습니다(표준국어대사전 "
            "'아니오' 표제어 뜻풀이 '→ 아니요'). 다만 이 줄이 앞 자막에서 이어지는 "
            "서술어('~가 아니오')라면 원문이 맞을 수 있습니다 — 앞뒤 문맥을 확인해 주세요."
        ),
        suggested_fix=text.replace("아니오", "아니요", 1),
    )


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
        # 후보가 하나면 그 표기가 왜 그렇게 적히는지 사전이 밝힌 규정 근거를 그대로
        # 인용한다(`docs/BACKLOG.md` 6번). "사전 근거 있음"이라고만 하면 번역가가
        # 무엇을 근거로 판단하라는 것인지 알 수 없다 — 조항이 실려 있으면 스스로
        # 확인할 수 있다. 검색 API에는 없고 사전 내용 API(view.do)에만 있는 정보다.
        note = spelling_norm_note(variants[0]) if len(variants) == 1 else ""
        evidence = f"({note})" if note else "(사전 근거 있음)"
        hints.append(
            f"'{word}'{_josa(word, '는')} '{', '.join(variants)}'일 가능성이 있습니다"
            f"{evidence}"
        )
        if suggested_fix is None and len(variants) == 1:
            suggested_fix = text.replace(word, variants[0], 1)

    reason = (
        f"사전에 없는 단어: {', '.join(unknown)} — 외국어 음차·고유명사일 수 있음. "
        # 음차라면 정답은 원어가 정한다. 아래 칸에 원어를 넣으면 국립국어원 용례로
        # 확정 표기를 찾아 주므로, 세칙을 직접 읽지 않고도 판단할 수 있다(docs/log-archive/2026-h2.md §61).
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


# ---------------------------------------------------------------------------
# 낱말 목록이 아니라 부류 전체를 보는 장치(2026-11-11, IMPLEMENTATION_LOG §105).
# - 어미 없이 끝난 용언 어간(문법 부류): '되'는 제35항 붙임 2로 '돼' 자동, 나머지는 표시.
# - 사전이 '→ 다른 어미'로 넘겨주는 어미(사전 조회): 자동.
# - 붙여 쓴 '명사+용언'의 한 음절 오기(사전 조회): 제안만.
# 자동 교정은 모두 **한 음절을 같은 길이의 한 음절로 바꾸는** 교정이라 위치가 어긋나지
# 않는다. 로그는 어절 단위로 남긴다 — edit_guard가 로그로 결과를 재구성해 검증하므로
# (`correct_mot_hada_compound`와 같은 이유).
# ---------------------------------------------------------------------------

# 이 태그의 말이 '되' 바로 앞에 **붙어** 있으면 그 '되'는 동사 '되다'가 아니라 연결 어미
# '-되'(말은 하되)를 kiwi가 잘못 가른 것일 수 있다 — 건드리지 않는다.
_PREDICATE_OR_ENDING_TAGS = frozenset(
    {"VV", "VA", "VX", "VCP", "VCN", "XSV", "XSA", "EP", "EC", "EF", "ETM", "ETN"}
)
_CLOSING_QUOTES = "\"'”’)]」』"
_WORD_EDGE_STRIP = ".,!?" + _CLOSING_QUOTES


def _word_bounds(text: str, pos: int) -> tuple[int, int]:
    """pos가 든 어절(공백·줄바꿈 사이)의 [시작, 끝)."""
    start = max(text.rfind(" ", 0, pos), text.rfind("\n", 0, pos)) + 1
    ends = [i for i in (text.find(" ", pos), text.find("\n", pos)) if i != -1]
    return start, (min(ends) if ends else len(text))


def _apply_syllable_swaps(text: str, swaps: dict[int, str]) -> tuple[str, list[str]]:
    """swaps {위치: 새 음절}을 적용하고 어절 단위 로그('원어절 -> 새어절')를 돌려준다.

    한 글자 어절(예: '되')은 문장 안에 여러 번 나올 수 있어 로그 재구성이 다른 자리까지
    바꾸면 edit_guard가 거부한다 — 어절이 두 글자 미만이면 앞 어절까지 묶어 로그를 남긴다.
    """
    if not swaps:
        return text, []
    chars = list(text)
    for pos, syllable in swaps.items():
        chars[pos] = syllable
    corrected = "".join(chars)
    spans: list[tuple[int, int]] = []
    for pos in sorted(swaps):
        start, end = _word_bounds(text, pos)
        if len(text[start:end].strip(_WORD_EDGE_STRIP)) < 2 and start > 0:
            start = _word_bounds(text, start - 1)[0]
        if spans and start < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((start, end))
    return corrected, [f"{text[s:e]} -> {corrected[s:e]}" for s, e in spans]


def _adjacent_prev(tokens, i):
    """tokens[i] 바로 앞에 **붙어 있는**(사이 공백 없는) 토큰. 없으면 None."""
    if i == 0:
        return None
    p = tokens[i - 1]
    return p if p.start + p.len >= tokens[i].start else None


def _is_sentence_end(rest: str) -> bool:
    """'되' 뒤의 나머지가 '줄 끝' 또는 '문장부호(.?!)+닫는 따옴표 뒤 공백·끝'인가.

    말줄임(`...`·`…`)·물결·쉼표는 말이 끊긴 자리일 수 있어 끝으로 보지 않는다."""
    i = 0
    while i < len(rest) and rest[i] in ".?!":
        i += 1
    punct = rest[:i]
    if ".." in punct:
        return False
    while i < len(rest) and rest[i] in _CLOSING_QUOTES:
        i += 1
    after = rest[i:]
    if not punct:
        return after.strip(" \t") == "" or after.lstrip(" \t").startswith("\n")
    return after == "" or after[0].isspace()


# 어미 없이 끝날 수 없는 용언 어간의 품사(불규칙 표지 '-I'·'-R' 등은 떼고 본다).
# 'VCP'(이다)는 넣지 않는다 — '학생이'의 '이'를 kiwi가 VCP로 읽는 일이 있어 조사와 갈리지 않는다.
_BARE_STEM_TAGS = frozenset({"VV", "VA", "VX", "VCN", "XSV", "XSA"})
_OPENING_QUOTES = "'\"‘“"


def _bare_stem_indices(text: str, tokens) -> list[int]:
    """용언 어간이 **어미 없이** 줄·문장을 끝내는 토큰 위치들(부류 검사, 낱말 목록 없음).

    어간은 어미 없이 홀로 끝날 수 없다. 이 자리에 걸리는 조건:
    - 품사가 `_BARE_STEM_TAGS`이고 표면이 형태와 같다(축약으로 어미가 녹은 '돼'·'가'는 제외).
    - 바로 뒤에 붙은 어미가 없다(다음 토큰이 같은 음절에 겹치거나 공백 없이 붙지 않음).
    - 뒤가 줄 끝이거나 `.?!`+닫는 따옴표 뒤 공백·끝(`_is_sentence_end`). 말줄임·물결·쉼표는
      끊긴 대사일 수 있어 제외.
    - 앞에 용언·어미가 붙어 있지 않다(연결 어미 '-되'를 kiwi가 어간으로 잘못 읽는 경우).
    - 앞 글자가 한글·공백이 아니면(`안/않`처럼 기호에 붙은 낱말 언급) 제외. 따옴표로 감싼
      글자 언급('되')도 제외.
    """
    out = []
    for i, t in enumerate(tokens):
        if t.tag.split("-")[0] not in _BARE_STEM_TAGS:
            continue
        end = t.start + t.len
        if text[t.start : end] != t.form:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt is not None and (nxt.start < end or (nxt.start == end and not nxt.tag.startswith("S"))):
            continue
        prev = _adjacent_prev(tokens, i)
        if prev is not None and prev.tag in _PREDICATE_OR_ENDING_TAGS:
            continue
        if not _is_sentence_end(text[end:]):
            continue
        before_char = text[t.start - 1] if t.start > 0 else ""
        after_char = text[end] if end < len(text) else ""
        if before_char and not (before_char.isspace() or "가" <= before_char <= "힣"):
            if not (before_char in _OPENING_QUOTES and after_char not in _CLOSING_QUOTES):
                continue
        out.append(i)
    return out


def check_bare_stem(index: int, text: str) -> FlagItem | None:
    """'되' 말고 다른 용언 어간이 어미 없이 줄·문장을 끝낸 자리를 **확인 필요**로 표시한다.

    '되'는 제35항 붙임 2가 답('돼')을 정해 주므로 `correct_doe_dwae()`가 고친다. 다른 어간은
    무엇이 빠졌는지(어미·말줄임) 알 수 없어 제안 없이 이유만 낸다('이제 그만 쉬' — '쉬어'?
    아니면 끊긴 말?). 코퍼스 측정(§105): 실제 자막·평가 문장 187줄에서 '되' 말고는 0건.
    """
    tokens = _kiwi.tokenize(text)
    stems = [tokens[i] for i in _bare_stem_indices(text, tokens) if tokens[i].form != "되"]
    if not stems:
        return None
    names = ", ".join(f"'{t.form}-'" for t in stems)
    return FlagItem(
        line_index=index,
        original_text=text,
        reason=(
            f"용언 어간({names})이 어미 없이 문장을 끝냅니다. 어미가 빠졌거나 말이 끊긴 자리면 "
            "말줄임표 등으로 나타내 주세요."
        ),
    )


def correct_doe_dwae(text: str) -> tuple[str, list[str]]:
    """'되'로 잘못 적은 '돼'('되어'의 준말)·'됐'('되었'의 준말)를 고친다.
    한글 맞춤법 제35항 붙임 2(되어→돼, 되었다→됐다).

    세 자리만 고친다(검증표 IMPLEMENTATION_LOG §105).
    (a) 동사 어간 '되'(VV)가 어미 없이 줄·문장 끝에 온 자리 — 어간은 홀로 끝날 수
        없으므로 '되어'의 준말 '돼'다('그러면 안되' -> '그러면 안돼').
    (b) '됬' — kiwi가 '되'+'었'(EP)으로 가른 음절. '되었'의 준말은 '됐'이다.
    (c) '되요'·'되서' — kiwi가 되/VV 바로 다음 음절을 '요'(EF/EC)·'서'(EC)로 가른 자리.
        '-요'·'-서'는 '되-' 어간에 바로 붙지 않는다('되어요'·'되어서'의 준말 '돼요'·'돼서').

    건드리지 않는 것: 명사 '되'(되/NNB, '쌀 한 되'), 연결 어미 '-되'(되/EC, '말은 하되'),
    어미가 붙은 '되고'·'되면'·'되세요', 말줄임으로 끊긴 '안 되...'.
    """
    tokens = _kiwi.tokenize(text)
    swaps: dict[int, str] = {}
    for i in _bare_stem_indices(text, tokens):
        if tokens[i].tag == "VV" and tokens[i].form == "되":
            swaps[tokens[i].start] = "돼"  # (a)
    for i, t in enumerate(tokens):
        if t.tag != "VV" or t.form != "되" or t.len != 1 or text[t.start : t.start + 1] != "되":
            continue
        prev = _adjacent_prev(tokens, i)
        if prev is not None and prev.tag in _PREDICATE_OR_ENDING_TAGS:
            continue
        end = t.start + 1
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if (
            nxt is not None
            and nxt.start == end
            and nxt.len == 1
            and text[end] == nxt.form
            and ((nxt.form == "요" and nxt.tag in ("EF", "EC")) or (nxt.form == "서" and nxt.tag == "EC"))
        ):
            swaps[t.start] = "돼"  # (c)
    pos = text.find("됬")
    while pos != -1:
        has_ep = any(t.tag == "EP" and t.form == "었" and t.start == pos for t in tokens)
        has_stem = any(
            t.tag.startswith("V") and t.form.endswith("되") and t.start + t.len == pos + 1 for t in tokens
        )
        if has_ep and has_stem:
            swaps[pos] = "됐"  # (b)
        pos = text.find("됬", pos + 1)
    return _apply_syllable_swaps(text, swaps)


# kiwi 어미 형태의 받침 자모(첫가끝 종성)를 사전 표제어가 쓰는 호환 자모로. 사전은
# '-ㄹ게'처럼 호환 자모로 적고 kiwi는 'ᆯ게'처럼 종성 자모로 낸다.
_CODA_TO_COMPAT = {"ᆫ": "ㄴ", "ᆯ": "ㄹ", "ᆷ": "ㅁ", "ᆸ": "ㅂ", "ᆻ": "ㅆ", "ᆼ": "ㅇ", "ᆨ": "ㄱ"}


def _redirect_for_ending(form: str) -> tuple[str, str] | None:
    """kiwi 어미 형태 `form`에 대해 표준국어대사전이 '→ 다른 어미'로 넘겨주면
    (원문에서 바꿀 꼬리, 바꿀 꼬리)를 돌려준다. 둘 다 표면에 보이는 음절 문자열이다.

    kiwi는 끝의 높임 보조사 '요'를 어미에 붙여 한 토큰으로 내기도 한다('ᆯ께요').
    그런 형태는 사전 표제어가 아니므로 '요'를 떼고 한 번 더 묻는다.
    받침 자모로 시작하는 어미('ᆯ께')는 그 받침이 앞 음절에 녹아 있으므로 표면에서는
    받침 뒤 음절('께')만 비교한다 — 바뀐 어미도 같은 받침으로 시작할 때만 받는다.
    """
    query = "".join(_CODA_TO_COMPAT.get(ch, ch) for ch in form)
    tail = ""
    target = ending_redirect(query)
    if target is None and query.endswith("요") and len(query) > 1:
        query, tail = query[:-1], "요"
        target = ending_redirect(query)
    if target is None:
        return None
    lead = query[0] if query[0] in _CODA_TO_COMPAT.values() else ""
    if lead and not target.startswith(lead):
        return None
    old, new = query[len(lead):] + tail, target[len(lead):] + tail
    if not old or not new or old == new:
        return None
    return old, new


def _ending_redirect_sites(text: str) -> list[tuple[int, str, str, bool]]:
    """(원문 위치, 원래 꼬리, 바꿀 꼬리, 뒤에 '?'가 오는가) 목록."""
    sites = []
    for t in _kiwi.tokenize(text):
        if t.tag not in ("EF", "EC"):
            continue
        pair = _redirect_for_ending(t.form)
        if pair is None:
            continue
        old, new = pair
        surface = text[t.start : t.start + t.len]
        if not surface.endswith(old):
            continue
        question = text[t.start + t.len :].lstrip(" ").startswith("?")
        sites.append((t.start + t.len - len(old), old, new, question))
    return sites


def correct_ending_redirect(text: str) -> tuple[str, list[str]]:
    """표준국어대사전이 '→ 다른 어미'로만 실어 둔 비표준 어미를 그 어미로 고친다.

    예: '-ㄹ께'(100390) "→ -ㄹ게.", '-을께'(262165) "→ -을게."(2026-11-11 조회) —
    '올께요' -> '올게요'. 낱말별 목록이 아니라 kiwi가 어미(EF/EC)로 가른 모든 형태를
    사전에 묻는다(`ending_redirect()`; 같은 표기의 어미 표제어가 **모두** 넘겨주기일 때만).
    조회는 어미 형태마다 한 번이고 캐시된다.

    **부정 근거다**: 원문 표기가 사전에서 비표준으로 명시돼 있다. 그래서 자동으로 고친다.
    다만 뒤에 '?'가 오면 고치지 않고 `check_ending_redirect_question()`이 표시한다 —
    '할께요?'는 '-ㄹ까요'(의문 어미, 제53항 다만)를 잘못 적은 것일 수 있어 사전이 가리키는
    '-ㄹ게요?'로 바꿔도 틀린 교정이 될 수 있다.
    길이가 같은 바꿈만 한다(로그 재구성이 위치를 잃지 않게). 다르면 표시로 돌린다.
    """
    swaps: dict[int, str] = {}
    for pos, old, new, question in _ending_redirect_sites(text):
        if question or len(old) != len(new):
            continue
        for k, (a, b) in enumerate(zip(old, new)):
            if a != b:
                swaps[pos + k] = b
    return _apply_syllable_swaps(text, swaps)


def check_ending_redirect_question(index: int, text: str) -> FlagItem | None:
    """`correct_ending_redirect()`가 자동으로 고치지 않고 남긴 비표준 어미를 표시한다
    (뒤에 '?'가 오거나, 바꿀 어미와 길이가 달라 자동 교정에서 뺀 자리). 제안 없이 이유만."""
    left = [
        (old, new) for _pos, old, new, question in _ending_redirect_sites(text)
        if question or len(old) != len(new)
    ]
    if not left:
        return None
    pairs = ", ".join(f"'-{old}' → '-{new}'" for old, new in left)
    return FlagItem(
        line_index=index,
        original_text=text,
        reason=(
            f"표준국어대사전이 비표준으로 넘겨주는 어미가 있습니다({pairs}). 뒤에 물음표가 오면 "
            "의문 어미('-ㄹ까요' 등)를 잘못 적은 것일 수도 있어 자동으로 고치지 않았습니다 — "
            "뜻에 맞게 고쳐 주세요."
        ),
    )


def check_glued_noun_predicate(index: int, text: str) -> FlagItem | None:
    """명사에 용언을 붙여 쓴 자리가 **자모 하나만 다른 표제어**의 오기로 보이면 제안한다.

    예: '어의없네' — kiwi가 어의/NNG + 없/VA로 가른다. 붙인 기본형 '어의없다'는 표준국어대사전에
    없고, '…없다'로 끝나는 네 음절 표준 표제어 중 앞부분의 한 음절에서 자모 하나만 다른 것은
    '어이없다' 하나뿐이다(`one_syllable_headword_variant()`, 끝 검색 1~2쪽 + 후보 확인).
    그러면 '어이없네'를 제안한다. 한 음절 명사('말없어')는 이웃 표제어가 많아 보지 않는다.

    **자동 교정하지 않는다.** "비슷한 표제어가 있다"는 긍정 근거일 뿐이고, 띄어 써야 할
    구('어의 없다')를 붙여 쓴 것일 수도 있다. 낱말 목록은 쓰지 않는다 — 명사(NNG)에 용언 어간
    (VV/VA)이 공백 없이 붙은 모든 자리에 같은 검사를 한다.
    """
    tokens = _kiwi.tokenize(text)
    suggested = text
    found = []
    for i in range(len(tokens) - 1):
        noun, stem = tokens[i], tokens[i + 1]
        if noun.tag != "NNG" or stem.tag not in ("VV", "VA") or stem.start != noun.start + noun.len:
            continue
        prev = _adjacent_prev(tokens, i)
        if prev is not None and prev.tag in _PREDICATE_OR_ENDING_TAGS:
            continue  # '할말없어'(하+ㄹ+말+없) — 꾸밈을 받는 명사구라 한 낱말의 오기가 아니다
        if len(noun.form) < 2:
            # 한 음절 명사는 자모 하나 차이 이웃이 너무 많다 — 반례 71문장 측정(§105)에서
            # '말없어'→'맛없어', '차없어'→'가없어', '말있어'→'맛있어'가 모두 한 음절 명사였다.
            continue
        noun_surface = text[noun.start : noun.start + noun.len]
        stem_surface = text[stem.start : stem.start + stem.len]
        if noun_surface != noun.form or stem_surface != stem.form:
            continue  # 불규칙 활용·축약으로 표면이 형태와 다르면 기본형을 믿을 수 없다
        base = noun.form + stem.form + "다"
        variant = one_syllable_headword_variant(base, stem.form + "다")
        if variant is None:
            continue
        new_head = variant[: len(noun.form)]
        start, end = noun.start, noun.start + noun.len
        suggested = suggested[:start] + new_head + suggested[end:]
        found.append((base, variant))
    if not found:
        return None
    pairs = ", ".join(f"'{a}'는 사전에 없고 '{b}'가 표제어" for a, b in found)
    return FlagItem(
        line_index=index,
        original_text=text,
        reason=(
            f"붙여 쓴 말이 자모 하나 다른 표제어의 오기일 수 있습니다({pairs}, 표준국어대사전). "
            "띄어 써야 할 말을 붙인 것이면 원문의 띄어쓰기를 고쳐 주세요."
        ),
        suggested_fix=suggested,
    )
