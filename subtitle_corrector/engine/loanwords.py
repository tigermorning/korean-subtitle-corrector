"""외래어 표기(kornorms 확정 표기). 일반 용어는 자동 반영, 고유명사는 플래그만 남긴다.
"""

from ..dictionary import is_standard_word, loanword_fix, word_exists
from ..report import FlagItem
from .kiwi_adapter import _LOANWORD_TAGS, _kiwi
from .kiwi_adapter import _has_reading
from .lexicon import _inside_unknown_compound, is_hada_stem, _tensified_headword_variant
from .text_utils import _JOSA_ALLOMORPHS, _josa

def correct_loanwords(
    text: str,
) -> tuple[str, list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """kornorms가 확정한 외래어 표기 오류를 고친다.

    NNG(일반 명사)는 kornorms 정답이 하나뿐이면 조용히 자동 반영하고, 서로
    다른 관례가 공존하면 반영은 하되 확인 플래그를 남긴다 — 기존 방식 그대로.

    NNP(고유명사)는 이 둘 중 어느 쪽이든 절대 텍스트에 자동 반영하지 않고
    항상 확인 플래그로만 제안한다. "스노우"가 인명(스노우 기자)이면 표기
    규칙대로 "스노"가 맞지만, 같은 표기가 영화 제목("스노우맨")처럼 배급사가
    정한 고유 표기일 수도 있어 규칙을 강제하면 실제 고유명사를 훼손할 위험이
    있다 — 텍스트만으로는 이 둘을 구분할 방법이 없으므로, 고유명사는 자동화
    대신 항상 사람이 최종 판단하게 한다.

    반환값: (수정된 텍스트, 확인 불필요 자동 교정 로그, 확인 필요 교정 목록,
    고유명사 확인 제안 목록)
    확인 불필요 로그 항목은 '원문 -> 정답' 문자열이다.
    확인 필요 목록 항목은 ('원문 -> 정답', 전체 맥락) 튜플이다.
    고유명사 확인 제안 목록 항목도 ('원문 -> 정답', 전체 맥락) 튜플이다 —
    텍스트 자체는 바뀌지 않고 이 제안만 리포트에 남는다.
    """
    tokens = _kiwi.tokenize(text)
    candidates = [t for t in tokens if t.tag in _LOANWORD_TAGS]
    replacements = []  # (start, len, original, fix, needs_review, context, is_proper_noun)
    for t in candidates:
        # '-하다'가 바로 붙은 어근은 외래어 명사가 아니라 **용언의 어근**이다.
        # 실사용에서 '새롭고 힙한 동네'가 '새롭고 히프한 동네'로 바뀌었다 — kornorms에
        # hip -> 히프 용례가 있어 '힙'을 명사로 보고 치환한 것이다. '힙하다'는 우리말샘
        # 표제어이므로 이 결합 자체가 사전에 있다(2026-08-03 실사용 감수).
        if is_hada_stem(tokens, t):
            continue
        # 이미 사전에 정식 등재된 표준 표기는 애초에 외래어 오표기 후보가
        # 아니므로 건드리지 않는다. 그렇지 않으면 "집"처럼 흔한 고유어가
        # kornorms의 전혀 무관한 외래어 항목과 우연히 겹쳐 "지브" 같은 엉뚱한
        # 말로 둔갑하는 사고가 생긴다 (실제로 발견된 버그). `word_exists()`가
        # 아니라 `is_standard_word()`를 쓴다 — 방언 동형이의어('빠리'=파리의
        # 방언, '커리'=카레의 방언)가 실존 낱말이라는 이유로 여기서 표준으로
        # 오판되면 정당한 외래어 교정(빠리→파리, 커리→카레)이 막힌다
        # (`docs/BACKLOG.md` 33번).
        if is_standard_word(t.form):
            continue
        # 된소리 구어형이 사전 표제어면(빤스→빤쓰) 외래어 표기로 자동 교정하지
        # 않고 check_colloquial_loanword()가 사람 확인 플래그를 남긴다.
        if _tensified_headword_variant(t.form):
            continue
        fix, needs_review, context = loanword_fix(t.form)
        if fix:
            # kiwi 1순위 태그만 믿으면 고유명사 보호가 뚫린다 — 같은 이름이 문장에 따라
            # NNG로 태깅된다('세상에, 러스'는 NNP, 두 줄 자막 안에서는 NNG). 대안 분석에
            # 고유명사 읽기가 하나라도 있으면 고유명사로 보고 자동 반영하지 않는다
            # (2026-08-04 사용자 제공 자막 7강 123번).
            is_proper = (
                t.tag == "NNP"
                or _has_proper_noun_reading(text, t)
                or _inside_unknown_compound(text, tokens, t)
            )
            replacements.append((t.start, t.len, t.form, fix, needs_review, context, is_proper))

    corrected = text
    applied = []
    needs_review_log = []
    proper_noun_suggestions = []
    for start, length, original, fix, needs_review, context, is_proper_noun in sorted(
        replacements, key=lambda r: r[0], reverse=True
    ):
        entry = f"{original} -> {fix}"
        if is_proper_noun:
            proper_noun_suggestions.append((entry, context))
            continue
        corrected = corrected[:start] + fix + corrected[start + length :]
        if needs_review:
            needs_review_log.append((entry, context))
        else:
            applied.append(entry)

    return (
        corrected,
        list(reversed(applied)),
        list(reversed(needs_review_log)),
        list(reversed(proper_noun_suggestions)),
    )


# 외래어 표기법 기본 원칙 제3항(받침은 ㄱㄴㄹㅁㅂㅅㅇ만)에 어긋나는 음절 —
# kiwi가 미등록 낱말('디스켙' 등)을 엉뚱한 형태소로 쪼개 버려(실측: '디스'+
# '하게'+'ᇀ') 토큰 기반 조회(loanword_fix)가 그 자리에 아예 닿지 못한다
# (작업자자료 w18·w19, 2026-09-02). kornorms에도 '커피숖'·'숖'·'켙' 항목이
# 없어(단어 자체가 아니라 원칙 위반이라 개별 오표기로 심의되지 않음) 동적
# 조회로 잡을 방법이 없다 — `docs/BACKLOG.md` 31번이 이미 정리한 "외래어
# 판별기가 없다" 장벽과 같은 부류다.
#
# **다만 이 음절들은 word_exists()로 확인(2026-09-02)해 보니 어떤 표제어에도
# 전혀 쓰이지 않는다** — ㅍ 받침은 '잎'·'높다'처럼 고유어에 실재하지만,
# '소'+ㅍ('숖')·'케'+ㅌ('켙') 조합 자체는 국립국어원 사전 어디에도 없다.
# 그래서 "이 낱말이 외래어인가"를 가릴 필요 없이(BACKLOG 31의 장벽을
# 비켜 간다) 이 음절이 등장하면 항상 오표기로 보고 토큰 경계와 무관하게
# 문자 그대로 바꾼다 — kiwi 토큰화가 망가지는 자리라 토큰 기반 규칙으로는
# 애초에 닿을 수 없기 때문이기도 하다. 새 음절을 추가하려면 반드시
# word_exists()로 "어떤 표제어에도 안 쓰인다"를 먼저 확인할 것.
_FORBIDDEN_LOANWORD_BATCHIM = {"숖": "숍", "켙": "켓"}


def correct_loanword_forbidden_batchim(text: str) -> tuple[str, list[str]]:
    """외래어 표기에 쓸 수 없는 받침 음절을 고친다('커피숖' -> '커피숍',
    '디스켙' -> '디스켓'). `_FORBIDDEN_LOANWORD_BATCHIM`의 음절은 국립국어원
    사전 어디에도 쓰이지 않아(word_exists 확인) 등장하면 항상 오표기다 —
    토큰 경계를 보지 않고 문자 그대로 치환한다(kiwi가 이런 미등록 낱말을
    엉뚱하게 쪼개 토큰 기반 조회가 닿지 못하는 자리라 문자 단위로 접근)."""
    corrected = text
    edits = []
    for wrong, right in _FORBIDDEN_LOANWORD_BATCHIM.items():
        if wrong not in corrected:
            continue
        edits.append(f"{wrong} -> {right}")
        corrected = corrected.replace(wrong, right)
    return corrected, edits


def check_colloquial_loanword(index: int, text: str) -> FlagItem | None:
    """'빤스'처럼 외래어 표기 교정 대상이지만 된소리 구어형('빤쓰')이 사전
    표제어로 있어 화자의 말투일 수 있는 경우, 자동 교정하지 않고 구어형과
    외래어 표기 중 어느 쪽으로 적을지 사람이 정하도록 플래그한다."""
    for t in _kiwi.tokenize(text):
        # `correct_loanwords()`와 같은 이유로 `is_standard_word()`를 쓴다 —
        # 방언 동형이의어가 이미 "표준 표기"인 것처럼 걸러내면 안 된다.
        if t.tag not in _LOANWORD_TAGS or is_standard_word(t.form):
            continue
        variant = _tensified_headword_variant(t.form)
        if not variant:
            continue
        fix, _needs_review, _context = loanword_fix(t.form)
        if not fix:
            continue
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{t.form}'{_josa(t.form, '은')} 구어형 '{variant}'(사전 표제어)일 수도, 외래어 표기 "
                f"'{fix}'일 수도 있습니다 — 말투를 살릴지 여부를 사람이 판단하세요."
            ),
            suggested_fix=text[: t.start] + variant + text[t.start + t.len :],
        )
    return None


# 「외래어 표기법」제3장 제7절(중국어의 표기) 제2항: "'ㅈ, ㅉ, ㅊ'으로 표기되는
# 자음(ㄐ, ㄓ, ㄗ, ㄑ, ㄔ, ㄘ) 뒤의 'ㅑ, ㅖ, ㅛ, ㅠ' 음은 'ㅏ, ㅔ, ㅗ, ㅜ'로 적는다"
# (docs/LOANWORD_TRANSCRIPTION_RULES.md 제3장 제7절). 한글의 ㅈ·ㅉ·ㅊ은 이미
# 항상 구개음이라 뒤에 반모음을 더 적어도 소리가 달라지지 않는다 — 그래서 이
# 규정은 중국어 전용이 아니라 출처 언어를 가리지 않는 일반 표기 관행이다.
# kornorms에 등재된 영어·독일어·프랑스어·에스파냐어·중국어·일본어 오표기
# 수십 건이 전부 이 12음절을 오표기로 지목하고 있다(실측, 2026-09-01:
# 메이져(X)/메이저(영어), 솔페쥬(X)/솔페주(프랑스어), 산쵸(X)/산초(에스파냐어),
# 왕스졔(중국어 인명 표기 자체), 쬬끼(X)/조끼(일본어) 등). 다만 코드로 옮긴
# 근거는 이 조항 하나뿐이므로 반드시 이 12음절에만 한정한다 — 다른 반모음
# 결합(예: '여'가 오는 '져')은 이 조항이 언급하지 않아 대상이 아니다(실사용
# '가져'가 이 패턴에 걸리면 안 된다 — '여'는애초에 대상 밖이라 안전하다).
_PALATAL_GLIDE_FIX = {
    "쟈": "자", "졔": "제", "죠": "조", "쥬": "주",
    "쨔": "짜", "쪠": "쩨", "쬬": "쪼", "쮸": "쭈",
    "챠": "차", "쳬": "체", "쵸": "초", "츄": "추",
}


def check_palatal_glide_loanword(index: int, text: str) -> FlagItem | None:
    """ㅈ·ㅉ·ㅊ 뒤에 반모음이 덧붙은 외래어 표기(쟈·졔·죠·쥬 등)를 확인
    플래그한다 — 위 `_PALATAL_GLIDE_FIX` 주석 근거. kornorms에 이미 등재된
    단어는 `correct_loanwords()`의 `loanword_fix()`가 먼저 처리하므로,
    여기서는 kornorms에 없는(아직 심의되지 않은) 새 표기만 대상으로 한다.
    자동 반영하지 않는다 — 원리4를 피하려 언어를 가리지 않고 기계적으로
    걸지만, 그래도 이 글자 조합 자체가 다른 정당한 표기의 일부일 가능성을
    사람이 최종 확인해야 한다."""
    for t in _kiwi.tokenize(text):
        if t.tag not in _LOANWORD_TAGS or is_standard_word(t.form):
            continue
        hit_syllables = [ch for ch in t.form if ch in _PALATAL_GLIDE_FIX]
        if not hit_syllables:
            continue
        fix, _needs_review, _context = loanword_fix(t.form)
        if fix:
            continue  # kornorms가 이미 다른 정답을 확정해 뒀다 — correct_loanwords()가 처리
        suggested_word = t.form
        for syllable in hit_syllables:
            suggested_word = suggested_word.replace(syllable, _PALATAL_GLIDE_FIX[syllable])
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{t.form}'{_josa(t.form, '은')} 외래어 표기법상 'ㅈ·ㅉ·ㅊ 뒤에는 "
                f"반모음을 적지 않는다'는 원칙에 걸립니다(제3장 제7절 제2항 — 중국어 "
                "세칙이지만 한글 표기 관행이라 출처 언어를 가리지 않습니다). "
                f"'{suggested_word}'가 맞는 표기인지 확인하세요."
            ),
            suggested_fix=text[: t.start] + suggested_word + text[t.start + t.len :],
        )
    return None


# 영어식 형용사형 국명·주명(-an/-ian)을 발음 그대로 옮기지 않고 국명(명사)으로
# 옮긴다(작업자 자료 표기_맞춤법_번역.txt 303~305행): Persian Architecture
# 페르시안 건축(x)/페르시아 건축(o), Mexican Food 멕시칸 음식(x)/멕시코
# 음식(o). word_exists()로 확인(2026-09-02): '페르시안'·'멕시칸' 둘 다
# 표제어 없음, '페르시아'·'멕시코'는 표제어 있음 — 형용사형 자체가 사전에
# 없다는 사실이 근거다. **'아시안'은 이 목록에서 뺐다** — 같은 방식으로
# 확인해 보니 '아시안'도 단독으로는 표제어가 없지만, '아시안게임'·
# '아시안컵'은 그 자체로 표제어(고유명사, 대회 이름)라 예외가 실재한다.
# 다음 낱말과 결합해 이미 사전 표제어를 이루면(대회 이름 등 고정된 고유
# 명사) 건드리지 않는다 — 아래서 그 결합 여부를 매번 확인한다.
_ADJECTIVAL_DEMONYM_TO_COUNTRY = {"페르시안": "페르시아", "멕시칸": "멕시코"}


def check_adjectival_demonym(index: int, text: str) -> FlagItem | None:
    """영어식 형용사형 국명(페르시안·멕시칸 등)을 국명으로 바꿀지 확인
    플래그한다. 고유명사(국명)로 자동 반영하지 않는 기존 정책과 같은
    이유로 텍스트는 바꾸지 않는다 — 뒷말과 결합해 이미 고정된 고유명사를
    이루는 예외가 있을 수 있어서다(예: '아시안게임')."""
    tokens = _kiwi.tokenize(text)
    for i, t in enumerate(tokens):
        country = _ADJECTIVAL_DEMONYM_TO_COUNTRY.get(t.form)
        if not country or t.tag not in _LOANWORD_TAGS:
            continue
        if i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.tag in ("NNG", "NNP") and word_exists(t.form + nxt.form):
                continue  # 이미 사전에 오른 고정 고유명사 결합 — 건드리지 않는다
        suggested = text[: t.start] + country + text[t.start + t.len :]
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{t.form}'{_josa(t.form, '은')} 영어 형용사형을 발음 그대로 옮긴 표기입니다 — "
                f"외래어 표기 관행상 국명은 형용사형이 아니라 나라 이름 '{country}'로 옮깁니다"
                f"(예: Persian Architecture → 페르시아 건축). 다만 뒷말과 결합해 이미 굳어진 "
                "고유명사(대회 이름 등)일 수 있어 자동 반영하지 않습니다 — 확인해 주세요."
            ),
            suggested_fix=suggested,
        )
    return None


def _has_proper_noun_reading(text: str, token) -> bool:
    """kiwi 대안 분석에 이 자리를 고유명사(NNP)로 읽는 후보가 있는지."""
    return _has_reading(text, token, ("NNP",))


# 인명·지명·상표 관용 표기 — kornorms 정방향 표제어는 있으나 `loanword_fix()`가
# 쓰는 relate_mark_o(오표기 목록)가 비어 있거나(w31·포르쉐), 원문이 다른
# 표제어의 뜻풀이 문장 속에만 등장해(w30) 동적 조회가 닿지 못하는 자리(BACKLOG
# w26·w27·w30·w31, 2026-09-03 kornorms 직접 조회로 확인). 손으로 확인한
# 근거를 남긴다.
#
# 주윤발 -> 저우룬파: kornorms 정확 일치, 中 인명, 제38차 외래어 심의회
# (2001.2.28.), example_no 63262 — "周潤發(Zhōu Rùnfā)" 표제어의 확정 한글
# 표기가 "저우룬파"다. relate_mark_o가 비어 있어 "주윤발"로는 loanword_fix()의
# 역방향 검색이 안 걸린다(코드가 아니라 데이터 공백).
#
# 덴 하흐 -> 헤이그: kornorms에 "덴 하흐"로 검색하면 "헤이그" 표제어(지명,
# 제32차 외래어 심의회 2000.3.8., example_no 44165)가 걸린다 — 뜻풀이 자체가
# "네덜란드 12 주명과 주도명-약칭 덴 하흐 Den Haag"라고 명시한다. relate_mark_o가
# 아니라 뜻풀이 문장 안에만 있어 loanword_fix()의 필드 기반 조회가 못 잡는다.
#
# 포르쉐 -> 포르셰(작업자자료 w28, 2026-09-03 재확인 — §98이 "라벨 정정"으로
# 끝냈던 자리인데 실측하니 loanword_fix()가 여전히 못 잡는 같은 데이터
# 공백이었다): kornorms "포르셰" 표제어(회사·제품명, 제53차 외래어 심의회
# 2003.9.3., example_no 53212)의 뜻풀이가 "×포르쉐"라고 명시하는데도
# relate_mark_o는 비어 있다 — 위 "덴 하흐"와 같은 성격(뜻풀이 문장에만 근거가
# 있음).
#
# **매카서(w26)·폴크스바겐(w27)은 같은 부류로 보이지만 여기 넣지 않는다.**
# 매카서는 kornorms "맥아더" 표제어의 relate_mark_o에도 없는 오표기다(등재된
# 것은 맥아썰·맥아서·매가더뿐) — 권위 있는 근거가 없어 우리가 임의로 "틀렸다"고
# 판정하는 셈이 된다. 폴크스바겐/폭스바겐은 kornorms에 상표명 자체가 없다(심의
# 대상 아님). 둘 다 데이터가 없어 못 고치는 것이지 이 표의 누락이 아니다 —
# BACKLOG에 "받아들인 한계"로 남긴다.
_CONVENTIONAL_PROPER_NOUN_SPELLINGS: dict[str, tuple[str, str]] = {
    "주윤발": ("저우룬파", "중국 인명은 현지음 표기가 원칙(kornorms 제38차 외래어 심의회, 2001.2.28.)"),
    "덴 하흐": ("헤이그", "지명은 관용 표기 우선(kornorms 제32차 외래어 심의회, 2000.3.8.)"),
    "포르쉐": ("포르셰", "kornorms 표제어 뜻풀이에 '×포르쉐'로 명시(제53차 외래어 심의회, 2003.9.3.)"),
}


def check_conventional_proper_noun_spelling(index: int, text: str) -> FlagItem | None:
    """kornorms 역방향 검색이 안 닿는 소수 인명·지명·상표 관용 표기를 손으로
    확인해 플래그한다(작업자자료 w28·w30·w31). 고유명사는 절대 자동 반영하지
    않는 이 파일의 기존 정책과 같은 이유로 텍스트는 바꾸지 않는다 — 같은
    표기가 실제 인물이 아니라 다른 고유명사(작품 제목 등)를 가리킬 수도
    있다."""
    tokens = _kiwi.tokenize(text)
    for i, t in enumerate(tokens):
        if t.tag != "NNP":
            continue
        hit = _CONVENTIONAL_PROPER_NOUN_SPELLINGS.get(t.form)
        span_end = t.start + t.len
        last_idx = i
        if hit is None and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.tag == "NNP" and text[t.start + t.len : nxt.start] == " ":
                hit = _CONVENTIONAL_PROPER_NOUN_SPELLINGS.get(f"{t.form} {nxt.form}")
                if hit is not None:
                    span_end = nxt.start + nxt.len
                    last_idx = i + 1
        if hit is None:
            continue
        fix, basis = hit
        original = text[t.start:span_end]
        replacement = fix
        replacement_end = span_end
        # 받침이 달라지면 곧바로 붙는 조사도 이형태를 맞춰 바꾼다(작업자자료
        # w31 — 받침 없는 '저우룬파'로 바뀌면 '주윤발이'의 '이'가 '가'가 돼야
        # 한다). kiwi가 조사(J로 시작하는 태그)로 읽고 사이에 공백이 없을
        # 때만 건드린다.
        if last_idx + 1 < len(tokens):
            particle = tokens[last_idx + 1]
            if (
                particle.tag.startswith("J")
                and particle.start == span_end
                and particle.form in _JOSA_ALLOMORPHS
            ):
                replacement += _josa(fix, particle.form)
                replacement_end = particle.start + particle.len
        suggested = text[: t.start] + replacement + text[replacement_end:]
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{original}'{_josa(original, '은')} 관용 표기 '{fix}'로 굳어져 있습니다"
                f"({basis}). 고유명사라 자동 반영하지 않습니다 — 확인해 주세요."
            ),
            suggested_fix=suggested,
        )
    return None
