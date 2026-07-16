"""자막 교정 엔진

세 가지를 확인한다:
1. 외래어 표기 — 국립국어원 어문 규범(kornorms)이 명시적으로 "이 표기는
   틀렸다"고 확정하고 정답까지 준 경우 자동으로 교정한다.
   - 일반 용어(예: 초코렛 -> 초콜릿): 문맥과 무관하게 하나의 공식 정답만
     있으므로 조용히 자동 반영하고 플래그하지 않는다.
   - 고유명사(NNP: 인명·지명·작품 제목 등): kornorms 정답이 하나뿐이든
     여러 관례가 공존하든 상관없이 텍스트에는 절대 자동 반영하지 않고
     항상 확인 플래그로만 제안한다. 예를 들어 "스노우"가 인명(스노우 기자)
     이면 표기 규칙대로 "스노"가 맞지만, 같은 표기가 영화 제목("스노우맨")
     처럼 배급사가 정한 고유 표기일 수도 있다 — 텍스트만으로는 이 둘을
     구분할 방법이 없으므로, 고유명사 표기는 자동화보다 안전을 우선한다.
2. 맞춤법 — 일반명사/동사/형용사 같은 내용어를 형태소 단위로 뽑아 사전 기본형
   (표제어)으로 복원한 뒤 표준국어대사전에 있는지 확인한다. 없으면 플래그만
   하고 자동 수정하지 않는다 (어떤 게 맞는 표기인지 알 수 없기 때문).
   고유명사(NNP, 사람 이름 등)는 이 검사에서 제외한다 — 정상적인 이름도
   사전 표제어가 아닌 경우가 대부분이라, 포함시키면 멀쩡한 이름을 전부
   오탐하게 된다.
3. 띄어쓰기 — 두 성격을 구분한다.
   - 조사·어미·접미사를 앞말에 붙이는 것(제1항/제41항)은 문맥과 무관하게
     항상 정답이 하나뿐이라 자동으로 정리한다(예: "오늘은날씨가좋네요" ->
     "오늘은 날씨가 좋네요"). 이건 "단어 경계가 어디인지 애매한" 문제가
     아니라 형태소 결합 규칙 자체가 예외 없이 고정되어 있어서다.
   - 내용어와 내용어가 바로 이어질 때(합성어처럼 하나로 합쳐질지 별개로
     남을지)는 '한번/한 번'처럼 의미에 따라 정답이 갈릴 수 있어, 사전으로
     확정되지 않는 한 절대 자동 적용하지 않고 플래그만 한다.
   - 예외적으로 보조 용언(제47항)은 "붙여 씀"이 허용되는 예외일 뿐 "띄어
     씀"이 원칙이므로, 붙여 쓴 형태를 항상 원칙(띄어쓰기) 형태로 자동
     통일한다 — 사용자가 붙여쓰기를 선호한다는 별도 지시가 없는 한.

주의: 이건 여전히 PRD 3단계 판단 엔진 중 1단계(사전/규범 근거)에 해당한다.
온라인가나다 아카이브 검색(2단계)은 아직 없다.
"""

import difflib
import re

from kiwipiepy import Kiwi

from .common_errors import ALWAYS_WRONG, CONFUSABLE_PAIRS, DISCRIMINATORY_TERMS, PURIFIED_TERMS
from .dictionary import compound_status, loanword_fix, usage_examples, word_exists
from .parsers import SubtitleEntry
from .report import FlagItem

# 자막의 "[이름/상황]" 같은 브래킷 표기는 실제 문장이 아니라 화자·상황을
# 표시하는 관례적 메타 표기라, 한글 맞춤법이 다루는 대상이 아니다. 이
# 안의 내용(예: "작게", "스피커")은 맞춤법·띄어쓰기 검사 대상에서 뺀다.
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")


def _bracket_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _BRACKET_TAG_RE.finditer(text)]


def _inside_any_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)

# NNP(고유명사)는 여기서 제외한다. 사람 이름 같은 고유명사는 표준국어대사전에
# 등재돼 있지 않은 게 정상이라, 포함시키면 "지민", "민준" 같은 멀쩡한 이름을
# 전부 "사전에 없는 단어"로 오탐하게 된다 (부산대 맞춤법 검사기가 사람 이름을
# 이상하게 바꾼다는 지적과 같은 종류의 문제).
_SPELLING_CHECK_TAGS = {"NNG", "VV", "VA"}
_LOANWORD_TAGS = {"NNG", "NNP"}
_CONFUSABLE_LOOKUP = {word: pair for pair in CONFUSABLE_PAIRS for word in pair}

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


def _mechanical_respace(text: str) -> str:
    """조사·어미·접미사 결합 지점의 띄어쓰기만 정리한다 (한글 맞춤법
    제41항: 조사는 앞말에 붙여 씀 + 어미/접미사는 애초에 앞 형태소와 분리해
    쓸 수 없음). 이 지점의 정답은 문맥과 무관하게 항상 하나뿐이므로 안전하게
    자동 적용할 수 있다.

    내용어(명사·동사·형용사·관형사 등)끼리 바로 이어지는 지점은 건드리지
    않고 원문 간격을 그대로 보존한다 — 이건 합성어로 붙일지 별개 단어로
    남길지가 의미에 따라 갈리는 애매한 영역이라(예: '한번'/'한 번'),
    사전 근거 없이 여기서 임의로 판단하면 안 되기 때문이다.

    토큰 표면형을 이어붙여 문자열을 재구성하지 않는다 — '해'(하+어)처럼
    두 형태소가 같은 음절 하나를 공유해 start 위치가 겹치는 경우(제47항
    보조용언 관련 로직에서도 이미 확인된 kiwi의 특성), 각 토큰을 독립적으로
    다시 이어붙이면 그 음절이 중복 출력된다. 대신 토큰 사이의 "간격"만
    원문에서 찾아 필요할 때만 교체하는 방식으로 이 문제를 피한다.
    """
    tokens = _kiwi.tokenize(text)
    edits = []  # (gap_start, gap_end, desired_gap)
    for t1, t2 in zip(tokens, tokens[1:]):
        gap_start = t1.start + t1.len
        gap_end = t2.start
        if gap_end < gap_start:
            continue  # 겹치는 형태소(예: '해'=하+어) - 실제 간격이 없어 건드릴 수 없음
        if "\n" in text[gap_start:gap_end]:
            continue  # 자막 등에서 의도적으로 넣은 줄바꿈 - 문법적 판단과 무관하게 원래 줄 구성을 보존한다
        if t2.form == "요" and t2.len == 1 and gap_start == gap_end:
            continue  # 존대 보조사 "요"(이거요, 빨리요 등)를 kiwi가 가끔 관형사(MM) 등으로
            # 잘못 태깅하는데, 원문에서 이미 붙어 있었다면 태그가 무엇이든 그대로 둔다 —
            # 진짜 관형사 "요"(요 녀석)라면 애초에 앞말과 띄어 쓰여 있었을 것이기 때문이다.
        if t2.tag in _ATTACH_TAGS:
            desired_gap = ""  # 조사/어미/접미사/서술격조사는 무조건 붙임
        elif (
            t1.tag in _MANDATORY_BOUNDARY_TAGS
            and not t2.tag.startswith(_PUNCT_TAG_PREFIX)
            and t2.tag not in _AMBIGUOUS_FOLLOW_TAGS
        ):
            desired_gap = " "  # 어절이 완결된 지점 -> 새 어절은 항상 띄어씀
        else:
            continue  # 애매한 지점(내용어·합성어 후보·보조용언·의존명사 등): 원문 간격 유지
        if text[gap_start:gap_end] != desired_gap:
            edits.append((gap_start, gap_end, desired_gap))

    corrected = text
    for gap_start, gap_end, desired_gap in sorted(edits, key=lambda e: e[0], reverse=True):
        corrected = corrected[:gap_start] + desired_gap + corrected[gap_end:]
    return corrected


def correct_particle_spacing(text: str) -> tuple[str, list[str]]:
    """조사·어미·접미사 결합 지점의 띄어쓰기 오류를 자동으로 정리한다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    corrected = _mechanical_respace(text)
    applied = [f"{text} -> {corrected}"] if corrected != text else []
    return corrected, applied


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
    candidates = [t for t in _kiwi.tokenize(text) if t.tag in _LOANWORD_TAGS]
    replacements = []  # (start, len, original, fix, needs_review, context, is_proper_noun)
    for t in candidates:
        # 이미 표준국어대사전에 정식 등재된 단어는 애초에 외래어 오표기 후보가
        # 아니므로 건드리지 않는다. 그렇지 않으면 "집"처럼 흔한 고유어가
        # kornorms의 전혀 무관한 외래어 항목과 우연히 겹쳐 "지브" 같은 엉뚱한
        # 말로 둔갑하는 사고가 생긴다 (실제로 발견된 버그).
        if word_exists(t.form):
            continue
        fix, needs_review, context = loanword_fix(t.form)
        if fix:
            replacements.append((t.start, t.len, t.form, fix, needs_review, context, t.tag == "NNP"))

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


_COMPOUND_LEAD_TAGS = {"NNG", "NNP", "MM"}  # 명사/고유명사/관형사(예: '그때'의 '그')


def _compound_candidate_spans(text: str) -> list[tuple[int, int, int]]:
    """사전상 합성어일 가능성이 있는 인접 구간 후보를 찾는다 (아직 사전
    확인 전 — 실제 합성어인지는 compound_status()로 따로 검증해야 한다).

    두 가지 패턴을 본다:
    1. (명사/고유명사/관형사) + (명사/고유명사) — 예: '노천'+'카페', '그'+'때'
    2. 용언 어간+관형사형 어미 + 명사 — 예: '쓴'(쓰-+-ᆫ) + '맛' = '쓴맛'

    반환값: (start, boundary, end) 리스트. boundary는 두 조각이 나뉘는
    지점(공백을 넣거나 뺄 위치)이다. 두 토큰/세 토큰 사이의 간격이 빈
    문자열이거나 공백 하나가 아니면(예: 조사가 끼어 있으면) 후보에서
    제외한다 — 그렇지 않으면 '회전축에 목이'처럼 조사를 건너뛰고 엉뚱한
    두 단어가 합쳐지는 사고가 생긴다.
    """
    tokens = _kiwi.tokenize(text)
    spans = []

    def gap_ok(end_pos: int, start_pos: int) -> bool:
        return text[end_pos:start_pos] in ("", " ")

    for t1, t2 in zip(tokens, tokens[1:]):
        if t1.tag not in _COMPOUND_LEAD_TAGS or t2.tag not in ("NNG", "NNP"):
            continue
        boundary = t1.start + t1.len
        if not gap_ok(boundary, t2.start):
            continue
        spans.append((t1.start, boundary, t2.start + t2.len))

    for t1, t2, t3 in zip(tokens, tokens[1:], tokens[2:]):
        if t1.tag not in ("VV", "VA") or t2.tag != "ETM" or t3.tag not in ("NNG", "NNP"):
            continue
        boundary = t2.start + t2.len
        if not gap_ok(boundary, t3.start):
            continue
        spans.append((t1.start, boundary, t3.start + t3.len))

    return spans


def correct_compound_spacing(text: str) -> tuple[str, list[str]]:
    """사전에 하나의 합성어(품사 있음, 하이픈 표기)로 등재된 인접 구간이
    띄어 쓰여 있으면 붙여 쓰도록 자동 교정한다 (예: '노천 카페' -> '노천카페',
    '쓴 맛' -> '쓴맛', '그 때' -> '그때').

    사전이 "이 조합은 무조건 붙여 쓰는 하나의 단어"라고 직접 확인해 준
    경우만 반영한다. 명사구(품사 없음, 캐럿 표기)는 띄어쓰기·붙여쓰기 둘 다
    허용되므로 건드리지 않는다. kiwi.space()는 이런 합성어를 놓치는 경우가
    있어 사전 조회로 보완한다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    fixes = []  # (start, end, replacement, description)
    for start, boundary, end in _compound_candidate_spans(text):
        original = text[start:end]
        combined = text[start:boundary] + text[boundary:end].lstrip(" ")
        if original == combined:
            continue  # 이미 붙어 있음
        if compound_status(combined) == "합성어":
            fixes.append((start, end, combined, f"{original} -> {combined}"))

    corrected = text
    applied = []
    for start, end, replacement, desc in sorted(fixes, key=lambda f: f[0], reverse=True):
        corrected = corrected[:start] + replacement + corrected[end:]
        applied.append(desc)
    return corrected, list(reversed(applied))


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
            corrected = corrected[:idx] + right + corrected[idx + len(wrong) :]
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


def correct_discriminatory_terms(text: str) -> tuple[str, list[str]]:
    """차별적·비하적 표현은 관례냐 아니냐를 따질 문제가 아니라 항상 바꿔야
    하므로 자동으로 교정한다 (예: '간질' -> '뇌전증').

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    return _apply_replacements(text, DISCRIMINATORY_TERMS)


_AUX_EC_FORMS = {"아", "어", "여"}
_AUX_NNB_FORMS = {"뻔", "만", "법", "듯", "성", "직", "척", "체", "양"}
# "-아/어지다"(피동·사동)와 "-아/어하다"는 제47항의 "붙임 허용"(원칙은 띄어쓰기,
# 붙임은 허용되는 예외) 대상이 아니라 별도 규정으로 "항상 붙임"이 원칙인
# 완전히 다른 규칙이다. 형태만 보면 패턴 1(본용언-아/어+보조용언)과 똑같이
# 생겨서(예: "전해지다"의 "지"도 kiwi가 VX로 태깅) 자칫 같은 패턴으로 오인해
# "전해졌다"를 "전해 졌다"로 잘못 갈라놓을 위험이 있어, lemma로 구분해 제외한다.
_ALWAYS_ATTACHED_AUX_LEMMAS = {"지다", "하다"}


def _force_span(suggested: str, original_span: str, other_span: str) -> str:
    """suggested 안에서 other_span(kiwi가 밀어붙이려는 형태)을 original_span
    (실제로 채택된, 정답으로 확정된 형태)으로 되돌린다."""
    if other_span != original_span:
        return suggested.replace(other_span, original_span)
    return suggested


def _aux_verb_pattern_spans(s: str) -> list[str]:
    """s를 토큰화해 보조 용언 붙임 허용 두 패턴(본용언-아/어+보조용언,
    관형사형+의존명사+하다/싶다)에 해당하는 구간의 실제 표면 텍스트를
    등장 순서대로 뽑아 돌려준다."""
    tokens = _kiwi.tokenize(s)
    spans = []
    for i in range(1, len(tokens) - 1):
        prev, cur, nxt = tokens[i - 1], tokens[i], tokens[i + 1]

        # 패턴 1: 본용언(VV/VA) + -아/어(EC) + 보조용언(VX)
        if (
            prev.tag in ("VV", "VA")
            and cur.tag == "EC"
            and nxt.tag == "VX"
            and cur.form in _AUX_EC_FORMS
            and nxt.lemma not in _ALWAYS_ATTACHED_AUX_LEMMAS
        ):
            stem_len = (cur.start + cur.len) - prev.start
            if stem_len >= 3 and compound_status(prev.lemma) == "합성어":
                continue  # 항상 띄움 예외 -> 붙임 허용 대상이 아님
            spans.append(s[prev.start : nxt.start + nxt.len])
            continue

        # 패턴 2: 관형사형(ETM, prev에 결합) + 의존명사(만/듯/척/체/법/양/성/직
        # 등, NNB) + 하다/싶다(XSA, XSV 또는 VX)
        if cur.tag == "NNB" and cur.form in _AUX_NNB_FORMS and nxt.tag in ("XSA", "XSV", "VX"):
            spans.append(s[prev.start : nxt.start + nxt.len])

    return spans


def _normalize_aux_verb_spacing(text: str, suggested: str) -> str:
    """한글 맞춤법 제47항의 보조 용언 붙임 허용 구간에서, kiwi.space()가 이미
    확정된 형태(correct_aux_verb_spacing()이 원칙에 맞춰 띄어 쓴 형태)와
    다른 형태를 제안해 불필요하게 "확인 필요" 플래그가 뜨는 것을 막는다.

    kiwi는 이 구간에서 항상 같은 방식으로 띄어 쓰지 않는다(예: "할만하다"에
    대해 "할 만하다"를 제안하기도 한다 — 관형사형+의존명사 사이는 띄우고
    의존명사+하다 사이는 붙이는, 우리가 채택한 형태와는 또 다른 조합).
    그래서 "붙인 형태/뗀 형태" 둘 중 하나로 단정하고 문자열을 맞바꾸는 대신,
    text와 suggested 양쪽에서 이 패턴에 해당하는 구간을 각각 독립적으로 찾아
    같은 등장 순서끼리 짝지어 그대로 맞바꾼다 — kiwi가 어떤 조합을 제안하든
    안전하게 대응하기 위함이다.
    """
    text_spans = _aux_verb_pattern_spans(text)
    suggested_spans = _aux_verb_pattern_spans(suggested)
    for definitive_span, kiwi_span in zip(text_spans, suggested_spans):
        suggested = _force_span(suggested, definitive_span, kiwi_span)
    return suggested


def correct_aux_verb_spacing(text: str) -> tuple[str, list[str]]:
    """한글 맞춤법 제47항: 보조 용언은 "띄어 씀을 원칙으로 하되, 붙여 씀도
    허용"한다 — 원칙은 띄어쓰기, 붙여쓰기는 허용되는 예외일 뿐이다. 이
    도구는 그 원칙 쪽을 기본값으로 삼아, 붙여 쓴 형태를 띄어 쓴 형태로
    자동 통일한다. 사용자가 붙여쓰기를 선호한다는 별도 지시가 없는 한
    항상 이 기본값(원칙)을 적용한다.

    _normalize_aux_verb_spacing()과 대상 패턴은 같지만 역할이 다르다 — 그쪽은
    이미 붙여 쓴 형태를 "허용되는 정답"으로 보고 kiwi 제안을 원문에 맞춰
    되돌리는(플래그 방지용) 함수였고, 이 함수는 원칙(띄어쓰기) 형태로
    실제 텍스트 자체를 자동 교정한다.

    단, 본용언이 3음절 이상의 사전 등재 합성어인 경우(예: 덤벼들어보아라)는
    항상 띄어 써야 하는 별개의 예외라 이미 붙어 있을 수 없으므로(있다면 그건
    이 함수의 대상이 아닌 다른 오류) 건드리지 않는다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    tokens = _kiwi.tokenize(text)
    edits = set()  # {(gap_start, gap_end)}

    for i in range(1, len(tokens) - 1):
        prev, cur, nxt = tokens[i - 1], tokens[i], tokens[i + 1]

        # 패턴 1: 본용언(VV/VA) + -아/어(EC) + 보조용언(VX)
        if (
            prev.tag in ("VV", "VA")
            and cur.tag == "EC"
            and nxt.tag == "VX"
            and cur.form in _AUX_EC_FORMS
            and nxt.lemma not in _ALWAYS_ATTACHED_AUX_LEMMAS
        ):
            stem_len = (cur.start + cur.len) - prev.start
            if stem_len >= 3 and compound_status(prev.lemma) == "합성어":
                continue  # 항상 띄움 예외 -> 이미 붙어 있을 수 없음
            # 본용언-어/아 부분은 실제 표면 텍스트(축약형 그대로, 예: "여쭤")를
            # 쓰고 보조용언은 사전 기본형을 붙여 "여쭤보다" 같은 후보를 만든다.
            # 이게 사전에 이미 붙여 쓴 한 단어로 등재되어 있다면(예: 여쭤보다,
            # 알아보다, 찾아보다), "원칙은 띄어쓰기"보다 사전 등재가 우선이므로
            # 억지로 띄우지 않는다 — correct_compound_spacing()이 명사 합성어를
            # 사전으로 확인하는 것과 같은 원칙이다.
            candidate = text[prev.start : cur.start + cur.len] + nxt.lemma
            if word_exists(candidate):
                continue
            gap_start, gap_end = cur.start + cur.len, nxt.start
            if text[gap_start:gap_end] == "":
                edits.add((gap_start, gap_end))

        # 패턴 2: 관형사형(ETM) + 의존명사(만/듯/척/체/법/양/성/직 등, NNB) +
        # 하다/싶다(XSA, XSV 또는 VX). 의존명사 앞뒤 두 간격 모두 원칙은
        # 띄어쓰기이므로(제42항 의존명사 + 제47항 보조용언), 둘 다 정리한다.
        # 한쪽만 띄우면("아는척 한다") kiwi가 남은 절반을 다른 품사로
        # 재분석해(하다=XSV -> VV) 오히려 새로운 오탐 플래그를 만들어낸다.
        if cur.tag == "NNB" and cur.form in _AUX_NNB_FORMS and nxt.tag in ("XSA", "XSV", "VX"):
            lead_start, lead_end = prev.start + prev.len, cur.start
            if text[lead_start:lead_end] == "":
                edits.add((lead_start, lead_end))
            gap_start, gap_end = cur.start + cur.len, nxt.start
            if text[gap_start:gap_end] == "":
                edits.add((gap_start, gap_end))

    corrected = text
    for gap_start, gap_end in sorted(edits, key=lambda e: e[0], reverse=True):
        corrected = corrected[:gap_start] + " " + corrected[gap_end:]
    applied = [f"{text} -> {corrected}"] if corrected != text else []
    return corrected, applied


def check_spelling(index: int, text: str) -> FlagItem | None:
    """사전에 없는 단어는 신조어일 수도, 외국어 음차(이름·지명 등)일 수도
    있어 이 함수만으로는 구분할 수 없다 — 그래서 고치자고 제안하지 않고,
    번역가 교육자료가 권장하는 실제 검증 방법(국립국어원 용례, 발음기호
    사전, 한글라이즈)으로 직접 확인하라고 안내만 한다."""
    unknown = [w for w in _content_lemmas(text) if not word_exists(w)]
    if unknown:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"사전에 없는 단어: {', '.join(unknown)} — 외국어 음차·고유명사일 수 있음. "
                "국립국어원 용례, 발음기호(Longman/Collins 등), 한글라이즈(hangulize.org)로 "
                "직접 확인 필요. 반복 등장하는 이름·요리명이면 위쪽의 고유명사/요리명 목록에 "
                "추가하면 이후 잘못 쪼개지지 않습니다."
            ),
        )
    return None


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


def check_confusable_words(index: int, text: str) -> FlagItem | None:
    """한글 맞춤법 제57항의 동음이의어 혼동 쌍(가름/갈음, 반드시/반듯이 등)이
    등장하면 항상 확인 플래그한다. 의미가 완전히 다른 별개의 단어라 어느 쪽이
    맞는지는 문맥을 봐야 알 수 있으므로, check_spelling과 달리 절대 자동
    교정하지 않는다."""
    matched = []
    for t in _kiwi.tokenize(text):
        for candidate in (t.form, t.lemma):
            pair = _CONFUSABLE_LOOKUP.get(candidate)
            if pair and pair not in matched:
                matched.append(pair)
    if not matched:
        return None
    pairs_desc = ", ".join("/".join(pair) for pair in matched)
    reason = f"자주 헷갈리는 동음이의어 확인 필요: {pairs_desc} (문맥에 맞는 단어인지 확인)"
    note = _usage_note([word for pair in matched for word in pair])
    if note:
        reason += f" | 우리말샘 용례) {note}"
    return FlagItem(line_index=index, original_text=text, reason=reason)


def check_purified_terms(index: int, text: str) -> FlagItem | None:
    """일반 순화어(예: 반팔->반소매)가 등장하면 확인 플래그한다. 차별적
    표현과 달리 관례적 표현이 여전히 널리 쓰이는 경우가 있어(예: 유모차는
    공식 순화어 유아차보다 압도적으로 많이 쓰임) 자동으로 바꾸지 않는다."""
    matched = [word for word in PURIFIED_TERMS if word in text]
    if not matched:
        return None
    suggestions = ", ".join(f"{word}->{PURIFIED_TERMS[word]}" for word in matched)
    reason = f"순화어 확인 필요: {suggestions} (관례적 표현이 더 적절할 수도 있음)"
    note = _usage_note(matched + [PURIFIED_TERMS[word] for word in matched])
    if note:
        reason += f" | 우리말샘 용례) {note}"
    return FlagItem(line_index=index, original_text=text, reason=reason)


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


def _protect_unfounded_respacing(text: str, suggested: str) -> str:
    """kiwi.space()가 사전에도 없고 어문 규정에도 근거가 없는 채로 공백을
    새로 끼워 넣자고 제안하는 경우를 되돌린다. 네 가지를 막는다:

    0. kiwi 자신의 tokenize()가 이미 하나의 형태소로 본 토큰 내부에 공백을
       넣는 것 — tokenize()와 space()가 서로 다른 모델이라 어긋난 경우고,
       kiwi 스스로도 확신이 없다는 신호이므로 근거 확인 없이 되돌린다.
    1. 고유명사(NNP) 토큰 경계를 갈라놓는 것 (예: '연실' -> '연 실') —
       kiwi가 모르는 이름일 뿐, 원래 하나의 토큰으로 붙어 있던 걸 갈라야
       한다는 근거가 없다.
    2. 표준국어대사전/우리말샘에 이미 붙여 쓴 형태로 등재된 경우 (예:
       '한잔하다', '탄두리치킨') — 사전이 kiwi의 통계적 추정보다 권위
       있는 근거다. correct_compound_spacing()의 명사 합성어 전용 처리를
       모든 품사 조합으로 일반화한 버전이다.
    3. '/' 바로 뒤, 또는 '[이름/상황]' 형태의 자막 브래킷 표기 안 — 이건
       실제 문장이 아니라 관례적 메타 표기라 한글 맞춤법이 다루는 대상이
       아니다. "'/' 뒤에 띄어 쓴다"는 규정 자체가 존재하지 않는다.
    """
    brackets = _bracket_spans(text)
    tokens = None
    to_remove = []  # suggested 상에서 지울 (j1, j2) 목록
    for i1, j1, j2 in _inserted_space_ranges(text, suggested):
        if _inside_any_span(i1, brackets) or (i1 > 0 and text[i1 - 1] == "/"):
            to_remove.append((j1, j2))
            continue
        if tokens is None:
            tokens = _kiwi.tokenize(text)
        if _token_containing(tokens, i1) is not None:
            to_remove.append((j1, j2))
            continue
        before, after = _straddling_tokens(tokens, i1)
        if before is None or after is None:
            continue
        if before.tag == "NNP" or after.tag == "NNP":
            to_remove.append((j1, j2))
            continue
        # 용언(동사/형용사) 토큰은 표면형이 어간뿐이라(예: '하다가'의 '하'),
        # 사전 기본형(lemma)으로 합쳐야 '한잔하다' 같은 등재된 복합동사를
        # 알아볼 수 있다. '한잔'+'하'로는 사전에 없지만 '한잔'+'하다'는 있음.
        before_part = before.lemma if before.tag.startswith("V") else before.form
        after_part = after.lemma if after.tag.startswith("V") else after.form
        joined = before_part + after_part
        if text[before.start : after.start + after.len] == before.form + after.form and word_exists(joined):
            to_remove.append((j1, j2))

    for j1, j2 in sorted(to_remove, key=lambda r: r[0], reverse=True):
        suggested = suggested[:j1] + suggested[j2:]
    return suggested


def check_spacing(index: int, text: str) -> FlagItem | None:
    """띄어쓰기 제안은 신뢰도를 알 수 없으므로 절대 자동 적용하지 않고
    원문과 다르면 무조건 사람 확인용으로 플래그한다 (예: '한번'/'한 번'처럼
    문맥에 따라 정답이 갈리는 경우 잘못 우겨서 고치는 걸 막기 위함)."""
    suggested = _kiwi.space(text)

    # kiwi는 사전에 등재된 합성어를 모르는 경우가 있어(예: '노천카페', '그때',
    # '쓴맛'), 이미 correct_compound_spacing()이 사전 근거로 확정 붙여쓰기한
    # 부분을 다시 갈라놓자고 제안할 수 있다. 확정된 합성어는 사전이 kiwi보다
    # 권위 있는 근거이므로, kiwi의 제안에서 그 부분만 원상복구해 오탐을 막는다.
    for start, boundary, end in _compound_candidate_spans(text):
        tail = text[boundary:end].lstrip(" ")
        combined = text[start:boundary] + tail
        if text[start:end] != combined:
            continue  # 이미 떨어져 있으면 합성어 자동 교정 대상이 아니었음
        if compound_status(combined) == "합성어":
            spaced = text[start:boundary] + " " + tail
            suggested = _force_span(suggested, combined, spaced)

    suggested = _normalize_aux_verb_spacing(text, suggested)
    suggested = _protect_unfounded_respacing(text, suggested)

    if suggested != text:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason="띄어쓰기 확인 필요 (문맥에 따라 정답이 다를 수 있음)",
            suggested_fix=suggested,
        )
    return None


def correct_entries(
    entries: list[SubtitleEntry],
) -> tuple[list[SubtitleEntry], list[FlagItem], list[str]]:
    """entries를 처리한다.

    반환값: (자동 교정 반영된 entries, 플래그 목록, 확인 불필요 자동 교정 로그)
    나머지 검사(맞춤법/띄어쓰기)는 자동 교정이 끝난 텍스트를 기준으로 수행한다.

    본격적인 처리 전에, 문서 전체에서 반복 등장하는 미등록 단어(주로
    고유명사)를 자동으로 감지해 kiwi에 등록한다(register_custom_words
    참고) — 사용자가 이름 목록을 따로 적지 않아도 이 자동 감지만으로
    대부분의 고유명사 오분석이 해결된다.
    """
    corrected_entries = []
    flags = []
    applied_log = []

    auto_detected = detect_recurring_unknown_words(entries)
    if auto_detected:
        register_custom_words(auto_detected, tag="NNP")
        applied_log.append(f"[자동 감지] 반복 등장하는 고유명사로 인식해 등록: {', '.join(auto_detected)}")

    for e in entries:
        corrected_text, applied_fixes, review_fixes, proper_noun_fixes = correct_loanwords(e.text)
        corrected_text, particle_fixes = correct_particle_spacing(corrected_text)
        corrected_text, compound_fixes = correct_compound_spacing(corrected_text)
        corrected_text, aux_verb_fixes = correct_aux_verb_spacing(corrected_text)
        corrected_text, always_wrong_fixes = correct_always_wrong(corrected_text)
        corrected_text, discriminatory_fixes = correct_discriminatory_terms(corrected_text)
        applied_log.extend(
            f"[{e.index}] {fix}"
            for fix in applied_fixes
            + particle_fixes
            + compound_fixes
            + aux_verb_fixes
            + always_wrong_fixes
            + discriminatory_fixes
        )

        corrected_entries.append(
            SubtitleEntry(index=e.index, start=e.start, end=e.end, text=corrected_text)
        )

        for fix, context in review_fixes:
            flags.append(
                FlagItem(
                    line_index=e.index,
                    original_text=corrected_text,
                    reason=(
                        f"인명/지명 표기 자동 적용됨 ({fix}, 참고: {context}) — "
                        "원지음 표기 원칙에 따른 추정치이므로 실제 발음 확인 필요"
                    ),
                )
            )

        for fix, context in proper_noun_fixes:
            original_token, _, replacement_token = fix.partition(" -> ")
            flags.append(
                FlagItem(
                    line_index=e.index,
                    original_text=corrected_text,
                    reason=(
                        f"고유명사 외래어 표기 확인 필요 ({fix}, 참고: {context or '국립국어원 확정 표기'}) — "
                        "인명·지명은 표기 규칙을 따라야 하지만, 작품 제목처럼 고유하게 "
                        "고정된 표기일 수 있어 자동 반영하지 않음. 실제 대상이 규칙을 "
                        "따라야 하는 경우에만 반영할 것"
                    ),
                    suggested_fix=corrected_text.replace(original_token, replacement_token, 1),
                )
            )

        flags.extend(
            f
            for f in (
                check_spelling(e.index, corrected_text),
                check_confusable_words(e.index, corrected_text),
                check_purified_terms(e.index, corrected_text),
                check_spacing(e.index, corrected_text),
            )
            if f
        )

    return corrected_entries, flags, applied_log


def apply_report_fixes(
    report_rows: list[dict], entries: list[SubtitleEntry]
) -> tuple[list[SubtitleEntry], int]:
    """리포트에서 사용자가 직접 채운 수정값(suggested_fix)을 entries에 반영한다.

    한 줄에 플래그가 여러 개 걸려 여러 행이 있을 수 있는데, 그중 사용자가
    실제로 값을 채운 행만 순서대로 적용한다 (같은 줄에 값이 여러 번 채워져
    있으면 리포트 파일에서 나중에 나오는 행이 최종 반영된다).

    반환값: (반영된 entries, 실제로 반영된 건수)
    """
    by_index = {e.index: e for e in entries}
    applied_count = 0

    for row in report_rows:
        fix = (row.get("suggested_fix") or "").strip()
        if not fix:
            continue
        try:
            line_index = int(row["line_index"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = by_index.get(line_index)
        if entry is None:
            continue
        entry.text = fix
        applied_count += 1

    return entries, applied_count
