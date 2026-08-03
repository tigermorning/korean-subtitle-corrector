"""kiwi 형태소 분석기 어댑터.

`_kiwi` 인스턴스는 **이 모듈에만** 존재한다. 모듈마다 `Kiwi()`를 새로 만들면
메모리가 배로 늘고(모델 약 310MB), `register_custom_words()`로 등록한 고유명사가
다른 모듈에 전달되지 않아 "kiwi가 이름을 쪼개는" 버그가 되살아난다.
형태소 태그 집합과 토큰 조회 도구도 여기 모은다.
"""

from collections import Counter
from kiwipiepy import Kiwi
from ..dictionary import word_exists
from .text_utils import _bracket_spans, _inside_any_span, _word_bounds

# NNP(고유명사)는 여기서 제외한다. 사람 이름 같은 고유명사는 표준국어대사전에
# 등재돼 있지 않은 게 정상이라, 포함시키면 "지민", "민준" 같은 멀쩡한 이름을
# 전부 "사전에 없는 단어"로 오탐지하게 된다 (부산대 맞춤법 검사기가 사람 이름을
# 이상하게 바꾼다는 지적과 같은 종류의 문제).
_SPELLING_CHECK_TAGS = {"NNG", "VV", "VA"}


_LOANWORD_TAGS = {"NNG", "NNP"}


# 조사(J*)·어미(E*)·파생접미사(XS*)·서술격 조사 '이다'(VCP): 한글 맞춤법
# 제41항에 따라 앞말에 무조건 붙여 쓰는 형태소. "이 태그가 다음 토큰이면
# 앞말에 붙인다"는 방향은 예외가 없어 항상 안전하다.
_ATTACH_TAGS = {
    "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
    "EP", "EF", "EC", "ETN", "ETM",
    "XSN", "XSA", "XSV",
    "VCP",
}


# 반대 방향("이 태그 다음에는 항상 공백")은 더 좁게 잡아야 한다. 예를 들어
# ETM(관형사형 어미)은 항상 다음에 명사가 와야 하는 어미인데, 그 명사와
# 합쳐서 하나의 합성어가 될 수도 있다(예: '쓴'+'맛' = '쓴맛', 이미
# _compound_candidate_spans()가 사전으로 확정하는 영역). 그래서 여기서는
# "무조건 공백"을 조사와 문장 단위를 끝내는 어미(EF·EC)·서술격 조사에만
# 한정한다 — 이들 뒤에 오는 건 항상 완전히 새로운 어절이지, 앞 형태소와
# 합쳐질 수 있는 후보가 아니다.
_MANDATORY_BOUNDARY_TAGS = {
    "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
    "EF", "EC", "VCP",
}


# 문장부호/기호는 새 어절의 시작으로 보지 않는다 — 종결어미 뒤에 마침표가
# 바로 붙는 "먹었다." 같은 경우까지 공백을 강제하면 안 되기 때문.
_PUNCT_TAG_PREFIX = "S"


# 보조용언(VX)과 의존명사(NNB)는 앞말과 붙여 쓸지 띄어 쓸지가 제47항/제42항의
# 예외 규정(붙임 허용)에 따라 갈리는 영역이라, 여기서는 판단하지 않고
# _normalize_aux_verb_spacing() 등 전용 로직에 맡긴다 — 예를 들어 '해보자'의
# 어미(EC) 뒤에 오는 '보다'(VX)에 공백을 강제하면 '해 보자'가 되어, 붙여 써도
# 맞는 형태('해보자')를 오히려 틀린 형태로 바꿔버리게 된다.
_AMBIGUOUS_FOLLOW_TAGS = {"VX", "NNB"}


_kiwi = Kiwi()


def register_custom_words(words: list[str], tag: str = "NNP") -> None:
    """번역가가 이 파일에 나오는 고유명사·요리/음료 이름을 미리 알려주면,
    kiwi가 이후 이 단어를 절대 잘못 쪼개지 않는다. kiwi는 모르는 단어를
    통계적으로 추측해서 쪼개다가("연실"->"연 실", "탄두리치킨"->"탄두 리
    치킨") 실제로 사고를 내는데, 사전에 근거가 없는 단어(주로 사람 이름
    같은 고유명사)는 이 방법이 유일하게 확실한 해법이다.

    인명·요리/음료 이름 모두 tag="NNP"(고유명사)로 등록해도 무방하다 —
    이 프로젝트에서 이 태그는 "kiwi야, 이 단어는 절대 쪼개지 마"라는
    표시로만 쓰이고, 다른 로직에 미치는 영향(맞춤법 검사 제외 등)도 둘 다
    바라는 방향과 같다. 같은 프로세스 내에서는 계속 유지되는 전역 상태
    이지만, 이미 맞는 단어를 하나 더 알아듣게 하는 것뿐이라 다른 파일
    처리에 영향을 주지 않는다."""
    for word in words:
        word = word.strip()
        if word:
            _kiwi.add_user_word(word, tag)


def detect_recurring_unknown_words(entries: list, min_count: int = 3) -> list[str]:
    """전체 문서에서 사전에 없지만 여러 번 반복되는 명사를 찾는다.

    오타는 문서 전체에서 우연히 같은 형태로 여러 번 반복될 가능성이 낮은
    반면, 캐릭터 이름이나 요리명은 같은 문서 안에서 계속 똑같이 쓰인다.
    이 빈도 차이를 이용해, 번역가가 목록을 따로 적지 않아도 자동으로
    "이건 아마 고유명사다"라고 짐작하는 것이다. register_custom_words()로
    등록해서 실제 쪼개짐을 막는 것과 한 쌍으로 쓴다."""
    from collections import Counter

    counts = Counter()
    for e in entries:
        for t in _kiwi.tokenize(e.text):
            if t.tag in ("NNG", "NNP") and not word_exists(t.form):
                counts[t.form] += 1
    return [word for word, count in counts.items() if count >= min_count]


def _content_lemmas(text: str) -> list[str]:
    brackets = _bracket_spans(text)
    return [
        t.lemma
        for t in _kiwi.tokenize(text)
        if t.tag in _SPELLING_CHECK_TAGS and not _inside_any_span(t.start, brackets)
    ]


def _merged_particle_reading_exists(text: str, t1, t2) -> bool:
    """t1(조사)과 뒤 음절이 실은 **하나의 조사**일 수 있는지 kiwi 후보로 확인한다.

    2026-08-02 실사용: '개나리길 입구에서 봐'가 '개나리길 입구에 서 봐'로 자동
    교정됐다. kiwi 1순위 분석이 '에'(JKB)+'서'(서다)였기 때문인데, 2순위 후보는
    '에서'(JKB) 하나다. 둘 다 문법적으로 가능한 문장이라('입구에서 보자' /
    '입구에 서 봐라') 어느 쪽인지는 문맥이 정한다 — 자동으로 고를 일이 아니다.

    판정 근거는 kiwi 자신의 대안 분석이다(확률적 추측이 아니라 "다른 읽기가
    존재한다"는 사실). 원문이 이미 띄어 쓰여 있으면 그 읽기 자체가 생기지 않으므로
    이 함수는 붙어 있는 경우에만 쓴다.
    """
    start, end = _word_bounds(text, t1.start)
    word = text[start:end]
    if not word:
        return False
    offset = t1.start - start
    for tokens, _score in _kiwi.analyze(word, top_n=5):
        for token in tokens:
            if not token.tag.startswith("J"):
                continue
            # 같은 자리에서 시작하면서 t1보다 길게 뻗은 조사 = 합쳐 읽은 후보
            if token.start == offset and token.len > t1.len:
                return True
    return False


_PUNCT_TAG_PREFIXES = ("S",)  # kiwi 문장부호 계열 태그(SF/SP/SS/SE/SO/SW ...)


def _is_punct_token(tok) -> bool:
    return tok.tag.startswith(_PUNCT_TAG_PREFIXES)


def _has_determiner_reading(text: str, token) -> bool:
    """감탄사로 태깅된 토큰이 실은 관형사('그 빌리지', '이 사람')일 수 있는지.

    2026-08-02 실사용: '그 빌리지에 살아'가 '그, 빌리지에 살아'로 자동 교정됐다.
    kiwi가 관형사 '그'를 감탄사(IC)로 태깅했기 때문이다. 판정 근거는 kiwi 자신의
    대안 분석이다 — 같은 자리를 관형사(MM)로 읽는 후보가 있으면 둘 중 어느 쪽인지는
    문맥이 정하므로, 쉼표를 넣지 않는다('에서' 과교정에서 쓴 것과 같은 방식).

    소유격 준말('네 책임이 아냐'의 '네' = 너+의)도 같은 부류다. kiwi는 이 자리를
    대명사+관형격 조사(NP+JKG)로 읽는 후보를 내놓는다 — 그 후보가 있으면 뒤 체언을
    꾸미는 관형어일 수 있으므로 쉼표를 넣지 않는다(2026-08-03 사용자 보고로 추가:
    '네 책임이 아냐'가 '네, 책임이 아냐'로 바뀌었다).
    """
    for tokens, _score in _kiwi.analyze(text, top_n=5):
        for i, candidate in enumerate(tokens):
            if candidate.start != token.start:
                continue
            if candidate.tag == "MM":
                return True
            # 대명사 + 관형격 조사('너'+'의') = 관형어 읽기
            if candidate.tag == "NP" and i + 1 < len(tokens) and tokens[i + 1].tag == "JKG":
                return True
    return False


def _straddling_tokens(tokens, pos: int):
    """원문 상의 한 지점(pos) 바로 앞/뒤에 붙어 있는 토큰을 찾는다."""
    before = after = None
    for t in tokens:
        if t.start + t.len <= pos:
            before = t
        if after is None and t.start >= pos:
            after = t
    return before, after


def _token_containing(tokens, pos: int):
    """pos가 토큰 경계가 아니라 어떤 토큰의 내부에 있으면 그 토큰을 찾는다.

    kiwi.tokenize()와 kiwi.space()는 서로 다른 내부 모델이라 가끔 어긋난다
    — tokenize()는 '연실'을 고유명사 토큰 하나로 보는데 space()는 그
    토큰 한가운데에 공백을 넣자고 제안하는 식이다("연실"->"연 실"). 이건
    kiwi 스스로도 이 단어를 확신하지 못한다는 신호이므로, 근거 확인 없이
    바로 되돌려야 한다."""
    for t in tokens:
        if t.start < pos < t.start + t.len:
            return t
    return None


def _tokenization_unstable_near(tokens, before, after) -> bool:
    """before/after 주변에 길이가 0인 토큰(완전히 생략된 형태소)이 있는지
    확인한다 — kiwi 자신도 이 구간의 형태소 경계를 확신하지 못한다는 신호다.

    "없다잖나"("없다"+"고"+"하"(길이 0, "하다"가 통째로 생략됨)+"지"+"않"+
    "나")처럼 압축된 구어체 표현을 kiwi가 내부적으로 재구성하다가, 실제
    발화에는 아예 없는 형태소를 길이 0으로 끼워 넣는 경우가 있다. 이런
    경우 `_straddling_tokens()`(위치 기반 검색)조차 엉뚱한 토큰을 짚어올
    수 있어(길이 0인 토큰과 실제 토큰이 같은 위치를 다투다 하나만 우연히
    골라짐), 사전 조회로 검증할 신뢰할 만한 후보 자체를 만들 수 없다 —
    "kiwi는 참고일 뿐, 사전 표제어가 기준"이라는 원칙에 따라, 이런
    자기모순적 구간은 kiwi의 공백 제안을 아예 신뢰하지 않고 원문 그대로
    보존한다.

    단순 위치 겹침(overlap)은 신호로 쓰지 않는다 — "됩니다"(되+ㅂ니다)처럼
    어간과 어미가 받침 하나를 공유해 위치가 겹치는 것은 지극히 정상적인
    활용이라, 겹침 자체를 "불안정"으로 보면 정상적인 활용까지 오탐지하게
    된다(실사용 버그로 확인됨 — "그러면 안됩니다"의 정당한 "안 됩니다"
    분리 제안이 막혀버림). 길이 0(형태소 자체가 완전히 생략됨)만 이례적인
    신호로 취급한다."""
    idx_before = _token_index(tokens, before)
    idx_after = _token_index(tokens, after)
    window = []
    if idx_before is not None:
        window.extend(tokens[max(0, idx_before - 1) : idx_before + 1])
    if idx_after is not None:
        window.extend(tokens[idx_after : idx_after + 2])
    return any(t.len == 0 for t in window)


def _token_index(tokens, target) -> int | None:
    for i, t in enumerate(tokens):
        if t is target:
            return i
    return None


# 전문 용어·고유명사 성격의 복합 표현(부대명, 편제 번호, 알파벳 약칭 등)에
# 흔히 등장하는 태그들. 한글 맞춤법 제49항(고유 명사)·제50항(전문 용어)은
# "단어별로 띄어 씀을 원칙으로 하되, 붙여 쓸 수 있다"고 명시적으로 허용한다
# — 즉 이미 붙여 쓰여 있다면 그 자체가 허용된 표기이므로, 사전에 그 정확한
# 조합이 개별 표제어로 없다는 이유만으로 갈라놓으면 안 된다. 제44항(수
# 표기: 만 단위 이내는 붙여 씀)에 해당하는 숫자+수사(NR, 예: "20만"의 "만")
# 조합도 같은 이유로 포함한다. 의존명사(NNB)는 제외한다 — 관형사형+의존명사
# 붙임은 제42항에 따라 실제로 항상 띄어 써야 하는 별개의 규칙이라, 여기
# 포함하면 정당한 오류까지 숨겨버리게 된다.
_TERM_COMPOUND_TAGS = {"NNG", "NNP", "SN", "SL", "XPN", "NR"}


# 숫자(SN) 바로 뒤에 붙는 기호(SW, %/$/# 등)는 항상 붙여 쓴다 — 이건
# 사전 등재 여부를 따질 대상이 아니라 순수 표기 관례("80%"를 "80 %"로
# 쓰지 않음)라, 별도로 항상 보호한다.
_NUMBER_SYMBOL_TAGS = {"SN", "SW"}


# 용어 후보를 이룰 수 있는 태그. _TERM_COMPOUND_TAGS(붙여 쓴 것을 보호하는 쪽)에
# 어근(XR: '강력')과 명사 파생 접미사(XSN: '골수성'의 '성')를 더한다 — 둘 다 용어
# 안쪽에만 나타나고 앞말과 항상 붙으므로, 빼면 '강력팀'·'골수성'에서 후보가
# 끊겨 같은 용어의 두 표기를 짝지을 수 없다.
_TERM_RUN_TAGS = _TERM_COMPOUND_TAGS | {"XR", "XSN"}


def _has_predicate_reading(text: str, token) -> bool:
    """감탄사로 태깅된 자리를 **용언으로 읽는 대안 분석**이 있는지.

    '무슨 일인데 그래?'의 '그래'는 '그렇다'의 활용(서술어)이다. 서술어 앞에 쉼표를 넣으면
    문장이 갈라진다(2026-08-04 사용자 제공 자막 5강 334번). 대명사·명사 읽기까지 넓히면
    '싫다면 뭐'(대명사 '뭐'도 있다)처럼 이미 정답으로 확정한 교정까지 막히므로, 문장 끝
    자리에서는 용언 읽기만 근거로 쓴다.
    """
    return _has_reading(text, token, ("VV", "VA", "VA-I", "VV-I", "VCP", "VCN"))


def _has_content_word_reading(text: str, token) -> bool:
    """감탄사로 태깅된 자리를 **명사나 용언으로 읽는 대안 분석**이 있는지.

    감탄사 뒤·앞에 쉼표를 넣는 규칙은 그 낱말이 정말 감탄사일 때만 맞다. kiwi는 명사와
    감탄사가 형태가 같은 말('아이' = 어린아이/감탄사, '참' = 참말로/감탄사)이나 서술어로
    읽히는 말('그래' = 그렇다의 활용)을 감탄사로 태깅할 때가 있다. 그 자리에 쉼표를
    넣으면 문장이 갈라진다 — 2026-08-04 사용자 제공 자막에서 '아이 심장이 선천적으로'가
    '아이, 심장이'로, '무슨 일인데 그래?'가 '무슨 일인데, 그래?'로 바뀌었다.

    판정 근거는 kiwi 자신의 대안 분석이다(확률적 추측이 아니라 "다른 읽기가 존재한다"는
    사실). 다른 읽기가 있으면 어느 쪽인지는 문맥이 정하므로 쉼표를 넣지 않는다.

    같은 자리에서 **같은 길이**로 읽는 후보만 본다. 길이를 안 보면 '아이고'(감탄사, 3자)를
    '아이'(명사, 2자)+'고'로 읽는 후보에 걸려 정당한 쉼표까지 막힌다 — 그건 같은 낱말을
    다르게 읽은 것이 아니라 아예 다른 분석이다.
    """
    return _has_reading(
        text,
        token,
        ("NNG", "NNP", "NNB", "NP", "NR", "VV", "VA", "VA-I", "VV-I", "VCP", "VCN"),
    )


def _has_reading(text: str, token, tags) -> bool:
    """token 자리를 같은 길이로 tags 중 하나로 읽는 대안 분석이 있는지."""
    for tokens, _score in _kiwi.analyze(text, top_n=5):
        for candidate in tokens:
            if (
                candidate.start == token.start
                and candidate.len == token.len
                and candidate.tag in tags
            ):
                return True
    return False
