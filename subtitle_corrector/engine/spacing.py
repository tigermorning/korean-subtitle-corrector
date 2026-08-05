"""띄어쓰기 자동 교정 — 조사·어미 붙임(제41항), 합성어(제42항), 보조 용언(제47항).
"""

from ..dictionary import compound_status, definition_markers, word_exists
from ..report import FlagItem
from .text_utils import (
    _bracket_spans,
    _force_span,
    _inside_any_span,
    _josa,
    _localized_change,
    _surface_span,
)
from .kiwi_adapter import (
    _AMBIGUOUS_FOLLOW_TAGS,
    _ATTACH_TAGS,
    _MANDATORY_BOUNDARY_TAGS,
    _PUNCT_TAG_PREFIX,
    _kiwi,
    _merged_particle_reading_exists,
)
from .options import SubtitleMarkers, normalize_spacing_mode
from .markers import _after_subtitle_marker

def _mechanical_respace(text: str, markers: "SubtitleMarkers | None" = None) -> str:
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
        if _after_subtitle_marker(text, gap_start, markers):
            continue  # 자막 표시와 말자막 사이 한 칸은 규칙이라 지우지 않는다
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
            # **부사 뒤에 띄어 쓴 접미사는 붙이지 않는다.** 부사+용언 구(句)와
            # 파생·합성 동사가 둘 다 존재하고 표기가 뜻을 가르는 자리다:
            # '안 되다'(금지)/'안되다'(상황이 안 됨), '못 하다'(하지 못함)/'못하다'
            # (능력 부족), '더 하다'(추가로 하다)/'더하다'(보태다). 원문이 띄어 놓았다면
            # 그 선택을 보존한다 — 2026-08-03 실사용 감수에서 '증축을 더 해도 되겠네요'가
            # '더해도'로 붙었다(사용자 제공 자막 4강 103번). 전에는 '안'만 막고 있었다.
            if t1.tag == "MAG" and gap_start != gap_end:
                continue
            # 행 끝에 띄어 쓴 '나'는 조사('백 배 나'→'백 배나')인지 '낫다'의 활용
            # '나아'의 오기인지 문맥 없이 가릴 수 없다. 붙여 버리면 '나아'였을
            # 가능성을 지우므로, 원문 간격을 보존하고 check_ambiguous_particle()이
            # 사람 확인용 플래그를 남긴다.
            if (
                t2.form == "나"
                and t2.tag == "JX"
                and gap_start != gap_end
                and i + 1 == len(tokens) - 1
            ):
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
            # 조사 뒤에 붙어 있는 글자가 실은 그 조사의 일부일 수 있으면(에+서 =
            # '에서') 어느 읽기가 맞는지 문맥이 정한다. 자동으로 갈라놓지 않고
            # 원문 간격을 보존한다 — check_spacing()이 사람 확인용 제안을 남긴다.
            if (
                gap_start == gap_end
                and t1.tag.startswith("J")
                and _merged_particle_reading_exists(text, t1, t2)
            ):
                continue
            desired_gap = " "  # 어절이 완결된 지점 -> 새 어절은 항상 띄어씀
        elif (
            t1.tag == "MAJ"
            and gap_start == gap_end
            and t2.tag not in _ATTACH_TAGS
            # 구두점 앞에는 공백을 두지 않는다(문맥 무관 규칙, 2026-08-03 사용자 지정).
            # 이 조건이 없어 '하지만...'이 '하지만 ...'으로, "'하지만'이라뇨?"가
            # "'하지만 '이라뇨?"로 벌어졌다(2026-08-04 사용자 제공 자막 5강 401·402번).
            and not t2.tag.startswith(_PUNCT_TAG_PREFIX)
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


def correct_particle_spacing(
    text: str, markers: "SubtitleMarkers | None" = None
) -> tuple[str, list[str]]:
    """조사·어미·접미사 결합 지점의 띄어쓰기 오류를 자동으로 정리한다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문조각 -> 교정조각')
    """
    corrected = _mechanical_respace(text, markers)
    applied = [_localized_change(text, corrected)] if corrected != text else []
    return corrected, applied


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
    # 용언 관형사형(보/VV+ㄴ/ETM 등)이 이끄는 조합은 '본 집'(보다+집)처럼 구문
    # 읽기가 항상 가능해 정답이 하나로 확정되지 않으므로, 사전에 합성어로
    # 등재돼 있어도 자동으로 붙이지 않는다(자동 교정은 정답이 100% 하나일 때만).
    tokens = _kiwi.tokenize(text)
    adnominal_starts = {t.start for t in tokens if t.tag in ("VV", "VA")}
    start_to_idx = {}
    for idx, tok in enumerate(tokens):
        start_to_idx.setdefault(tok.start, idx)

    def left_grouping_ambiguous(start: int) -> bool:
        """병합 시작 토큰(예: '보물선 투자'에서 kiwi가 '보물선'을 '보물'+'선'으로
        쪼갠 '선')이 바로 앞 명사와 붙어 다른 사전 표제어(보물+선='보물선')를
        이루면, 그 토큰은 좌우 어느 쪽에도 붙을 수 있어 병합 결과가 유일하지
        않다 — 자동 병합하지 않는다."""
        idx = start_to_idx.get(start)
        if not idx:
            return False
        prev, lead = tokens[idx - 1], tokens[idx]
        if prev.tag not in ("NNG", "NNP"):
            return False
        if prev.start + prev.len != lead.start:
            return False  # 사이에 공백/다른 토큰이 있으면 좌측 결합 후보 아님
        return word_exists(prev.form + lead.form)

    # 자막 표시(효과음·지문·화자명) 안쪽은 일반 문장 규칙의 대상이 아니다.
    # 2026-08-02 실사용: SDH 효과음 '[탁 - 차 문]'의 '차 문'이 '차문'으로 병합됐다.
    # '차문'은 사전 표제어이긴 하나 뜻이 借文(대작)·借問(물음)·조선 상소문뿐이라
    # 자동차 문과 무관하다. 표시 안은 이미 맞춤법·띄어쓰기 제안에서 빼고 있었는데
    # 합성어 병합만 빠져 있었다.
    brackets = _bracket_spans(text)

    fixes = []  # (start, end, replacement, description) — 지금은 비어 있다(아래 주석 참고)
    candidates = []  # (start, end, 붙임형, 원문) — 사람에게 물을 후보
    for start, boundary, end in _compound_candidate_spans(text):
        if _inside_any_span(start, brackets) or _inside_any_span(boundary, brackets):
            continue
        if start in adnominal_starts:
            continue
        if left_grouping_ambiguous(start):
            continue
        original = text[start:end]
        combined = text[start:boundary] + text[boundary:end].lstrip(" ")
        if original == combined:
            continue  # 이미 붙어 있음
        if _positional_noun_phrase(text, boundary, end):
            continue
        if compound_status(combined) == "합성어":
            # 붙임형이 '준말'(예: 큰애='큰아이'의 준말)이나 '비유적'(예: 턱밑)
            # 표제어면, 띄어 쓴 구(句)와 의미가 경쟁하므로 문맥 없이 자동으로
            # 붙이지 않는다. 명사+명사 경우는 check_ambiguous_compound()가 확인
            # 플래그를, 용언 관형사형+명사(큰 애들=크다+애들)는 명백한 구라
            # 아무 처리도 하지 않는다.
            if definition_markers(combined):
                continue
            # **자동으로 붙이지 않는다(2026-08-04 사용자 결정).** 붙임형이 표제어라는 것은
            # "붙여 쓸 수도 있다"는 근거이지 원문이 띄어 쓴 것이 틀렸다는 근거가 아니다.
            # 실사용에서 뜻이 바뀌는 사고가 반복됐다 — '남의 집 개'->'집개'(집에서 기르는
            # 개), '따지러 온 다음 날'->'다음날'(정해지지 않은 미래의 어떤 날),
            # '예산 안에서'->'예산안'. 사전은 이 넷과 '노천 카페'->'노천카페'(타당)를
            # 가르지 못한다(모두 표제어·표지 없음). 그래서 후보만 모아
            # check_compound_merge_candidate()가 확인 항목으로 낸다.
            candidates.append((start, end, combined, original))

    corrected = text
    applied = []
    for start, end, replacement, desc in sorted(fixes, key=lambda f: f[0], reverse=True):
        corrected = corrected[:start] + replacement + corrected[end:]
        applied.append(desc)
    _MERGE_CANDIDATES[text] = candidates
    return corrected, list(reversed(applied))


# 마지막으로 계산한 병합 후보. correct_compound_spacing()은 (텍스트, 로그)만 돌려주는
# 계약이라 후보를 함께 실어 보낼 자리가 없다 — 같은 줄에 대해 곧바로 호출되는
# check_compound_merge_candidate()가 이 값을 읽는다. 파이프라인은 한 줄씩 순서대로
# 처리하므로 이 방식이 성립한다.
_MERGE_CANDIDATES: dict[str, list] = {}


def check_compound_merge_candidate(index: int, text: str) -> FlagItem | None:
    """띄어 쓴 명사 연쇄를 붙여 쓸 후보로 확인 플래그한다('노천 카페' -> '노천카페').

    자동으로 붙이지 않는 이유는 correct_compound_spacing() 안의 주석에 있다 — 사전은
    뜻이 바뀌는 경우('집 개' -> '집개')와 타당한 경우('노천 카페' -> '노천카페')를 가르지
    못한다. 판정은 사람이 한다.
    """
    candidates = _MERGE_CANDIDATES.get(text) or []
    for _start, _end, combined, original in candidates:
        suggested = text.replace(original, combined, 1)
        if suggested == text:
            continue
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'{combined}'{_josa(combined, '이')} 사전 표제어이므로 "
                f"'{original}'{_josa(original, '을')} 붙여 쓸 수 있습니다. "
                "다만 붙이면 뜻이 달라지는 경우가 있어(예: '집 개'와 '집개') 자동으로 "
                "바꾸지 않았습니다 — 문맥 확인이 필요합니다."
            ),
        )
    return None


# 위치·방향을 뜻하는 자립명사. 앞말과 띄어 써서 "그 범위의 내부/외부"를 나타내는 용법이
# 매우 흔하다('예산 안에서', '집 밖으로', '책상 위에'). 그런데 붙인 형태가 우연히 다른
# 뜻의 사전 표제어인 경우가 있어('예산안' = 예산 案), 합성어 병합이 원문의 뜻을 바꿔
# 버린다 — 2026-08-03 실사용 감수에서 '예산 안에서 5m 정도 늘리고'가 '예산안에서'로
# 바뀌었다(사용자 제공 자막 4강 160·203번).
_POSITIONAL_NOUNS = frozenset({"안", "밖", "속", "위", "아래", "앞", "뒤", "옆", "사이", "가운데"})


# 위치 명사에 붙어 "그 범위에서/으로"를 만드는 부사격 조사. 이 조사가 붙어 있으면 위치
# 표현으로 읽는 것이 자연스럽다.
_POSITIONAL_PARTICLES = ("에서", "에다", "에", "으로", "로", "까지", "부터")


def _positional_noun_phrase(text: str, boundary: int, end: int) -> bool:
    """병합 후보의 뒷말이 '안/밖/속/위…' + 부사격 조사인지 — 그렇다면 붙이지 않는다."""
    tail = text[boundary:end].lstrip(" ")
    for noun in _POSITIONAL_NOUNS:
        if not tail.startswith(noun):
            continue
        rest = tail[len(noun):]
        if not rest:
            return True  # '예산 안'처럼 조사 없이 끝나도 위치 표현일 수 있다
        if any(rest.startswith(particle) for particle in _POSITIONAL_PARTICLES):
            return True
    return False


def check_ambiguous_compound(index: int, text: str) -> FlagItem | None:
    """붙이면 사전 합성어(비유어/준말)가 되지만 띄어 쓰면 글자 그대로의 구(句)로도
    읽히는 '명사+명사' 조합을 확인 플래그한다 (예: '턱 밑' ↔ 턱밑=비유어 '아주
    가까운 곳'). correct_compound_spacing()이 이런 표지 있는 합성어를 자동으로
    붙이지 않으므로, 대신 여기서 사람이 문맥으로 판단하도록 남긴다.

    용언 관형사형+명사(예: '큰 애들' = 크다의 관형형 '큰' + '애들')는 명백한
    구이므로 플래그하지 않는다 — 사용자 확인 사항."""
    tokens = _kiwi.tokenize(text)
    # 용언 어간(VV/VA)이 시작하는 위치. 관형사형 어미(ㄴ 등)가 어간과 같은
    # start를 공유할 수 있어(예: '크'/VA와 'ㄴ'/ETM이 둘 다 start=14) dict로는
    # 덮어써지므로 집합으로 모은다.
    adnominal_starts = {t.start for t in tokens if t.tag in ("VV", "VA")}
    for start, boundary, end in _compound_candidate_spans(text):
        original = text[start:end]
        combined = text[start:boundary] + text[boundary:end].lstrip(" ")
        if original == combined:
            continue  # 이미 붙어 있으면 대상 아님
        if start in adnominal_starts:
            continue  # 용언 관형사형+명사 = 구, 플래그 안 함
        if compound_status(combined) != "합성어":
            continue
        if not definition_markers(combined):
            continue
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{combined}'로 붙여 쓰면 사전 표제어(비유·준말)가 되지만, "
                f"'{original}'처럼 띄어 쓰면 글자 그대로의 뜻일 수 있어 문맥 확인이 필요합니다."
            ),
            suggested_fix=text[:start] + combined + text[end:],
        )
    return None


_AUX_EC_FORMS = {"아", "어", "여"}


_AUX_NNB_FORMS = {"뻔", "만", "법", "듯", "성", "직", "척", "체", "양"}


# "-아/어지다"(피동·사동)와 "-아/어하다"는 제47항의 "붙임 허용"(원칙은 띄어쓰기,
# 붙임은 허용되는 예외) 대상이 아니라 별도 규정으로 "항상 붙임"이 원칙인
# 완전히 다른 규칙이다. 형태만 보면 패턴 1(본용언-아/어+보조용언)과 똑같이
# 생겨서(예: "전해지다"의 "지"도 kiwi가 VX로 태깅) 자칫 같은 패턴으로 오인해
# "전해졌다"를 "전해 졌다"로 잘못 갈라놓을 위험이 있어, lemma로 구분해 제외한다.
_ALWAYS_ATTACHED_AUX_LEMMAS = {"지다", "하다"}


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
        if (
            prev.tag == "ETM"
            and cur.tag == "NNB"
            and cur.form in _AUX_NNB_FORMS
            and nxt.tag in ("XSA", "XSV", "VX")
        ):
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
    """제47항 원칙(띄어쓰기) 기준으로만 교정하는 얇은 래퍼.

    문서 전체의 기준을 고르는 경로는 _aux_verb_spacing()이다. 이 함수는 기준을
    고를 필요가 없는 호출부(원칙이 곧 기본값인 경우)를 위해 남겨 둔다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    corrected, applied, _ = _aux_verb_spacing(text, "principle")
    return corrected, applied


def _aux_verb_spacing(text: str, mode: str = "principle") -> tuple[str, list[str], list[str]]:
    """한글 맞춤법 제47항: 보조 용언은 "띄어 씀을 원칙으로 하되, 붙여 씀도
    허용"한다 — 둘 다 맞는 표기다. mode가 어느 쪽으로 통일할지 정한다.

      keep(기본값)      — 아무것도 바꾸지 않는다. 원문의 선택을 그대로 둔다.
      principle         — 붙여 쓴 형태를 띄어 쓴 형태로 바꾼다.
      allowance         — 띄어 쓴 형태를 붙여 쓴 형태로 바꾼다.

    어느 쪽이든 대상 구간(패턴 1·2)은 같고 간격을 넣느냐 빼느냐만 갈린다.
    문서 한 편에는 한 mode만 적용되므로 원칙과 허용이 섞이지 않는다.

    _normalize_aux_verb_spacing()과 대상 패턴은 같지만 역할이 다르다 — 그쪽은
    원문에서 이미 확정된 형태를 "정답"으로 보고 kiwi 제안을 원문에 맞춰
    되돌리는(플래그 방지용) 함수라 mode와 무관하게 그대로 동작한다. 이 함수는
    실제 텍스트 자체를 선택된 기준으로 자동 교정한다.

    붙임이 규정상 불가능한 구간(본용언이 3음절 이상 합성어, 의존명사+하다
    조합이 사전에 없음)은 allowance에서도 띄어 쓴다. 이건 기준 혼용이 아니라
    제47항 자체의 예외이므로, 사용자가 오해하지 않도록 세 번째 반환값으로
    사유를 돌려준다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록, 붙임 불가 구간 안내 목록)
    """
    normalized = normalize_spacing_mode(mode)
    if normalized == "keep":
        return text, [], []  # 원문 유지가 기본 — 원칙·허용 둘 다 규범상 맞다
    joining = normalized == "allowance"
    tokens = _kiwi.tokenize(text)
    edits = set()  # {(gap_start, gap_end, replacement)}
    blocked: list[str] = []

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
            gap_start, gap_end = cur.start + cur.len, nxt.start
            gap = text[gap_start:gap_end]
            span = _surface_span(text, prev.start, nxt.start + nxt.len)

            stem_len = (cur.start + cur.len) - prev.start
            if stem_len >= 3 and compound_status(prev.lemma) == "합성어":
                # 항상 띄움 예외. 원칙에서는 이미 붙어 있을 수 없어 그냥 넘기고,
                # 허용에서는 붙이면 안 되는 구간이므로 사유를 남긴다.
                if joining and gap.strip() == "" and gap != "":
                    blocked.append(
                        f"'{span}': 본용언이 3음절 이상 합성어라 제47항 붙임 허용 대상이 "
                        "아님 -> 허용 기준에서도 띄어 씀"
                    )
                continue
            if joining:
                if gap.strip() == "" and gap != "":
                    edits.add((gap_start, gap_end, ""))
                continue
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
            if gap == "":
                edits.add((gap_start, gap_end, " "))

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
        # **앞 토큰이 관형사형 어미(ETM)여야 한다.** 이 조건이 없어 사전 표제어의
        # 하이픈 표기가 깨졌다 — `'그럴-듯하다'`에서 prev가 하이픈(SO)이라 그 뒤에
        # 공백이 들어가 `'그럴- 듯하다'`가 됐다(2026-08-04 규칙 전수 점검에서 발견).
        # 패턴 2는 애초에 "관형사형+의존명사+하다"를 다루는 규칙이므로, 관형사형이
        # 아닌 것이 앞에 오면 이 규칙의 대상이 아니다.
        if (
            prev.tag == "ETM"
            and cur.tag == "NNB"
            and cur.form in _AUX_NNB_FORMS
            and nxt.tag in ("XSA", "XSV", "VX")
        ):
            lead_word_start = prev.start
            if i >= 2 and tokens[i - 2].start + tokens[i - 2].len > prev.start:
                lead_word_start = tokens[i - 2].start  # 그렇+ㄹ 같은 받침 공유 보정
            nxt_citation = nxt.lemma if nxt.lemma.endswith("다") else nxt.lemma + "다"
            whole_candidate = text[lead_word_start : cur.start + cur.len] + nxt_citation
            if word_exists(whole_candidate):
                continue  # (a) 전체가 통째로 하나의 표제어 -> 그대로 둔다
            lead_start, lead_end = prev.start + prev.len, cur.start
            lead_gap = text[lead_start:lead_end]
            if not word_exists(cur.form + nxt_citation):
                # 의존명사+하다/싶다 단독 조합조차 사전에 없는 예외적
                # 경우 -> 붙여 쓴다고 단정하지 않고 그대로 둔다.
                if joining and lead_gap.strip() == "" and lead_gap != "":
                    span = _surface_span(text, lead_word_start, nxt.start + nxt.len)
                    blocked.append(
                        f"'{span}': '{cur.form}{nxt_citation}'"
                        f"{_josa(nxt_citation or cur.form, '가')} 사전에 없어 붙임 근거가 "
                        "없음 -> 허용 기준에서도 띄어 씀"
                    )
                continue
            if joining:
                # 허용: 관형사형+의존명사 사이를 붙인다(예: '올 듯하다' -> '올듯하다').
                if lead_gap.strip() == "" and lead_gap != "":
                    edits.add((lead_start, lead_end, ""))
            elif lead_gap == "":
                edits.add((lead_start, lead_end, " "))  # (b)
            # (c) 의존명사+하다/싶다 사이는 어느 기준에서도 건드리지 않는다
            # (사전 등재 형태라 항상 붙임 — 트레일링 간격은 애초에 edits에
            # 추가한 적이 없다).

    corrected = text
    for gap_start, gap_end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        corrected = corrected[:gap_start] + replacement + corrected[gap_end:]
    applied = [_localized_change(text, corrected)] if corrected != text else []
    return corrected, applied, blocked
