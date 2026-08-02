"""
"이 표기를 무엇으로 바꿔야 하는가" 계열 판정.

규범 표기 재지정, 전(前) 용어, 외래어 표기 용례, 순화어 — 사전이 **대안 표기까지**
확정해 준 경우만 다룬다. 대안이 하나로 확정되지 않으면 여기서 답을 만들지 않는다.
"""

import difflib
import re
from functools import lru_cache
from .clients import search_kornorms, search_onyongeo, search_opendict, search_stdict
from .headwords import _opendict_item_is_standard

_STANDARD_REPLACEMENT_RE = re.compile(
    r"(?:규범 표기는|표준 용어는)\s*[‘']([^’']+)[’']"
)


def standard_term_replacement(query: str) -> str | None:
    """query가 우리말샘에 "규범 표기는/표준 용어는 'X'이다"로 명시된 비표준
    표기라면, 그 대안(X)을 돌려준다("요오드"→"아이오딘"). "미확정"처럼 특정
    대안이 없는 경우나, 애초에 비표준 표기가 아닌 경우는 None을 돌려준다.

    "초코렛"류(일반 외래어 오표기)는 이미 kornorms(외래어 표기 용례)의
    relate_mark_o "(X)" 표시로 잡히지만, "요오드"(화학 용어)처럼 kornorms는
    오히려 정답으로 등재하고("Jod"의 정식 번역어) 우리말샘만 "표준 용어는
    다른 것"이라고 안내하는 경우가 있다 — 전문 용어 표준화가 kornorms보다
    우리말샘에 먼저/추가로 반영된 것으로 보인다(실사용 검증으로 발견)."""
    matches = [
        item
        for item in search_opendict(query).get("channel", {}).get("item", [])
        if (item.get("word") or "").replace("-", "").replace("^", "") == query
    ]
    if not matches:
        return None
    # "집"처럼 같은 표제어 아래 표준 동형이의어(집=거처)와 비표준 동형이의어
    # (집=즙의 옛 표기)가 우연히 같이 있을 수 있다 — 표준으로 쓰이는 동형이의어가
    # 하나라도 있으면, 이 표기 자체를 신조어/오표기로 단정하지 않는다
    # (word_exists()와 동일한 안전장치, 실사용 검증으로 발견).
    if any(_opendict_item_is_standard(item) for item in matches):
        return None
    for item in matches:
        for sense in item.get("sense", []):
            match = _STANDARD_REPLACEMENT_RE.search(sense.get("definition") or "")
            if match:
                return match.group(1)
    return None


# 표준국어대사전이 "'뇌전증'의 전 용어.", "'조현병'의 전 용어."처럼 옛 용어를
# 안내하는 문구. 대상 용어는 통낫표(‘’)로 감싸며, 곧바로 "의 전 용어"가 온다.
# 곧은 따옴표('')로 온 경우도 fallback으로 함께 잡는다. 여기서 group(1)이
# 현재 표준 용어(교체 대상)다. "낮잡아 이르는 말"/"속되게 이르는 말"(예:
# 문둥이·지랄병)은 이 문구가 아니므로 이 규칙이 건드리지 않는다 — 정확히
# "전 용어" 표지만 매칭한다.
_FORMER_TERM_RE = re.compile(r"[‘']([^’']+)[’']의\s*전\s*용어")


@lru_cache(maxsize=4096)
def former_term_field(word: str) -> str | None:
    """word의 "전 용어" 안내가 어느 전문 분야 뜻에 달려 있는지 돌려준다.

    표준국어대사전 검색 API는 분야(cat)를 주지 않고 우리말샘은 준다. 2026-08-02
    실사용에서 '원통'이 옛 용어로 안내됐는데, 그 안내는 **수학 분야 뜻**('원기둥'의
    전 용어)에만 달려 있고 일상적인 뜻('분하고 억울함')과는 무관했다. 분야를 함께
    보여주면 사람이 문맥을 보고 즉시 판단할 수 있다.

    반환값: 분야 이름(예: "수학"), 분야 표시가 없거나 조회 실패면 None.
    """
    try:
        items = search_opendict(word).get("channel", {}).get("item", [])
    except Exception:
        return None
    if isinstance(items, dict):
        items = [items]
    for item in items:
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword != word:
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        for sense in senses:
            if _FORMER_TERM_RE.search((sense.get("definition") or "")):
                return (sense.get("cat") or "").strip() or None
    return None


@lru_cache(maxsize=4096)
def former_term_lookup(word: str) -> dict | None:
    """word가 표준국어대사전에서 "'X'의 전 용어."로 표시된 옛 용어(지양 대상)면,
    그 현재 표준 용어(X)와 동형이의 판정 정보를 돌려준다.

    표준국어대사전은 표준 용어가 바뀐 옛 표기(예: "간질"→"뇌전증",
    "정신분열증"→"조현병")를 뜻풀이 끝에 "'X'의 전 용어."로 안내한다. 다만
    "간질"처럼 옛 용어 뜻 외에 전혀 다른 뜻(곤충 이름·조직 이름·'간질거리다'
    어근 등)이 같이 등재된 동형이의어가 있어, 문맥 없이 무턱대고 바꾸면 다른
    뜻을 훼손한다. 그래서 판단 근거만 모아 돌려주고, 자동 교정할지 플래그만
    할지는 호출부가 결정한다.

    반환값:
    - None: 이 단어에 "전 용어" 뜻이 하나도 없음(교체 대상 아님. 현재 표준
      용어인 "뇌전증"/"조현병"도 여기 해당해 절대 플래그되지 않는다).
    - {"target": X, "ambiguous": bool, "other_meanings": [...]}:
        target       = 현재 표준 용어(교체 목표)
        ambiguous    = "전 용어"가 아닌 다른 뜻이 하나라도 있으면 True
                       (모든 뜻이 "전 용어" 뜻이면 False → 안전하게 자동 교체 가능)
        other_meanings = "전 용어"가 아닌 나머지 뜻풀이 목록(플래그 사유에 실어
                         사람이 문맥으로 판단하게 함)

    조회·파싱 실패는 search_dialect/standard_term_replacement와 같은 원칙으로
    None(교체 대상 아님)으로 흡수해 파이프라인이 멈추지 않게 한다."""
    try:
        data = search_stdict(word)
    except Exception:
        return None
    items = data.get("channel", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    former_target = None
    other_meanings: list[str] = []
    has_former = False
    for item in items:
        # 검색 API가 부분일치 표제어까지 돌려줄 수 있으므로, 조회한 단어와
        # 정확히 일치하는 표제어의 뜻만 본다(word_exists 등과 같은 안전장치).
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword != word:
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        for sense in senses:
            definition = (sense.get("definition") or "").strip()
            match = _FORMER_TERM_RE.search(definition)
            if match:
                has_former = True
                if former_target is None:
                    former_target = match.group(1)
            elif definition:
                other_meanings.append(definition)
    if not has_former:
        return None
    return {
        "target": former_target,
        "ambiguous": bool(other_meanings),
        "other_meanings": other_meanings,
    }


def _closest_segment(token: str, korean_mark: str) -> str:
    """korean_mark가 '성, 이름' 형식(콤마로 여러 조각)이면, token과 가장 비슷한
    조각 하나만 골라 돌려준다. 그렇지 않으면 korean_mark를 그대로 돌려준다.

    인명 항목의 korean_mark는 전체 이름("스노, 에드거 파크스")을 담고 있어서,
    token 하나("스노우")를 그대로 전체 이름으로 바꿔버리면 문장에 엉뚱한
    이름 전체가 삽입되는 오류가 생긴다. 이를 막기 위한 안전장치다.
    """
    parts = [p.strip() for p in korean_mark.split(",") if p.strip()]
    if len(parts) <= 1:
        return korean_mark
    return max(parts, key=lambda p: difflib.SequenceMatcher(None, token, p).ratio())


def loanword_fix(token: str) -> tuple[str | None, bool, str | None]:
    """token이 국립국어원이 명시적으로 틀렸다고 표시한 외래어 표기(relate_mark_o에
    '(X)'로 표시)와 일치하면, 공식 정답(korean_mark 중 token에 해당하는 부분)을
    돌려준다. token 자체가 이미 맞는 표기이거나 kornorms에 없는 단어면
    (None, False, None)을 돌려준다.

    반환값: (교정값 또는 None, 사람 확인 필요 여부, 참고용 전체 맥락 또는 None)

    판단 기준은 "인명이냐 일반 용어냐"가 아니라 "**검색된 정답이 하나로
    일치하느냐**"다:
    - kornorms에 등재된 모든 일치 항목이 같은 교정값을 가리키면, 이미 국립
      국어원이 확정한 단일 정답이라는 뜻이므로 확인 없이 자동 반영한다
      (예: "스노우"는 인명 표기에서도 항상 "스노"가 맞다 — 이건 문맥에
      따라 갈리는 게 아니라 그냥 확정된 표기 오류다).
    - 서로 다른 교정값이 섞여 있으면(예: 성경식 "예레미야" vs 현대 인명
      "제러마이아"처럼 같은 원어에 대해 등재된 관례 자체가 갈리는 경우),
      텍스트만으로는 어느 쪽인지 판단할 수 없고 실제 영상 발음을 들어야
      하므로 첫 번째 후보를 적용하되 항상 "확인 필요"로 표시한다.
    """
    matches = []  # (segment, item)
    for item in search_kornorms(token):
        correct = item.get("korean_mark")
        if not correct:
            continue
        segment = _closest_segment(token, correct)
        if segment != token:
            matches.append((segment, item))

    if not matches:
        return None, False, None

    distinct_segments = {segment for segment, _ in matches}
    if len(distinct_segments) == 1:
        return matches[0][0], False, None

    segment, item = matches[0]
    context = (
        f"{item.get('srclang_mark')} -> {item.get('korean_mark')} "
        f"(그 외 {len(distinct_segments) - 1}개의 다른 표기가 등재되어 있음)"
    )
    return segment, True, context


# ---------------------------------------------------------------------------
# 순화어(다듬은 말) API + 정적 목록 통합 조회
# ---------------------------------------------------------------------------

_PURIFIED_API_CACHE: dict[str, str] | None = None


def get_purified_terms() -> dict[str, str]:
    """온용어 API에서 "다듬은 말"을 동적으로 조회하고, 정적 목록과 통합한다.

    API가 실패하면 기존 정적 목록(PURIFIED_TERMS)으로 fallback한다.
    서버 프로세스가 살아있는 동안 API 결과를 캐시해 반복 조회를 줄인다.
    """
    global _PURIFIED_API_CACHE
    from subtitle_corrector.common_errors import PURIFIED_TERMS

    if _PURIFIED_API_CACHE is not None:
        merged = dict(PURIFIED_TERMS)
        merged.update(_PURIFIED_API_CACHE)
        return merged

    api_terms: dict[str, str] = {}
    try:
        results = search_onyongeo("", glossary_type="다듬은 말")
        for item in results:
            word = item.get("word", "")
            # 온용어 응답에서 word는 "표제어^의존형"처럼 캐럿이 포함될 수 있음
            # -> 캐럿 앞부분만 추출
            clean_word = word.split("^")[0] if "^" in word else word
            if clean_word:
                # "다듬은 말"의 경우 word가 이미 순화 대상(원래 표현),
                # glossary나 definition에서 순화어(새 표현)를 찾아야 함
                # 하지만 온용어 API의 "다듬은 말"은 표제어=순화 대상,
                # 대역어(translation) 또는 정의에서 순화 결과를 제공
                translation = item.get("translation", "")
                if translation:
                    api_terms[clean_word] = translation
    except Exception:
        pass

    _PURIFIED_API_CACHE = api_terms
    merged = dict(PURIFIED_TERMS)
    merged.update(api_terms)
    return merged
