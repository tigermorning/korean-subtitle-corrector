"""어휘 치환 — 항상 틀린 표기, 비표준어, 차별적 표현, 전(前) 용어. 조사 이형태 보정 포함.
"""

import re
from ..common_errors import ALWAYS_WRONG, DISCRIMINATORY_TERMS
from ..dictionary import (
    headword_definitions,
    specialist_only_fields,
    former_term_field,
    former_term_lookup,
    standard_term_replacement,
    word_exists,
)
from ..report import FlagItem
from .text_utils import _has_batchim, _josa
from .kiwi_adapter import _kiwi
from .lexicon import _inside_unknown_compound, _tensified_headword_variant, is_hada_stem

def check_ambiguous_particle(index: int, text: str) -> FlagItem | None:
    """행 끝에 띄어 쓴 '나'가 조사('백 배 나'→'백 배나')인지 '낫다'의 활용
    '나아'의 오기인지 모호할 때 확인 플래그한다. correct_particle_spacing()이
    이 경우 자동으로 붙이지 않으므로, 사람이 문맥으로 판단하게 남긴다."""
    tokens = _kiwi.tokenize(text)
    if len(tokens) < 2:
        return None
    last, prev = tokens[-1], tokens[-2]
    if last.form == "나" and last.tag == "JX" and prev.start + prev.len < last.start:
        joined = text[: prev.start + prev.len] + text[last.start :]  # 사이 공백 제거
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                "행 끝 '나'가 조사('~나')인지 '낫다'의 활용 '나아'의 오기인지 "
                "모호합니다 — 문맥 확인이 필요합니다."
            ),
            suggested_fix=joined,
        )
    return None


# 받침 유무에 따라 형태가 바뀌는 조사 짝: (받침 있을 때 형태, 받침 없을
# 때 형태). "으로/로"는 ㄹ받침 예외("물로"이지 "물으로"가 아님)가 있어
# 일반화하기 까다로워 제외한다 — 확신 없는 부분은 건드리지 않는다는 원칙.
_PARTICLE_ALLOMORPH_GROUPS = [("이", "가"), ("은", "는"), ("을", "를"), ("과", "와")]


_PARTICLE_TO_GROUP = {form: group for group in _PARTICLE_ALLOMORPH_GROUPS for form in group}


def _matching_particle_allomorph(replacement: str, tail: str) -> tuple[str | None, int]:
    """단어를 치환한 뒤(예: "벙어리"->"언어장애인"), 바로 뒤에 오는 조사가
    새 단어의 받침 유무와 안 맞으면("언어장애인가"는 틀림, "언어장애인이"가
    맞음) 맞는 형태로 바꿔 돌려준다.

    반환값: (바꿀 조사 또는 None, 원문에서 지워야 할 길이). 조사가 아니거나
    이미 맞는 형태면 (None, 0)을 돌려줘 원문 그대로 둔다."""
    if not tail or tail[0] not in _PARTICLE_TO_GROUP:
        return None, 0
    with_batchim, without_batchim = _PARTICLE_TO_GROUP[tail[0]]
    desired = with_batchim if _has_batchim(replacement) else without_batchim
    if tail[0] == desired:
        return None, 0
    return desired, 1


def _apply_replacements(text: str, mapping: dict) -> tuple[str, list[str]]:
    """mapping의 각 (원문, 정답) 쌍을 text에 적용한다. 긴 표현부터 먼저
    치환해서, 짧은 표현이 긴 표현의 일부일 때 잘못 겹쳐 치환되는 사고를
    막는다 (예: '벙어리장갑'을 '벙어리'보다 먼저 처리).

    또한 kiwi 토큰 경계와 정확히 일치하는 위치만 교체한다 — 그렇지 않으면
    "재판장님"(재판장+님)처럼 전혀 무관한 긴 단어 안에 짧은 표현("장님")이
    우연히 부분 문자열로 들어있는 경우까지 잘못 건드려 "재판시각장애인" 같은
    사고가 생긴다. 단순 글자 일치가 아니라 실제로 그 형태소 그대로 등장한
    경우에만 교정을 적용한다."""
    corrected = text
    applied = []
    for wrong, right in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        if wrong not in corrected:
            continue
        tokens = _kiwi.tokenize(corrected)
        token_starts = {t.start for t in tokens}
        token_ends = {t.start + t.len for t in tokens}
        matches = []
        search_from = 0
        while True:
            idx = corrected.find(wrong, search_from)
            if idx == -1:
                break
            end = idx + len(wrong)
            if idx in token_starts and end in token_ends:
                matches.append(idx)
            search_from = idx + 1
        if not matches:
            continue
        for idx in sorted(matches, reverse=True):
            end = idx + len(wrong)
            tail = corrected[end:]
            new_particle, old_len = _matching_particle_allomorph(right, tail)
            if new_particle is not None:
                corrected = corrected[:idx] + right + new_particle + corrected[end + old_len :]
            else:
                corrected = corrected[:idx] + right + tail
        applied.append(f"{wrong} -> {right}")
    return corrected, applied


def correct_always_wrong(text: str) -> tuple[str, list[str]]:
    """문맥과 무관하게 예외 없이 항상 틀린 표현을 자동으로 고친다
    (예: '그리고 나서' -> '그러고 나서'). 국립국어원 API로 조회하는 게
    아니라 잘 알려진 관용적 오용 사례를 직접 정리한 목록(common_errors.py)에
    근거하므로, 초코렛->초콜릿 같은 kornorms 확정 오류와 같은 성격이다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    return _apply_replacements(text, ALWAYS_WRONG)


def correct_mot_hada_compound(text: str) -> tuple[str, list[str]]:
    """부사 뒤의 '하다'가 표준어에서 '못하다'로 굳은 자리에 '못'을 넣는다
    ('안절부절했다' -> '안절부절못했다', `docs/BACKLOG.md` 24번).

    **왜 별도 규칙인가**: 이 부류는 낱말 치환이 아니라 **용언 활용형**을 바꿔야 한다.
    `ALWAYS_WRONG` 같은 표기 치환 목록으로는 '안절부절하다' 하나만 잡히고 '안절부절했다'
    ·'안절부절하지'·'안절부절해'는 놓친다(평가셋 g05가 이 이유로 실패했다). 활용형은
    형태소 경계에서 다뤄야 한다 — '하'(XSV/VV) 앞에 '못'을 끼우면 활용은 그대로 남는다.

    **근거는 부정 근거다**(§58 분류): 원문 형태(`부사+하다`)가 사전에 **없고**
    `부사+못하다`가 표제어일 때만 바꾼다. 표준어 규정 제25항이 '안절부절못하다'를
    표준으로, '안절부절하다'를 버림으로 정한 자리가 이 조건에 그대로 걸린다
    (실측: `word_exists('안절부절하다')`=False, `word_exists('안절부절못하다')`=True).
    부사 자체도 표제어여야 한다 — kiwi가 모르는 낱말을 MAG로 태깅한 경우를 막는다.

    코퍼스 622줄에서 이 조건에 걸리는 부사는 '안절부절' 하나뿐이었다. '잘'·'그만'·
    '더'·'우당탕'은 `부사+하다`가 표제어라 대상이 아니다(2026-08-04 실측).

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    tokens = _kiwi.tokenize(text)
    cuts = []  # (부사 끝, '하' 시작) — 이 사이를 '못'으로 채운다
    for i in range(1, len(tokens)):
        adverb, hada = tokens[i - 1], tokens[i]
        if hada.form != "하" or hada.tag not in ("XSV", "VV"):
            continue
        if adverb.tag != "MAG":
            continue
        gap_start, gap_end = adverb.start + adverb.len, hada.start
        if text[gap_start:gap_end] not in ("", " "):
            continue  # 붙여 쓰거나 한 칸 띄어 쓴 자리만
        stem = adverb.form
        if not word_exists(stem) or word_exists(stem + "하다") or not word_exists(stem + "못하다"):
            continue
        cuts.append((gap_start, gap_end))
    if not cuts:
        return text, []
    corrected = text
    applied = []
    for gap_start, gap_end in sorted(cuts, reverse=True):
        # 로그는 **어절 단위**로 남긴다 — edit_guard가 이 로그로 결과를 재구성해
        # 검증하므로, 잘린 조각을 남기면 정당한 교정이 막힌다(fail-closed).
        word_start = corrected.rfind(" ", 0, gap_start) + 1
        word_end = corrected.find(" ", gap_end)
        word_end = len(corrected) if word_end == -1 else word_end
        before_word = corrected[word_start:word_end]
        corrected = corrected[:gap_start] + "못" + corrected[gap_end:]
        after_word = corrected[word_start : word_end + len("못") - (gap_end - gap_start)]
        applied.append(f"{before_word} -> {after_word}")
    return corrected, list(reversed(applied))


def correct_nonstandard_terms(text: str) -> tuple[str, list[str]]:
    """우리말샘이 "규범 표기는/표준 용어는 'X'이다"로 이미 명시해 둔 비표준
    표기(예: "요오드"->"아이오딘")를 자동 교정한다.

    correct_always_wrong()의 ALWAYS_WRONG(정적 목록)이나 correct_loanwords()의
    kornorms(외래어 표기 용례)와는 다른 세 번째 원천이다 — "요오드"는
    kornorms엔 오히려 정답으로("Jod"의 정식 번역어) 등재되어 있어
    correct_loanwords()로는 못 잡고, 우리말샘 자체의 표준화 안내에서만
    확인된다(실사용 검증으로 발견). 매번 실시간으로 우리말샘을 조회하므로
    정적 목록과 달리 국립국어원이 표준 용어를 바꿔도 코드 수정이 필요 없다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    replacements = {}
    tokens = _kiwi.tokenize(text)
    for t in tokens:
        # '-하다'가 바로 붙은 어근은 그 자체가 다른 낱말의 일부다. '힙하다'(우리말샘
        # 표제어)의 '힙'을 우리말샘의 다른 항목(hip = 신체 부위, 규범 표기 '히프')으로
        # 바꿔 '히프한 동네'가 됐다(2026-08-03 사용자 제공 자막 4강 132번).
        if is_hada_stem(tokens, t):
            continue
        # 부사(MAG)를 뺐던 탓에 '일찌기'('일찍이'의 비표준 표기, 우리말샘이 규범
        # 표기를 명시)가 그대로 나갔다 — 같은 성격의 명사 '눈쌀'·'설겆이'는 잡히는데
        # 부사만 새던 것이다(2026-08-03 평가셋 확대에서 g17로 드러남). 코퍼스의
        # 부사 90종을 전수 조회해 새로 바뀌는 것이 '일찌기'->'일찍이', '웬지'->'왠지'
        # 둘뿐이고 둘 다 정답임을 확인한 뒤 넓혔다.
        # 사전에 없는 복합어의 **조각**은 고치지 않는다. `매직블럭`이 `매직`+`블럭`으로
        # 쪼개져 `매직블록`이 됐다 — 상표 이름이 조용히 바뀐 것이다(2026-08-05 사용자
        # 지적). 모르는 말의 일부만 규칙으로 고치는 것은 원리 1(조각 대조)이 금지한다.
        # `correct_loanwords()`에 넣은 것과 같은 가드다.
        if _inside_unknown_compound(text, tokens, t):
            continue
        if t.tag not in ("NNG", "NNP", "MAG"):
            continue
        # 된소리 구어형이 사전 표제어면(빤스→빤쓰) 규범 표기로 자동 바꾸지 않고
        # check_colloquial_loanword()가 말투 보존 여부를 사람에게 묻는다.
        if _tensified_headword_variant(t.form):
            continue
        replacement = standard_term_replacement(t.form)
        if replacement:
            replacements[t.form] = replacement
    if not replacements:
        return text, []
    return _apply_replacements(text, replacements)


def correct_discriminatory_terms(text: str) -> tuple[str, list[str]]:
    """차별적·비하적 표현은 관례냐 아니냐를 따질 문제가 아니라 항상 바꿔야
    하므로 자동으로 교정한다 (예: '간질' -> '뇌전증').

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    return _apply_replacements(text, DISCRIMINATORY_TERMS)


# 뜻풀이에서 문맥 대조에 쓸 내용어 태그. 조사·어미는 어느 문장에나 있어 근거가 안 된다.
_DEFINITION_CONTENT_TAGS = ("NNG", "NNP", "VV", "VA")


# 어느 뜻풀이에나, 어느 문장에나 나오는 낱말. 겹쳐도 아무 근거가 되지 않는다 —
# `있다` 하나 때문에 '건초 더미에 누웠다'가 `힘줄집`("…싸고 있는 것") 뜻으로
# 읽혔다(2026-08-05 실측). 뜻을 가르는 신호가 아니라 문장을 잇는 말들이다.
#
# `document_context`는 문서 전체를 문맥으로 쓴다(자막 한 편은 화제가 이어지므로
# 정당한 설계 — 위 함수 docstring 참고). 그런데 여러 화제가 섞인 문서(예: 서로
# 무관한 기사 여러 건을 묶은 프로즈 텍스트)에서는 전혀 무관한 문장의 흔한 낱말이
# 우연히 겹쳐 같은 사고를 낸다 — '건강'·'들다'·'올리다' 때문에 '정수'(精髓, 흔한
# 뜻)가 '양수'의 옛 용어로 오탐지됐다(2026-09-02 실사용 감수, 뉴스 기사 10건
# 묶음 텍스트). 같은 부류라 같은 목록에 추가한다.
_CONTEXT_STOP_LEMMAS = frozenset({
    "있다", "없다", "하다", "되다", "같다", "보다", "주다", "쓰다", "가지다",
    "만들다", "넣다", "이르다", "나타내다", "위하다", "대하다", "따르다",
    "많다", "적다", "크다", "작다", "높다", "낮다", "좋다", "길다",
    "사람", "모양", "상태", "경우", "정도", "방법", "부분", "따위", "이것", "그것",
    "들다", "올리다", "건강", "시작",
})


def _content_lemmas(text: str) -> set[str]:
    return {
        t.lemma
        for t in _kiwi.tokenize(text)
        if t.tag.startswith(_DEFINITION_CONTENT_TAGS)
        and len(t.lemma) >= 2
        and t.lemma not in _CONTEXT_STOP_LEMMAS
    }


def _specialist_reading_supported(target: str, context: str, surface: str) -> bool:
    """문서가 **전문 분야 뜻으로 읽을 근거**를 주는지 — 없으면 플래그하지 않는다.

    `건초`는 우리말샘에 다섯 뜻이 있다: 일반어 '베어서 말린 풀', 역사 연호 셋,
    그리고 의학 '힘줄집'(옛 용어). 그런데 **'건초는 베어서 말린 풀이다'라는 문장에도
    옛 용어 플래그가 붙었다**(2026-08-05 사용자 보고) — 문맥이 정의를 말하고 있는데도.

    판정에 쓰는 신호는 둘이고, 둘 다 사전이 준 것이다.

    ① **분야 일치**: `surface`(예: '건초')의 "전 용어" 뜻 그 자체에 분야가 달려
       있으면(`former_term_field`), 문서의 다른 낱말이 **정확히 같은 분야로만**
       쓰이는 낱말인지(`specialist_only_fields`) 본다(`힘줄집`=의학, `반지름`=
       수학처럼 일반 뜻이 아예 없는 낱말만 근거로 인정). **계열(비슷한 분야를
       묶은 그룹)로 넓혀 보지 않는다**(2026-09-02, §94·BACKLOG 34번) — 예전엔
       {수학·물리·화학·천문·지구}를 한 계열로 묶어 근거로 인정했는데, 그 폭이
       근거 없이 넓어서 '방안'(→모눈, 수학)이 무관한 '플라스틱'·'활성'(둘 다
       화학 전용 낱말) 때문에 오탐지됐다. 이 계열 묶음이 실제로 필요한
       회귀 테스트는 하나도 없었다(기존 테스트는 전부 `힘줄`=의학·`반지름`=
       수학처럼 정확히 같은 분야로 이미 통과하고 있었다) — 그래서 안전하게
       지웠다.
    ② **뜻풀이 낱말 겹침**: 문서의 낱말이 그 표준 용어의 뜻풀이에 나오는가
       (`뇌전증`의 뜻풀이에 '발작'이 있고, '환자가 간질 발작을 일으켰다'에도 있다).

    ②가 필요한 이유: `cat` 표시는 **전문어 뜻에만** 달려 있어 흔한 의학 낱말이
    빠진다 — `환자`는 경제·역사, `치료`·`곤충`은 아예 표시가 없다(실측). ①만 쓰면
    정작 병명 문맥을 놓친다.

    **①은 양쪽 다 "그 뜻 하나만" 보도록 좁혔다**(2026-09-02 수정, §90·§92·
    BACKLOG 34번). 처음엔 `target`(교체 목표어) 쪽만 `sense_fields(target)`
    (모든 뜻)에서 `former_term_field(surface)`(그 "전 용어" 뜻 하나)로 좁혀
    '정수'→'양수' 오탐지(§90)를 고쳤는데, 검증하다 **문맥 낱말 쪽도 같은
    문제**를 새로 발견했다 — '감독'·'허가'처럼 일반 뜻과 무관한 전문 뜻(가톨릭
    성직 등)이 같이 있는 낱말이 그 무관한 뜻의 분야로 문맥 신호를 오염시켜
    '방안'→'모눈'·'소재'→'금육재'가 오탐지됐다(§92). `sense_fields(lemma)`
    (그 낱말의 모든 뜻)를 `specialist_only_fields(lemma)`(일반 뜻이 하나도
    없는 낱말만 인정)로 바꿔 양쪽 다 정밀하게 막는다.

    **이 판정은 플래그를 줄이는 방향으로만 쓴다.** 근거가 없으면 조용히 넘어갈 뿐
    텍스트를 바꾸지 않으므로, 판정이 틀려도 잃는 것은 제안 하나다(자동 교정에는
    이 신호를 쓰지 않는다 — 뜻이 하나뿐인 옛 용어는 지금처럼 문맥과 무관하게 바꾼다).
    """
    context_lemmas = _content_lemmas(context) - {surface}
    if not context_lemmas:
        return False
    source_field = former_term_field(surface)
    if source_field:
        for lemma in context_lemmas:
            if source_field in specialist_only_fields(lemma):
                return True
    definition_lemmas: set[str] = set()
    for definition in headword_definitions(target):
        definition_lemmas |= _content_lemmas(definition)
    return bool(context_lemmas & definition_lemmas)


def correct_former_terms(
    index: int, text: str, context: str | None = None
) -> tuple[str, list[str], list[FlagItem]]:
    """표준국어대사전이 "'X'의 전 용어"로 표시한 옛 용어(지양 대상)를 처리한다.

    correct_nonstandard_terms()가 우리말샘의 "규범 표기는/표준 용어는" 안내를
    보는 것과 원천만 다를 뿐 같은 성격의 실시간 동적 규칙이다 — 정적 목록이
    아니라 매번 표준국어대사전을 조회하므로 국립국어원이 표준 용어를 바꿔도
    코드 수정이 필요 없다.

    안전 규칙(동형이의어 오교정 방지):
    - 모든 뜻이 "전 용어" 뜻인 단어(예: "정신분열증" → 전부 "조현병"의 전 용어)는
      문맥과 무관하게 하나의 정답만 있으므로 조용히 자동 교정한다.
    - "전 용어" 뜻 외에 다른 뜻도 있는 동형이의어(예: "간질" — 옛 용어(뇌전증)
      외에 곤충·조직·'간질거리다' 어근 뜻도 있음)는 **절대 자동 교정하지 않는다.**
      다만 2026-08-05부터, 문서에 그 전문 분야 뜻으로 읽을 근거가 하나도 없으면
      플래그도 남기지 않는다(`_specialist_reading_supported` 참고). '건초는 베어서
      말린 풀이다'라는 문장에까지 '힘줄집' 제안이 붙던 것을 막는다. 근거가 있으면
      지금처럼 다른 뜻들을 사유에 실어 사람에게 넘긴다.

    `context`는 문맥 판정에 쓸 텍스트다(기본값은 그 줄 자체). 자막은 한 줄이 짧아
    문서 전체를 넘기면 판정이 훨씬 정확해진다 — `correct_entries()`가 그렇게 부른다.

    반환값: (수정된 텍스트, 자동 교정 로그: '원문 -> 정답', 확인 플래그 목록)

    kiwi는 "정신분열증"을 "정신"+"분열증"으로 쪼갠다 — 그런데 "정신분열증"
    (정신^분열증)은 통째로 하나의 옛 용어 표제어다. 개별 토큰만 조회하면
    "분열증"만 잡혀 "정신조현병" 같은 오교정이 난다. 그래서 공백 없이 바로
    이어진 명사 토큰들의 최대 구간에서 **긴 결합부터** 사전을 조회해, 여러
    형태소로 이루어진 옛 용어(정신분열증)를 한 단위로 처리한다."""
    tokens = _kiwi.tokenize(text)
    noun_tags = ("NNG", "NNP")
    n = len(tokens)
    auto_replacements: dict[str, str] = {}
    flags: list[FlagItem] = []
    flagged: set[str] = set()

    i = 0
    while i < n:
        if tokens[i].tag not in noun_tags:
            i += 1
            continue
        # 공백 없이 바로 이어진 명사 토큰들의 최대 구간(run)을 모은다.
        j = i
        while (
            j + 1 < n
            and tokens[j + 1].tag in noun_tags
            and tokens[j + 1].start == tokens[j].start + tokens[j].len
        ):
            j += 1
        # run 안에서 긴 결합부터 그리디 매칭 — 가장 긴 옛 용어를 한 단위로 잡는다.
        p = i
        while p <= j:
            matched = False
            for q in range(j, p - 1, -1):
                surface = text[tokens[p].start : tokens[q].start + tokens[q].len]
                result = former_term_lookup(surface)
                if result is None:
                    continue
                # '수강생'처럼 이 명사(수강)가 뒤따르는 접미사(생/XSN)와 결합해
                # 별개의 표제어를 이루면, 그 안의 '수강'을 옛 용어로 보지 않는다
                # (더 긴 표제어 우선 — '수강생'은 '수강(옛 용어)'과 무관한 단어).
                k = q + 1
                while (
                    k < n
                    and tokens[k].tag == "XSN"
                    and tokens[k].start == tokens[k - 1].start + tokens[k - 1].len
                ):
                    k += 1
                if k > q + 1:
                    extended = text[tokens[p].start : tokens[k - 1].start + tokens[k - 1].len]
                    if word_exists(extended):
                        p = q + 1
                        matched = True
                        break
                target = result["target"]
                if not result["ambiguous"]:
                    auto_replacements[surface] = target
                elif not _specialist_reading_supported(target, context or text, surface):
                    # 문서 어디에도 그 전문 분야 뜻으로 읽을 근거가 없다 — 묻지 않는다
                    # (`건초는 베어서 말린 풀이다`, 2026-08-05 사용자 보고). 신호①이
                    # 이제 소스·문맥 양쪽 다 "일반 뜻이 없는 낱말"만 근거로 인정하므로
                    # (`specialist_only_fields`, 2026-09-02, §92·BACKLOG 34번), 그
                    # 결과를 여기서 다시 뒤집지 않는다 — 예전엔 여기 `elif
                    # former_term_field(surface): pass`가 있어서 분야가 달린 옛
                    # 용어는 문맥이 맞아도 항상 억제됐다(잠복 버그, '원통의 반지름을
                    # 구해 보자'로도 한 번도 안 물었었다).
                    pass
                elif surface not in flagged:
                    flagged.add(surface)
                    others = "; ".join(result["other_meanings"])
                    flags.append(
                        FlagItem(
                            line_index=index,
                            original_text=text,
                            reason=(
                                f"표준국어대사전이 '{surface}'을(를) '{target}'의 전 용어(옛 "
                                f"용어)로 표시함 — 지양 대상이나, '{surface}'에 다른 뜻도 있어 "
                                f"자동 교정하지 않고 플래그만 남김(문맥으로 판단 필요). "
                                f"다른 뜻: {others}"
                            ),
                            suggested_fix=target,
                        )
                    )
                p = q + 1
                matched = True
                break
            if not matched:
                p += 1
        i = j + 1

    corrected, applied = text, []
    if auto_replacements:
        corrected, applied = _apply_replacements(text, auto_replacements)
    return corrected, applied, flags


# 준말 -> 본말. **둘 다 표준**이라 자동 교정하지 않고 확인 플래그만 남긴다
# (2026-08-03 사용자 지정). 항목마다 사전 근거를 적는다 — 표준어끼리의 임의 치환은
# 이 프로젝트가 막으려는 부류이므로(평가셋 t12: '도리어'를 '되레'로 바꾸지 않는다),
# 근거 없이 늘리면 안 된다.
_CONTRACTIONS_TO_FULL_FORM = {
    # 표준국어대사전 '아냐'(감탄사): "'아니야'의 준말." 서술어로 쓰인 '아냐'
    # ('내 잘못이 아냐' = 아니다 + -야)도 같은 준말이다.
    "아냐": "아니야",
}


def check_contracted_form(index: int, text: str) -> FlagItem | None:
    """준말을 본말로 펴는 후보를 확인 플래그한다('아냐' -> '아니야').

    자동 교정하지 않는 이유: 준말도 본말도 표준이다. 어느 쪽을 쓸지는 대사의 말투와
    납품처 기준이 정하는 문제라 사전으로 답이 나오지 않는다. 어절 단위로만 본다 —
    '아냐도'처럼 조사가 붙은 형태나 낱말 안('개아냐')은 건드리지 않는다.
    """
    for short, full in _CONTRACTIONS_TO_FULL_FORM.items():
        for match in re.finditer(rf"(?<![^\s(\[\"']){re.escape(short)}(?![^\s,.!?…)\]\"'])", text):
            suggested = text[: match.start()] + full + text[match.end() :]
            return FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=suggested,
                reason=(
                    f"'{short}'{_josa(short, '는')} 표준국어대사전에 \"'{full}'의 준말\"로 등재된 "
                    "표준 표기입니다. "
                    f"둘 다 맞으므로 자동으로 바꾸지 않았습니다 — 본말로 펴려면 '{full}'입니다."
                ),
            )
    return None
