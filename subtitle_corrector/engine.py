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
   오탐지하게 된다.
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

from .common_errors import ALWAYS_WRONG, DISCRIMINATORY_TERMS
from .dictionary import (
    compound_status,
    convert_dialect,
    detect_dialect_ratio,
    detect_speaker_dialect,
    former_term_lookup,
    get_purified_terms,
    loanword_fix,
    registered_ending,
    search_dialect,
    search_kornorms,
    standard_term_replacement,
    usage_examples,
    word_exists,
)
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

    # "과"(조사 "~와/과" vs 한자어 접두사 "과-[過]": 과증식, 과체중 등)처럼
    # 조사와 형태가 같은 접두사가 있다 — 뒤 단어와 합쳐 사전에 등재된 단어가
    # 되고 그 사이 간격이 이미 붙어 있으면, 조사가 아니라 다음 단어에 붙는
    # 접두사로 본다. 이 토큰은 (a) 앞말에 강제로 붙이지도 않고(조사가
    # 아니므로), (b) 자신이 조사로서 어절을 완결짓지도 않는다(뒤에 오는
    # 단어의 일부이므로) — 애매하면 그대로 둔다는 원칙에 따라 이 지점
    # 전체를 건드리지 않는다.
    ambiguous_prefix_indices = set()
    for i, t in enumerate(tokens[:-2]):
        nxt, nxt2 = tokens[i + 1], tokens[i + 2]
        if (
            nxt.tag in ("JC", "JX", "JKS", "JKO", "JKG")
            and nxt2.start == nxt.start + nxt.len
            and word_exists(nxt.form + nxt2.lemma)
        ):
            ambiguous_prefix_indices.add(i + 1)

    edits = []  # (gap_start, gap_end, desired_gap)
    for i in range(len(tokens) - 1):
        t1, t2 = tokens[i], tokens[i + 1]
        gap_start = t1.start + t1.len
        gap_end = t2.start
        if gap_end < gap_start:
            continue  # 겹치는 형태소(예: '해'=하+어) - 실제 간격이 없어 건드릴 수 없음
        if t2.len == 0:
            continue  # kiwi가 삽입한 길이 0 가상 토큰(예: '없다길래'→없+다+하(길이0)+길래)
            # — 실제 텍스트에 없는 형태소라 태그 판정에 근거가 없음. 이 토큰의
            # 태그(예: VV)를 근거로 앞 형태소(EC)와의 경계에 공백을 삽입하면
            # 원문을 왜곡한다(예: '없다길래'→'없다 길래' 오류).
        if "\n" in text[gap_start:gap_end]:
            continue  # 자막 등에서 의도적으로 넣은 줄바꿈 - 문법적 판단과 무관하게 원래 줄 구성을 보존한다
        if t2.form == "요" and t2.len == 1 and gap_start == gap_end:
            continue  # 존대 보조사 "요"(이거요, 빨리요 등)를 kiwi가 가끔 관형사(MM) 등으로
            # 잘못 태깅하는데, 원문에서 이미 붙어 있었다면 태그가 무엇이든 그대로 둔다 —
            # 진짜 관형사 "요"(요 녀석)라면 애초에 앞말과 띄어 쓰여 있었을 것이기 때문이다.
        if (i + 1) in ambiguous_prefix_indices or i in ambiguous_prefix_indices:
            continue
        if t2.tag in _ATTACH_TAGS:
            desired_gap = ""  # 조사/어미/접미사/서술격조사는 무조건 붙임
            # "안 되다"(금지)와 "안되다"(상황이 안 됨)는 같은 형태인데 띄어쓰기가
            # 완전히 반대다. kiwi가 "되"를 XSV(파생접미사)로 태깅하면 _ATTACH_TAGS
            # 때문에 공백을 제거하는데, 이 경우 "안 되다"의 띄어쓰기를 파괴할 수 있다.
            # "안되다"는 표준국어대사전 별도 표제어이므로, 원문의 띄어쓰기를 보존한다.
            if t1.form == "안" and t1.tag == "MAG" and gap_start != gap_end:
                continue
        elif (
            t1.tag in _MANDATORY_BOUNDARY_TAGS
            and not t2.tag.startswith(_PUNCT_TAG_PREFIX)
            and t2.tag not in _AMBIGUOUS_FOLLOW_TAGS
        ):
            # EC(연결어미) 뒤에 오는 내용어(VV/VA 등) 경계는 원칙적으로 띄어쓰기가
            # 맞지만, 축약된 구어체 표현(예: "있냐하면요"="있느냐 하면요")에서는
            # EC와 VV가 의도적으로 붙어 있다. 원문에서 이미 붙어 있으면(간격 0),
            # 이 경계가 축약인지 진짜 어절 경계인지 문맥 없이는 구분할 수 없으므로
            # 원문 간격을 보존한다 — "애매하면 자동 수정하지 않는다" 원칙.
            # 단, 조사(J*)나 서술격조사(VCP) 등에는 이 예외를 적용하지 않는다
            # (예: "오늘은날씨"→"오늘은 날씨"는 반드시 교정해야 함).
            if t1.tag == "EC" and gap_start == gap_end:
                continue
            desired_gap = " "  # 어절이 완결된 지점 -> 새 어절은 항상 띄어씀
        elif (
            t1.tag == "MAJ"
            and gap_start == gap_end
            and t2.tag not in _ATTACH_TAGS
        ):
            # 연결부사("그래서", "그런데", "하지만" 등)는 항상 새 어절의 시작이므로
            # 뒤에 공백이 있어야 한다. 조사(J*) 뒤에는 붙는 경우("그런데도")가 있어
            # _ATTACH_TAGS인 경우는 건드리지 않는다(보조사 "도"는 앞말에 붙임).
            desired_gap = " "
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

# 관형사(그/이/저/두/세 등)+명사 조합은 사전이 "합성어"로 확인해 줘도
# 원문이 의도한 뜻과 무관한 우연의 동형이의어일 위험이 크다 — 관형사는
# 거의 모든 명사 앞에 올 수 있어("두 강", "그 다리" 등) 이런 충돌이
# 명사+명사보다 훨씬 흔하다(실제로 "두강"[杜康=술의 별칭], "그다리"["다리쇠"의
# 방언]과 충돌하는 사고가 발견됨, §20). 그래서 관형사가 이끄는 조합은 이미
# 검증된 소수의 고정 표현만 자동으로 붙이고, 그 외는 사전이 "합성어"라고
# 확인해줘도 자동으로 붙이지 않는다(플래그만 — 사전 등재만으로는 뜻이
# 원문 의도와 같은지 확인할 수 없기 때문). 새 사례를 검증하면 이 목록에
# 추가한다.
_MM_NOUN_COMPOUND_ALLOWLIST = {"그때", "그날", "이날", "그곳", "이곳", "저곳"}

# 시간 단위 의존명사(년/월/일/시간/분/초/주/개월 등, 숫자 뒤에 붙는 것들).
# "7년 전 일이에요"처럼 숫자+시간단위 뒤에 오는 "전"은 "~하기 전(以前)"의
# "전"이 아니라 "며칠 전"처럼 "지금부터 그만큼 전"이라는 뜻으로, 뒤에 오는
# 명사와 절대 하나의 단어가 될 수 없다("전일"[全日/前日]이 사전에 등재된
# 별개의 단어라 뒤 명사와 우연히 합쳐지는 사고가 남, §21). 반대로 이런
# 시간 표현이 앞에 없는 "전일"은 kiwi 자신도 이미 하나의 토큰으로 본다 —
# 즉 이 경우만 명사+명사 합성 후보에서 제외하면 된다(사전 등재 여부와
# 무관하게, 문맥상 애초에 합성 후보가 될 수 없는 경우이므로).
_DURATION_UNIT_NNB = {"년", "월", "일", "시간", "분", "초", "주", "개월", "주일", "달"}


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

    for i in range(len(tokens) - 1):
        t1, t2 = tokens[i], tokens[i + 1]
        if t1.tag not in _COMPOUND_LEAD_TAGS or t2.tag not in ("NNG", "NNP"):
            continue
        if t1.tag == "MM" and t1.lemma + t2.lemma not in _MM_NOUN_COMPOUND_ALLOWLIST:
            continue
        if t1.lemma == "전" and i >= 1 and tokens[i - 1].tag == "NNB" and tokens[i - 1].lemma in _DURATION_UNIT_NNB:
            continue  # "7년 전 일"의 "전" -> "~전(前)에"의 뜻, 뒤 명사와 합성 후보가 될 수 없음
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


# 받침 유무에 따라 형태가 바뀌는 조사 짝: (받침 있을 때 형태, 받침 없을
# 때 형태). "으로/로"는 ㄹ받침 예외("물로"이지 "물으로"가 아님)가 있어
# 일반화하기 까다로워 제외한다 — 확신 없는 부분은 건드리지 않는다는 원칙.
_PARTICLE_ALLOMORPH_GROUPS = [("이", "가"), ("은", "는"), ("을", "를"), ("과", "와")]
_PARTICLE_TO_GROUP = {form: group for group in _PARTICLE_ALLOMORPH_GROUPS for form in group}


def _has_batchim(syllable: str) -> bool:
    """한글 음절 하나에 받침이 있는지 확인한다(유니코드 완성형 한글은
    코드포인트 = 0xAC00 + (초성*21+중성)*28+종성 공식을 따르므로, 그 값을
    28로 나눈 나머지가 0이면 받침이 없다는 뜻)."""
    if not syllable:
        return False
    code = ord(syllable[-1])
    if not (0xAC00 <= code <= 0xD7A3):
        return False
    return (code - 0xAC00) % 28 != 0


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
    for t in _kiwi.tokenize(text):
        if t.tag not in ("NNG", "NNP"):
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


def correct_former_terms(index: int, text: str) -> tuple[str, list[str], list[FlagItem]]:
    """표준국어대사전이 "'X'의 전 용어"로 표시한 옛 용어(지양 대상)를 처리한다.

    correct_nonstandard_terms()가 우리말샘의 "규범 표기는/표준 용어는" 안내를
    보는 것과 원천만 다를 뿐 같은 성격의 실시간 동적 규칙이다 — 정적 목록이
    아니라 매번 표준국어대사전을 조회하므로 국립국어원이 표준 용어를 바꿔도
    코드 수정이 필요 없다.

    안전 규칙(동형이의어 오교정 방지):
    - 모든 뜻이 "전 용어" 뜻인 단어(예: "정신분열증" → 전부 "조현병"의 전 용어)는
      문맥과 무관하게 하나의 정답만 있으므로 조용히 자동 교정한다.
    - "전 용어" 뜻 외에 다른 뜻도 있는 동형이의어(예: "간질" — 옛 용어(뇌전증)
      외에 곤충·조직·'간질거리다' 어근 뜻도 있음)는 자동 교정하지 않고 플래그만
      남긴다. 텍스트만으로 어느 뜻인지 자동 판별하는 것은 확률적 추정이라 이
      프로젝트가 금지하는 방식이므로(문맥 기반 의미 판별 시도 안 함), 사람이
      문맥으로 판단하도록 다른 뜻들을 사유에 실어 안전하게 넘긴다.

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
                target = result["target"]
                if not result["ambiguous"]:
                    auto_replacements[surface] = target
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

        # 패턴 1: 본용언(VV/VA) + -아/어(EC) + 보조용언(VX). kiwi는 불규칙
        # 활용 어간(잇다의 "잇" 등)을 "VV"가 아니라 "VV-I"처럼 하위분류
        # 접미사를 붙여 태깅하므로, 정확히 일치("==")가 아니라 접두사
        # 일치(startswith)로 확인해야 이런 불규칙 동사를 놓치지 않는다.
        if (
            (prev.tag.startswith("VV") or prev.tag.startswith("VA"))
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

        # 패턴 1: 본용언(VV/VA) + -아/어(EC) + 보조용언(VX). kiwi는 불규칙
        # 활용 어간(잇다의 "잇" 등)을 "VV"가 아니라 "VV-I"처럼 하위분류
        # 접미사를 붙여 태깅하므로, 정확히 일치("==")가 아니라 접두사
        # 일치(startswith)로 확인해야 이런 불규칙 동사를 놓치지 않는다.
        if (
            (prev.tag.startswith("VV") or prev.tag.startswith("VA"))
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
            nxt_citation = nxt.lemma if nxt.lemma.endswith("다") else nxt.lemma + "다"
            candidate = text[prev.start : cur.start + cur.len] + nxt_citation
            if word_exists(candidate):
                continue
            gap_start, gap_end = cur.start + cur.len, nxt.start
            if text[gap_start:gap_end] == "":
                edits.add((gap_start, gap_end))

        # 패턴 2: 관형사형(ETM) + 의존명사(만/듯/척/체/법/양/성/직/뻔 등, NNB) +
        # 하다/싶다(XSA, XSV 또는 VX). 세 가지를 구분해야 한다.
        #
        # (a) "그럴듯하다"처럼 전체가 그 자체로 하나의 독립된 표제어로
        #     등재된 경우("그럴-듯하다", 품사: 형용사 — 생산적인 보조
        #     형용사 "듯-하다"와는 별개의 고유 단어) - 완전히 그대로 둔다.
        # (b) 나머지 일반적인 경우, 관형사형+의존명사 사이(예: "할"+"만")는
        #     제42항에 따라 항상 띄어 쓴다.
        # (c) 의존명사+하다/싶다 사이(예: "만"+"하다")는 표준국어대사전에
        #     "만-하다"(보조 형용사), "척-하다"(보조 동사), "법-하다"(보조
        #     형용사)처럼 그 자체가 하나의 단어로 등재되어 있으면 항상
        #     붙여 쓴다. 예전에는 이 9개 의존명사 전부를 수동으로 한 번
        #     확인한 뒤 "항상 참"이라고 가정하고 하드코딩했는데, 이는
        #     실시간 사전 조회 원칙(§5)에 어긋난다 — "할만하다"처럼 특정
        #     본용언이 붙은 전체 표면형은 사전에 없어도(word_exists가
        #     0을 반환해도), "만하다"만 떼어 조회하면 등재된 걸 확인할
        #     수 있는데도 원래는 이 후자 조회를 하지 않아 놓쳤다. 이제
        #     매번 그 자리에서 바로 이 바른 형태(의존명사+하다/싶다
        #     단독)로 실시간 조회해 확인하고, 아니라면(예: "만싶다"처럼
        #     실제로 없는 조합) 억지로 붙이지 않고 그대로 둔다(사람 확인
        #     영역으로 남김 — 애매하면 자동 수정하지 않는다는 원칙).
        if cur.tag == "NNB" and cur.form in _AUX_NNB_FORMS and nxt.tag in ("XSA", "XSV", "VX"):
            lead_word_start = prev.start
            if i >= 2 and tokens[i - 2].start + tokens[i - 2].len > prev.start:
                lead_word_start = tokens[i - 2].start  # 그렇+ㄹ 같은 받침 공유 보정
            nxt_citation = nxt.lemma if nxt.lemma.endswith("다") else nxt.lemma + "다"
            whole_candidate = text[lead_word_start : cur.start + cur.len] + nxt_citation
            if word_exists(whole_candidate):
                continue  # (a) 전체가 통째로 하나의 표제어 -> 그대로 둔다
            lead_start, lead_end = prev.start + prev.len, cur.start
            if text[lead_start:lead_end] == "":
                edits.add((lead_start, lead_end))  # (b)
            if not word_exists(cur.form + nxt_citation):
                # 의존명사+하다/싶다 단독 조합조차 사전에 없는 예외적
                # 경우 -> 붙여 쓴다고 단정하지 않고 그대로 둔다.
                edits.discard((lead_start, lead_end))
            # (c) 사전에 등재된 경우, 의존명사+하다/싶다 사이는 건드리지
            # 않는다(위에서 (b) 간격만 edits에 추가했고, 트레일링 간격은
            # 애초에 추가한 적이 없다).

    corrected = text
    for gap_start, gap_end in sorted(edits, key=lambda e: e[0], reverse=True):
        corrected = corrected[:gap_start] + " " + corrected[gap_end:]
    applied = [f"{text} -> {corrected}"] if corrected != text else []
    return corrected, applied


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


def check_spelling(index: int, text: str) -> FlagItem | None:
    """사전에 없는 단어는 신조어일 수도, 외국어 음차(이름·지명 등)일 수도
    있어 이 함수만으로는 구분할 수 없다 — 그래서 고치자고 제안하지 않고,
    번역가 교육자료가 권장하는 실제 검증 방법(국립국어원 용례, 발음기호
    사전, 한글라이즈)으로 직접 확인하라고 안내만 한다."""
    unknown = [
        w
        for w in _content_lemmas(text)
        if not word_exists(w) and not _is_productive_demonym_compound(w) and not search_kornorms(w)
    ]
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


# 화자별 사투리 처리 모드.
#   - "protect": (지정된 화자의 기본값) 사투리를 그대로 보호한다. 어떤
#     자동 교정도, 어떤 플래그도 남기지 않는다. 대본 속 사투리는 대부분
#     작가의 의도이므로 기본적으로 건드리지 않는다.
#   - "assist": 텍스트는 그대로 두고, 표준어→사투리 제안 플래그만 남긴다
#     (작가가 사투리 화자를 원하지만 사투리에 익숙하지 않은 경우 도움).
#   - "to_standard": 사투리→표준어 자동 변환 + 확인 플래그(드문 opt-in).
_VALID_DIALECT_MODES = frozenset({"protect", "assist", "to_standard"})

# 이전 모드명과의 하위 호환: 옛 호출부가 넘기는 문자열을 새 모드로 매핑한다.
#   - "flag_only"(사투리를 의심스러운 것으로 플래그하던 옛 기본값) → "protect"
#   - "to_dialect"(표준어→사투리 자동 재작성) → "assist"
_DIALECT_MODE_ALIASES = {
    "flag_only": "protect",
    "to_dialect": "assist",
}


def normalize_dialect_mode(mode: str | None) -> str:
    """모드 문자열을 유효한 새 모드명으로 정규화한다.

    빈 값/미지정은 "protect"(기본값). 하위 호환 별칭(flag_only/to_dialect)은
    각각 protect/assist로 매핑한다. 알 수 없는 값도 안전하게 "protect"로 둔다.
    """
    if not mode:
        return "protect"
    mode = _DIALECT_MODE_ALIASES.get(mode, mode)
    if mode not in _VALID_DIALECT_MODES:
        return "protect"
    return mode


def resolve_dialect_mode(
    speaker: str | None,
    dialect_map: dict[str, str] | None,
    dialect_modes: dict[str, str] | None,
) -> tuple[str | None, str | None]:
    """화자의 사투리 (지역, 모드)를 결정한다.

    반환값:
        - 화자가 dialect_map에 있으면 (지역, 정규화된 모드).
        - 그 외(사투리 미지정 화자)는 (None, None).
    """
    if not dialect_map or not speaker or speaker not in dialect_map:
        return None, None
    region = dialect_map[speaker]
    mode = normalize_dialect_mode((dialect_modes or {}).get(speaker))
    return region, mode


def check_dialect(
    index: int,
    text: str,
    region: str | None,
    mode: str | None,
) -> tuple[str, list[FlagItem]]:
    """resolve_dialect_mode()로 이미 결정된 (region, mode)에 따라 사투리를 처리한다.

    - region이 None(사투리 미지정 화자): 자동 감지 후 플래그만 남긴다(비율 >= 0.15).
      표준어로 간주하지만 어미가 표준이 아니어도 자동교정하지 않는다.
    - mode == "assist": 텍스트는 그대로 두고, 표준어→사투리 제안 플래그만 만든다.
      convert_dialect(to_dialect)가 바꿀 게 없고 search_dialect도 비면 플래그 없음.
    - mode == "to_standard": 사투리→표준어 자동 변환 + 확인 플래그.

    "protect" 모드는 이 함수를 호출하지 않는다(호출부에서 통째로 건너뛴다).

    반환값: (처리된 텍스트, 플래그 목록)
    """
    # 사투리 미지정 화자 — 자동 감지 (항상 플래그만)
    if region is None:
        from .dictionary import DIALECT_MARKERS
        for detected in DIALECT_MARKERS:
            if detect_dialect_ratio(text, detected) >= 0.15:
                return text, [FlagItem(
                    line_index=index,
                    original_text=text,
                    reason=(
                        f"사투리 패턴 감지 ({detected}) — "
                        f"이 화자가 {detected} 사투리를 쓰는 것 같습니다. "
                        "사투리 설정이 필요하면 화자별 사투리를 지정해 주세요."
                    ),
                )]
        return text, []

    if mode == "to_standard":
        converted = convert_dialect(text, region, "to_standard")
        if converted != text:
            return converted, [FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=converted,
                reason=(
                    f"사투리→표준어 자동 변환 ({region}) — "
                    "변환된 텍스트를 확인해 주세요."
                ),
            )]
        return text, []

    if mode == "assist":
        # 텍스트는 절대 바꾸지 않는다. 표준어 표현을 사투리로 바꾸는 제안만 남긴다.
        suggested = convert_dialect(text, region, "to_dialect")
        if suggested != text:
            return text, [FlagItem(
                line_index=index,
                original_text=text,
                suggested_fix=suggested,
                reason=(
                    f"사투리 제안 ({region}) — 이 화자는 {region} 사투리를 쓰도록 "
                    "지정돼 있습니다. 표준어 표현을 사투리로 바꾸는 제안이며, "
                    "자동 반영하지 않으니 검토 후 채택하세요."
                ),
            )]
        # convert가 바꿀 게 없으면 지역어 종합 정보 API로 대응 사투리를 조회한다.
        api_results = []
        try:
            api_results = search_dialect(text.split()[-1] if text.split() else "")
        except Exception:
            pass
        for result in api_results:
            dialect_word = result.get("word", "")
            if dialect_word:
                std_word = result.get("std_word", "")
                std_note = f" (표준어: {std_word})" if std_word else ""
                return text, [FlagItem(
                    line_index=index,
                    original_text=text,
                    reason=(
                        f"사투리 제안 ({region}) — 참고 사투리 표현: "
                        f"{dialect_word}{std_note}. 검토 후 직접 반영하세요."
                    ),
                )]
        # 제안할 사투리가 없으면 플래그를 남기지 않는다.
        return text, []

    # 알 수 없는 모드는 안전하게 보호로 간주한다(플래그 없음).
    return text, []


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


def _removed_space_points(original: str, suggested: str) -> list[tuple[int, int]]:
    """kiwi.space()가 원문에 이미 있던 공백을 지워버린(두 단어를 붙여버린)
    지점들을 찾는다. _inserted_space_ranges()와 반대 방향이다.

    반환값: (원문 상의 공백 위치, suggested 상에서 다시 공백을 끼워 넣어야
    할 위치) 목록."""
    matcher = difflib.SequenceMatcher(a=original, b=suggested, autojunk=False)
    points = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete" and original[i1:i2] == " ":
            points.append((i1, j1))
    return points


def _protect_unfounded_joining(text: str, suggested: str) -> str:
    """kiwi.space()가 사전에도 없고 어문 규정에도 근거가 없는 채로 원문의
    공백을 지워버리는(두 단어를 붙여버리는) 것을 되돌린다.

    "그만하려고 합니다"(-려고 하다: 의도를 나타내는 본동사 구성, 제47항
    보조 용언 붙임 허용 대상이 전혀 아니라 항상 띄어 써야 함)를 kiwi가
    "그만하려고합니다"로 붙여버리는 사고에서 발견함. _protect_unfounded_
    respacing()은 kiwi가 "근거 없이 새로 공백을 끼워 넣는 것"만 막고
    있었고, "근거 없이 있던 공백을 지워버리는 것"은 전혀 막지 못하고
    있었다 — 이 함수가 그 반대 방향을 담당한다.

    두 토큰 사이에 공백이 정확히 하나 있던 단순한 경우만 다루고(다른
    요인이 섞인 복잡한 경우는 판단을 보류), 합친 형태가 사전에 실제로
    등재되어 있을 때만(word_exists) kiwi의 판단을 신뢰해 그대로 둔다.

    두 토큰 사이 "간격"만 위치 기반으로 확인한다(표면형을 이어붙여
    비교하지 않는다) — '합니다'처럼 어간(하)과 다음 형태소(ᆸ니다)가 받침
    하나를 공유해 표면형과 실제 글자가 어긋나는 kiwi 특성(제41항 관련
    로직에서도 이미 확인됨) 때문에, 표면형 재구성 비교는 이런 경우를
    엉뚱하게 걸러내 버린다."""
    tokens = _kiwi.tokenize(text)
    to_restore = []
    for pos, insert_at in _removed_space_points(text, suggested):
        before, after = _straddling_tokens(tokens, pos)
        if before is None or after is None:
            continue
        if text[before.start + before.len : after.start] != " ":
            continue
        if before.form == "안" and after.lemma == "되다":
            # "안 되다"(금지: ~면 안 돼)와 "안되다"(상황이 안 됨: 농사가 안돼)는
            # 같은 형태인데 띄어쓰기가 완전히 반대다. kiwi.space()는 이 둘을
            # 구분하지 못하고 불규칙하게 제안한다(농사가 안돼→안 돼, 테드, 안 돼→안돼).
            # _andoeda_forces_split가 금지 구성(-면/-거든 등)을 확실히 잡으면
            # 그 경우만 띄어쓰기를 강제하고, 나머지는 원문의 띄어쓰기를 보존해
            # 사람이 최종 판단하게 한다 — "애매하면 자동 수정하지 않는다" 원칙.
            if _andoeda_forces_split(tokens, after):
                to_restore.append(insert_at)  # 금지 구성 확정 -> 항상 띄어씀
            else:
                to_restore.append(insert_at)  # 애매함 -> 원문 보존 (사람 확인)
            continue
        if before.tag == "NNG" and after.lemma == "받다" and (
            _is_action_noun(before.form) or before.form in _PASSIVE_ONLY_BATDA_NOUNS
        ):
            continue  # 동작성 명사+받다(접사) -> "호출받다"처럼 사전 미등재라도 항상 붙여씀
        before_part = before.lemma if before.tag.startswith("V") else before.form
        after_part = after.lemma if after.tag.startswith("V") else after.form
        if not word_exists(before_part + after_part):
            to_restore.append(insert_at)

    for insert_at in sorted(to_restore, reverse=True):
        suggested = suggested[:insert_at] + " " + suggested[insert_at:]
    return suggested


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


# "안"(부정 부사)+"되다"는 뜻이 갈리는 두 가지 서로 다른 구성이다 —
# "안되다"(형용사/동사, 하나의 단어: 상황이 좋지 않다·훌륭하게 되지 못하다
# 등, 예: "공부가 안된다")와 "안 되다"(부정 부사 "안"+동사 "되다": 허용·
# 가능하지 않다, 예: "~하면 안 됩니다")는 사전 등재 여부만으로는 구분할 수
# 없다(§20 실사용 버그). 다만 "-면"/"-거든"/"-아서는/-어서는" 같은 조건·전제
# 어미로 이어지는 절 안에 오는 "안 되다"는 사실상 예외 없이 금지·불가
# 구성이므로, 이 경우만 확실한 문법적 근거로 삼아 항상 띄어 쓰도록 강제한다.
# 그 외의 경우(예: "공부가 안된다")는 이 신호가 없으므로 기존 사전 등재
# 판단(항상 붙임)을 그대로 따른다 — 확신이 없는 나머지 경우까지 추정으로
# 판단하지 않는다.
_CONDITIONAL_EC_FORMS = {"면", "거든", "다면", "라면"}

# 2026-07-21 발견: "그렇게 하시면 결과가 안됩니다"처럼 조건 어미와 "안" 사이에
# 주어 등 다른 어절이 끼면, 조건 어미가 "안" 바로 앞 토큰인지만 보는 인접
# 검사가 신호를 놓친다. 그 사이에 오는 어절이 체언(+조사)·부사뿐이고 중간에
# 용언 어간·다른 종결/연결 어미·문장부호가 없으면 여전히 같은 절 안이라고
# 안전하게 볼 수 있으므로, 그 범위까지는 뒤로 훑어 조건 어미를 찾는다.
# 용언 어간이나 다른 어미는 그 자체로 끝나는 형태소가 없어 walk가 그 어미
# 토큰에서 먼저 멈추므로 별도로 막지 않아도 안전하다 — 처음 만나는 EC가
# 조건형이 아니면 그 자리에서 탐색을 끝낸다(더 앞쪽의 조건 어미는 다른 절에
# 속하므로 무시).
_INTERVENING_TAGS = {
    "NNG", "NNP", "NNB", "NR", "SN", "XSN",
    "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
    "MAG",
}
_MAX_CONDITIONAL_LOOKBACK = 5


def _token_index(tokens, target) -> int | None:
    for i, t in enumerate(tokens):
        if t is target:
            return i
    return None


def _conditional_marker_before(tokens, start_idx: int):
    """start_idx부터 뒤로 훑어, 같은 절 안에서 처음 만나는 어미(EC) 토큰을
    돌려준다. 체언·조사·부사(_INTERVENING_TAGS)는 건너뛰고, 그 외 태그나
    탐색 범위(_MAX_CONDITIONAL_LOOKBACK)를 넘으면 None을 돌려준다."""
    i = start_idx
    steps = 0
    while i >= 0 and steps < _MAX_CONDITIONAL_LOOKBACK:
        token = tokens[i]
        if token.tag == "EC":
            return token
        if token.tag not in _INTERVENING_TAGS:
            return None
        i -= 1
        steps += 1
    return None


def _andoeda_forces_split(tokens, after) -> bool:
    """after가 '되다'(그 직전이 부정 부사 '안')일 때, 그 앞 절이 조건·전제
    어미로 이어지는 금지 구성인지 확인한다."""
    idx = _token_index(tokens, after)
    if idx is None or idx < 2:
        return False
    if tokens[idx - 1].form != "안" or tokens[idx - 1].tag != "MAG":
        return False
    marker = _conditional_marker_before(tokens, idx - 2)
    if marker is None:
        return False
    return marker.form in _CONDITIONAL_EC_FORMS or marker.form.startswith(("어서", "아서"))


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


def _protect_unfounded_respacing(text: str, suggested: str) -> str:
    """kiwi.space()가 사전에도 없고 어문 규정에도 근거가 없는 채로 공백을
    새로 끼워 넣자고 제안하는 경우를 되돌린다. 다섯 가지를 막는다:

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
    4. 전문 용어·고유명사·편제 번호 성격의 토큰끼리(_TERM_COMPOUND_TAGS)
       원래 붙어 있던 경우 (예: '제505공수보병연대원', '폭파병', 'E중대',
       '2대대', '20만') — 제49항/제50항이 이미 붙여쓰기를 허용하므로,
       사전에 그 정확한 조합이 없다는 것만으로는 갈라야 할 근거가 안 된다.
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
        if _tokenization_unstable_near(tokens, before, after):
            to_remove.append((j1, j2))
            continue  # kiwi 자신도 이 구간의 형태소 경계를 확신하지 못함 -> 원문 보존
        if before.tag == "NNP" or after.tag == "NNP":
            to_remove.append((j1, j2))
            continue
        if before.tag in _TERM_COMPOUND_TAGS and after.tag in _TERM_COMPOUND_TAGS:
            to_remove.append((j1, j2))
            continue
        if before.tag in _NUMBER_SYMBOL_TAGS and after.tag in _NUMBER_SYMBOL_TAGS:
            to_remove.append((j1, j2))
            continue  # "80%" 같은 숫자+기호 표기 관례 (사전 등재 여부와 무관)
        if before.form == "안" and after.lemma == "되다" and _andoeda_forces_split(tokens, after):
            continue  # 금지 구성 확정 -> 이 공백 삽입은 정답이므로 되돌리지 않는다
        if before.tag == "NNG" and after.lemma == "받다" and (
            _is_action_noun(before.form) or before.form in _PASSIVE_ONLY_BATDA_NOUNS
        ):
            to_remove.append((j1, j2))
            continue  # 동작성 명사+받다(접사) -> "호출받다"처럼 사전 미등재라도 항상 붙여씀
        if after.form == "요" and after.len == 1:
            to_remove.append((j1, j2))
            continue  # 존대 보조사 "요" — _mechanical_respace()와 같은 이유로 항상 보호한다
            # (kiwi가 관형사 등으로 잘못 태깅해도, 원문에 이미 붙어 있었다면 그대로 둔다)
        if after.tag in _ATTACH_TAGS or registered_ending(after.form):
            to_remove.append((j1, j2))
            continue  # 조사·어미(EF뿐 아니라 EC 등 _ATTACH_TAGS 전체)는 제41항에 따라
            # 항상 앞말에 붙는다(_mechanical_respace()와 같은 원칙) — "같잖아요"
            # ("같"+"지"+"않"+"어요"가 "잖"이라는 축약된 한 글자로 압축되는 kiwi
            # 특성 때문에 tokenize()와 space()가 서로 다른 경계를 봄)처럼 앞
            # 형태소가 축약되어 있어도 갈라놓을 근거는 없다. kiwi가 태그를 다르게
            # 매길 가능성에 대비해, "-form"이 사전에 등재된 어미·접사 표제어인지도
            # 함께 확인한다(registered_ending — kiwi 태그가 아니라 사전 표제어
            # 자체를 최종 근거로 삼는다).
        # 용언(동사/형용사) 토큰은 표면형이 어간뿐이라(예: '하다가'의 '하'),
        # 사전 기본형(lemma)으로 합쳐야 '한잔하다' 같은 등재된 복합동사를
        # 알아볼 수 있다. '한잔'+'하'로는 사전에 없지만 '한잔'+'하다'는 있음.
        # 간격 확인은 표면형을 이어붙여 비교하지 않는다 — '잘해야'(잘+하다의
        # 활용형 '해')처럼 어간과 어미가 받침/음절을 공유해 표면형과 실제
        # 글자가 어긋나는 kiwi 특성(제41항 관련 로직에서도 이미 확인됨)
        # 때문에, 표면형 재구성 비교는 이런 경우를 엉뚱하게 걸러내 버린다.
        # 대신 두 토큰이 실제로 빈틈없이 맞닿아 있는지만 위치로 확인한다.
        if before.start + before.len != after.start:
            continue
        # before가 연결어미(EC)이고 그 앞에 어간이 바로 붙어 있으면(예:
        # '기어다니다'의 '기'+'어', '데려다주다'의 '데리'+'어다'), EC 하나만
        #으로는 사전 표제어와 비교할 수 없다 — 어간까지 포함한 실제 표면형
        # ('기어', '데려다')을 써야 correct_aux_verb_spacing() 패턴 1과 같은
        # 방식으로 후보를 만들 수 있다. lemma가 아니라 표면형을 쓰는 이유는
        # '기다'+'어'='기어'처럼 축약된 실제 표기를 그대로 보존해야 하기
        # 때문이다(어간 lemma를 쓰면 '기다다니다'처럼 없는 말이 된다).
        before_part = before.form
        if before.tag == "EC":
            # 어간과 어미가 받침/음절을 공유해 위치가 살짝 겹치는 경우
            # ('데리'+'어다'='데려다'처럼 어간의 끝과 EC의 시작 위치가
            # 정확히 맞닿지 않는 경우도 있음)까지 잡기 위해, 토큰 목록
            # 상의 순서(바로 이전 토큰)로 어간을 찾는다 — 위치 비교
            # (_straddling_tokens)는 겹치는 경우 엉뚱한 토큰을 찾아온다.
            before_idx = _token_index(tokens, before)
            stem = tokens[before_idx - 1] if before_idx and before_idx >= 1 else None
            if stem is not None and stem.tag.startswith("V") and stem.start < before.start:
                before_part = text[stem.start : before.start + before.len]
        elif before.tag.startswith("V"):
            before_part = before.lemma
        after_part = after.lemma if after.tag.startswith("V") else after.form
        if word_exists(before_part + after_part):
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
    # 권위 있는 근거이므로, kiwi의 제안에서 그 부분만 원상복구해 오탐지를 막는다.
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
    suggested = _protect_unfounded_joining(text, suggested)

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
    dialect_map: dict[str, str] | None = None,
    dialect_modes: dict[str, str] | None = None,
) -> tuple[list[SubtitleEntry], list[FlagItem], list[str]]:
    """entries를 처리한다.

    반환값: (자동 교정 반영된 entries, 플래그 목록, 확인 불필요 자동 교정 로그)
    나머지 검사(맞춤법/띄어쓰기)는 자동 교정이 끝난 텍스트를 기준으로 수행한다.

    본격적인 처리 전에, 문서 전체에서 반복 등장하는 미등록 단어(주로
    고유명사)를 자동으로 감지해 kiwi에 등록한다(register_custom_words
    참고) — 사용자가 이름 목록을 따로 적지 않아도 이 자동 감지만으로
    대부분의 고유명사 오분석이 해결된다.

    dialect_map에 지정된 화자는 dialect_modes의 모드에 따라 처리한다(기본값은
    "protect"):
      - protect: 원문을 그대로 두고 표준화 교정·플래그를 전부 건너뛴다.
      - assist: 텍스트는 그대로, 표준어→사투리 제안 플래그만 남긴다.
      - to_standard: 사투리→표준어 변환 후 표준화 파이프라인을 적용한다.
    사투리 미지정 화자는 기존대로 표준화 파이프라인을 돌리고, 이름이 있으면
    자동 감지 플래그(비율 >= 0.15)를 남긴다.
    """
    corrected_entries = []
    flags = []
    applied_log = []

    auto_detected = detect_recurring_unknown_words(entries)
    if auto_detected:
        register_custom_words(auto_detected, tag="NNP")
        applied_log.append(f"[자동 감지] 반복 등장하는 고유명사로 인식해 등록: {', '.join(auto_detected)}")

    for e in entries:
        # 사투리 모드를 가장 먼저 결정한다 — 표준화 파이프라인을 돌리기 전에
        # 이 화자의 대사를 건드려도 되는지 판단해야 하기 때문이다. 대본 속
        # 사투리는 대부분 작가의 의도이므로, 지정된 화자의 기본값(protect)은
        # 어떤 교정·플래그도 하지 않고 원문을 그대로 둔다.
        region, mode = resolve_dialect_mode(e.speaker, dialect_map, dialect_modes)

        # protect — 원문을 완전히 그대로 둔다. 표준화 교정도, 외래어/고유명사
        # 검토 플래그도, 맞춤법/순화어/띄어쓰기 검사도 전부 건너뛴다.
        # (지정된 화자의 대사 안에 진짜 오타가 있어도 그대로 두는 것을 감수한다 —
        #  "의도된 사투리"와 "오타"를 확실히 구분하는 것은 판별 불가능한 경계
        #  사례라, 확률적 추정으로 자동 수정하지 않는 것이 이 프로젝트의 정책이다.)
        if region is not None and mode == "protect":
            corrected_entries.append(
                SubtitleEntry(
                    index=e.index, start=e.start, end=e.end,
                    text=e.text, speaker=e.speaker,
                )
            )
            continue

        # assist — 텍스트는 그대로 두고 표준화 파이프라인도 돌리지 않는다
        # (표준화는 의도와 정반대다). 표준어→사투리 제안 플래그만 남긴다.
        if region is not None and mode == "assist":
            _, dialect_flags = check_dialect(e.index, e.text, region, mode)
            flags.extend(dialect_flags)
            corrected_entries.append(
                SubtitleEntry(
                    index=e.index, start=e.start, end=e.end,
                    text=e.text, speaker=e.speaker,
                )
            )
            continue

        # 여기부터: 사투리 미지정 화자 또는 to_standard 화자.
        # to_standard는 먼저 사투리→표준어로 변환한 뒤, 변환된 표준어 텍스트에
        # 일반 표준화 파이프라인을 적용한다(이 화자는 표준 출력을 원한다).
        corrected_text = e.text
        if region is not None and mode == "to_standard":
            corrected_text, dialect_flags = check_dialect(
                e.index, corrected_text, region, mode,
            )
            flags.extend(dialect_flags)
            if corrected_text != e.text:
                applied_log.append(f"[{e.index}] 사투리→표준어 변환: {corrected_text}")

        corrected_text, applied_fixes, review_fixes, proper_noun_fixes = correct_loanwords(corrected_text)
        corrected_text, particle_fixes = correct_particle_spacing(corrected_text)
        corrected_text, compound_fixes = correct_compound_spacing(corrected_text)
        corrected_text, aux_verb_fixes = correct_aux_verb_spacing(corrected_text)
        corrected_text, always_wrong_fixes = correct_always_wrong(corrected_text)
        corrected_text, nonstandard_fixes = correct_nonstandard_terms(corrected_text)
        corrected_text, discriminatory_fixes = correct_discriminatory_terms(corrected_text)
        corrected_text, former_term_fixes, former_term_flags = correct_former_terms(
            e.index, corrected_text
        )
        applied_log.extend(
            f"[{e.index}] {fix}"
            for fix in applied_fixes
            + particle_fixes
            + compound_fixes
            + aux_verb_fixes
            + always_wrong_fixes
            + nonstandard_fixes
            + discriminatory_fixes
            + former_term_fixes
        )
        flags.extend(former_term_flags)

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

        # 사투리 미지정 화자(이름은 있으나 지역 지정 없음)는 자동 감지 플래그만 남긴다.
        if region is None and e.speaker:
            _, dialect_flags = check_dialect(e.index, corrected_text, None, None)
            flags.extend(dialect_flags)

        flags.extend(
            f
            for f in (
                check_spelling(e.index, corrected_text),
                check_purified_terms(e.index, corrected_text),
                check_spacing(e.index, corrected_text),
            )
            if f
        )

        corrected_entries.append(
            SubtitleEntry(
                index=e.index, start=e.start, end=e.end,
                text=corrected_text, speaker=e.speaker,
            )
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
