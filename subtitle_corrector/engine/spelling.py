"""맞춤법·순화어 검사. 대부분 자동 교정하지 않고 플래그만 남긴다 —
사전에 없다는 사실만으로는 무엇이 맞는 표기인지 알 수 없기 때문이다.
예외는 `correct_gumeon_ending()`처럼 사전 존재가 아니라 kiwi 구조
태그로 문맥과 무관하게 근거가 확정되는 자리뿐이다.
"""

from ..dictionary import (
    appears_in_standard_headword,
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


# 어간과 한 음절로 줄어드는 과거 시제 선어말 어미. '였'은 '하'+'였'('했')처럼
# 용언 어간 뒤에서만 본다 — 서술격 조사 '이'+'었'('였')은 VCP라 아래 어간 태그에
# 걸리지 않는다(코퍼스에서 '이었'/'였'이 kiwi.join과 갈리는 것을 확인했다).
_PAST_EP_FORMS = ("었", "았", "였")
_CONTRACTING_STEM_TAGS = ("VV", "VA", "VX", "XSV", "XSA")


def _past_contraction_fixes(text: str, tokens) -> dict:
    """어간+'-었-'이 한 음절로 줄어든 자리 중 표기가 준말 규정과 다른 곳.

    반환값: {음절 위치: 규정대로의 준말 음절}.

    kiwi는 '됬다'를 되/VV + 었/EP + 다/EF로 **정상 분석**한다 — 틀린 표면을 표준
    형태소로 정규화해 버리므로, 기본형('되다')만 사전에 묻는 `check_spelling()`에는
    아무것도 걸리지 않았다(2026-09-17). 줄어든 음절을 kiwi가 같은 형태소로 **다시 짜
    본 결과**(`kiwi.join`)가 규정대로의 준말이므로(한글 맞춤법 제34·35항), 원문
    음절이 그것과 다르면 원문이 규정 밖의 표기다. 형태소가 한 음절에 겹친 자리만
    본다 — '되었다'처럼 줄이지 않은 본말도 맞는 표기다.

    실측(2026-09-17): 맞는 준말·불규칙 활용 60여 개(파랬다·도왔다·불렀다·뵀다·쇘다·
    쬈다·가르쳤다·괜찮아졌다 …)에서 0건, 저장소 코퍼스 1,457줄에서 '됬' 말고 0건.
    """
    fixes = {}
    for stem, ep in zip(tokens, tokens[1:]):
        if not stem.tag.startswith(_CONTRACTING_STEM_TAGS):
            continue
        # kiwi는 문맥에 따라 '됬었다'의 '었었'을 한 토큰으로 묶는다('그렇게 됬었다',
        # 2026-09-17 실측). 어간과 겹치는 것은 그 첫 음절뿐이므로 첫 '었'만 다시 짠다.
        if ep.tag != "EP" or ep.form[:1] not in _PAST_EP_FORMS or ep.len != len(ep.form):
            continue
        if ep.start != stem.start + stem.len - 1:
            continue  # 어간 마지막 음절과 겹치지 않음 = 줄이지 않은 본말
        try:
            rebuilt = _kiwi.join([(stem.form, stem.tag), (ep.form[:1], ep.tag)])
        except Exception:
            continue
        if rebuilt and rebuilt[-1] != text[ep.start]:
            fixes[ep.start] = rebuilt[-1]
    return fixes


# '되' 어간 뒤에 '-어'가 빠진 채 붙은 어미. 이 어미들은 표준어에서 '-어요·-어서·
# -어야·-어야지·-어도'로만 쓰이므로, 어간에 바로 붙은 표면('되요')은 언제나 '되어'가
# 줄어든 '돼'를 잘못 적은 것이다(한글 맞춤법 제35항 [붙임 2]). 뜻(이루어짐/허락)과
# 무관하다 — '일이 잘 돼요'도 '들어가도 돼요'도 '돼요'다. '되라'(하라체 명령)·'되오'
# (하오체)·'되고'·'되면'·'되지'·'되니까'처럼 어간에 직접 붙는 어미는 넣지 않는다.
# 값은 kiwi가 그 자리에 다는 태그들(2026-09-17 실측: '되요'=EF, '밥이 되도'=JX).
_DWAE_ENDINGS = {
    "요": ("EF", "JX"),
    "서": ("EC",),
    "야": ("EF", "EC"),
    "야지": ("EC", "EF"),
    "도": ("EC", "JX"),
}

# 앞에 오면 '되'가 부피 단위 명사일 수 있는 자리 — kiwi가 동사로 잘못 읽는 것을
# 실측했다('보리 되도 팔았다'·'말과 되요' -> 되/VV). 수 관형사('한 되요')는 kiwi가
# NNB로 잘 가르지만 같은 부류라 함께 막는다. 뒤에 단위 명사가 오면('되서 개만') '두세'의
# 방언(우리말샘 '되-서')일 수 있다. 이런 자리는 자동 교정하지 않고 확인 플래그로 내린다.
_MEASURE_NOUN_PREV_TAGS = ("MM", "SN", "NR", "NNB", "JC")
_BARE_NOUN_TAGS = ("NNG", "NNP")
_COUNTER_NEXT_TAGS = ("NNB", "NR", "SN")
_CLOSING_QUOTES = frozenset({"\"", "'", "”", "’", ")", "」", "』"})


def _dwae_ending_fixes(text: str, tokens) -> tuple[set, set]:
    """'되요'·'되서'·'되야'·'되도', 그리고 문장 끝 '되'('가도 되?') 자리.

    문장 끝 '되': 용언 어간은 어미 없이 문장을 끝낼 수 없으므로, kiwi가 동사 '되'
    뒤에 어미를 하나도 못 찾고 곧바로 문장부호나 줄 끝을 만났다면 '-어'가 빠진
    것이다('안 되!' -> '안 돼!'). 뒤에 다른 낱말이 오면('되 찾았다' — 띄어 쓴
    '되찾다'일 수 있다) 이 판정을 하지 않는다.

    반환값: (자동 교정할 '되' 위치, 확인만 할 위치)."""
    auto, review = set(), set()
    for i, stem in enumerate(tokens):
        ending = tokens[i + 1] if i + 1 < len(tokens) else None
        if stem.form != "되" or not stem.tag.startswith(("VV", "XSV")) or stem.len != 1:
            continue
        if text[stem.start] != "되":
            continue  # '돼'로 적힌 자리(kiwi는 '돼요'도 되/VV로 돌려준다)
        if ending is None or ending.tag.startswith("S"):
            # 문장을 끝내는 부호만 인정한다. '되/돼'처럼 빗금·화살표가 오는 자리는
            # 낱말을 설명하는 글이지 문장 끝이 아니다(코퍼스 실측 오탐지, 2026-09-17).
            if ending is not None and (
                ending.start <= stem.start
                or not (ending.tag in ("SF", "SE") or ending.form in _CLOSING_QUOTES)
            ):
                continue
            nxt = None  # 문장 끝 '되' — 뒤따르는 단위 명사 검사는 해당 없음
        else:
            if ending.start != stem.start + 1:
                continue  # 어미가 어간 음절에 겹쳤다 = '어'와 이미 줄어든 형태
            if ending.tag not in _DWAE_ENDINGS.get(ending.form, ()):
                continue
            if text[ending.start : ending.start + len(ending.form)] != ending.form:
                continue
            nxt = tokens[i + 2] if i + 2 < len(tokens) else None
        prev = tokens[i - 1] if i >= 1 else None
        spaced = prev is not None and prev.start + prev.len < stem.start
        risky = (
            (prev is not None and prev.tag in _MEASURE_NOUN_PREV_TAGS)
            or (spaced and prev.tag in _BARE_NOUN_TAGS)
            or (nxt is not None and nxt.tag in _COUNTER_NEXT_TAGS)
        )
        (review if risky else auto).add(stem.start)
    return auto, review


def correct_dwae_spelling(text: str) -> tuple[str, list[str]]:
    """'되/돼' 표기 오류 중 답이 하나로 정해지는 자리를 자동으로 고친다.

    - '됬' -> '됐'('됬다' -> '됐다'): '됬'은 표준 낱말 어디에도 없는 음절이다 — 우리말샘
      포함 검색 0건(2026-09-17, 제목·속담까지 담는 개방형 사전). kiwi가 그 음절을
      '되'+'었'으로 읽은 자리만 고친다.
    - '되요/되서/되야/되야지/되도' -> '돼…': `_DWAE_ENDINGS` 참고. 부피 단위 명사 '되'나
      '두세'의 방언일 수 있는 자리는 `check_dwae_spelling()`이 확인 플래그로 넘긴다.

    **2026-09-17 사용자 결정으로 자동 교정한다**(처음엔 확인 플래그만 뒀다). 되/돼는
    발음이 같아 생기는 표기 오류이지 사투리 어미가 아니므로, "표준어 화자의 비표준
    어미를 자동 교정하지 않는다"는 원칙(AGENTS.md)의 대상이 아니다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')"""
    tokens = _kiwi.tokenize(text)
    edits = {
        pos: "됐"
        for pos, syllable in _past_contraction_fixes(text, tokens).items()
        if text[pos] == "됬" and syllable == "됐"
    }
    auto, _review = _dwae_ending_fixes(text, tokens)
    edits.update({pos: "돼" for pos in auto})
    if not edits:
        return text, []
    chars = list(text)
    for pos, syllable in edits.items():
        chars[pos] = syllable
    corrected = "".join(chars)
    return corrected, [_localized_change(text, corrected)]


def check_dwae_spelling(index: int, text: str) -> FlagItem | None:
    """되/돼 표기가 틀렸을 가능성이 높지만 자동으로 고치지 않은 자리를 확인 플래그한다.

    자동 교정(`correct_dwae_spelling()`) 뒤의 텍스트에 돈다. 남는 것은 둘이다.
    - '되요'류인데 '되'가 부피 단위 명사·'두세'의 방언일 수 있는 자리('보리 되도').
    - '됬' 말고 준말 규정과 다른 줄어든 음절(지금까지 실측 0건 — 안전망)."""
    tokens = _kiwi.tokenize(text)
    fixes = dict(_past_contraction_fixes(text, tokens))
    _auto, review = _dwae_ending_fixes(text, tokens)
    fixes.update({pos: "돼" for pos in review})
    if not fixes:
        return None
    chars = list(text)
    for pos, syllable in fixes.items():
        chars[pos] = syllable
    pairs = ", ".join(
        dict.fromkeys(f"'{text[pos]}' -> '{syllable}'" for pos, syllable in sorted(fixes.items()))
    )
    return FlagItem(
        line_index=index,
        original_text=text,
        reason=(
            f"되/돼 표기를 확인해 주세요({pairs}). '되어'가 줄면 '돼'로 적습니다 — "
            "한글 맞춤법 제35항 [붙임 2]('되어요'->'돼요', '되었다'->'됐다'). "
            "다만 '되'가 부피 단위(쌀 한 되)나 '두세'의 방언이면 원문이 맞습니다."
        ),
        suggested_fix="".join(chars),
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
