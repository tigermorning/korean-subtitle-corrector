"""국립국어원 표준국어대사전 / 우리말샘 / 온용어 / 한국어기초사전 / 지역어 오픈API 연동.

조회 함수들에 @lru_cache를 달아 같은 단어를 반복 조회하지 않게 한다(자막에는
"그리고", "저는" 같은 흔한 단어가 반복되므로 실제 API 호출 수가 크게 줄어든다).
이건 §5의 "국립국어원 API에 최대한 의존" 원칙과 충돌하지 않는다 — 매번 최신
데이터를 받아오는 대신 잠깐(서버 프로세스가 살아있는 동안) 같은 답을 재사용
하는 것뿐이고, 로컬에 사전을 통째로 복제해 규정 개정 추적 부담을 떠안는
것과는 다르다. 서버를 재시작하면 캐시도 비워진다.
"""

import difflib
import os
import re
import xml.etree.ElementTree as ET
from functools import lru_cache

import requests
from dotenv import load_dotenv

from subtitle_corrector.gananda_precedents import check_precedent

load_dotenv()

STDICT_API_KEY = os.getenv("STDICT_API_KEY")
OPENDICT_API_KEY = os.getenv("OPENDICT_API_KEY")
KORNORMS_API_KEY = os.getenv("KORNORMS_API_KEY")
ONYONGEO_KEY = os.getenv("ONYONGEO_KEY")
KRDICT_KEY = os.getenv("KRDICT_KEY")
DIALECT_API_KEY = os.getenv("DIALECT_API_KEY")

STDICT_URL = "https://stdict.korean.go.kr/api/search.do"
OPENDICT_URL = "https://opendict.korean.go.kr/api/search"
OPENDICT_VIEW_URL = "https://opendict.korean.go.kr/api/view"
KORNORMS_URL = "https://korean.go.kr/kornorms/exampleReqList.do"
ONYONGEO_URL = "https://kli.korean.go.kr/term/api/search.do"
KRDICT_URL = "https://krdict.korean.go.kr/api/search"
DIALECT_URL = "https://dialect.korean.go.kr/dialect/openAPI/data"


def _empty_channel() -> dict:
    return {"channel": {"total": 0, "item": []}}


@lru_cache(maxsize=4096)
def search_stdict(query: str) -> dict:
    if not STDICT_API_KEY:
        raise RuntimeError("STDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": STDICT_API_KEY, "q": query, "req_type": "json"}
    try:
        response = requests.get(STDICT_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        # 국립국어원 서버가 느리거나 응답을 안 주는 경우, "찾지 못함"과 똑같이
        # 처리한다 — 이 함수의 판단 결과가 불확실하다는 뜻이므로, 호출부는
        # 이미 "등재 안 됨/판단 근거 불충분"일 때와 같은 경로(확인 플래그)로
        # 자연스럽게 넘어간다. usage_examples()의 기존 처리 방식과 동일한 원칙.
        return _empty_channel()
    # 검색 결과가 없으면 API가 200 상태코드에 빈 본문을 돌려준다.
    if not response.text.strip():
        return _empty_channel()
    return response.json()


@lru_cache(maxsize=4096)
def search_opendict(query: str) -> dict:
    if not OPENDICT_API_KEY:
        raise RuntimeError("OPENDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": OPENDICT_API_KEY, "q": query, "req_type": "json"}
    try:
        response = requests.get(OPENDICT_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return _empty_channel()
    if not response.text.strip():
        return _empty_channel()
    return response.json()


_NONSTANDARD_REDIRECT_MARKERS = ("규범 표기는", "표준 용어는")


def _opendict_item_is_standard(item: dict) -> bool:
    """우리말샘은 이미 알려진 비표준 표기("초코렛", "스노우 체인" 등)도
    하나의 표제어처럼 등재해 두고, 그 뜻풀이 끝에 "⇒규범 표기는 'OO'이다"라고
    정답을 안내한다. 화학·의학 등 전문 용어는 "⇒표준 용어는 'OO'이다"라는
    다른 문구를 쓴다(예: "요오드"⇒"표준 용어는 '아이오딘'이다" — 실사용
    검증으로 발견, "규범 표기는"만 확인하던 코드가 이 문구를 놓치고 있었음).
    이런 항목은 "표제어가 존재는 하지만 틀린 표기"이므로 존재 확인 근거로
    쓰면 안 된다 — 하나라도 이 안내가 없는 뜻풀이가 있으면 표준 표기로 본다.

    다만 "⇒규범 표기는 미확정이다"(예: "쉴더병")는 다른 대안 표기를
    안내하는 게 아니라 국립국어원이 아직 표준 표기를 정하지 못했다는
    뜻이다 — 이 표기 자체가 현재로선 유일하게 등재된 표기이므로, 다른
    대안이 있는 경우("규범 표기는/표준 용어는 'X'이다")와 구분해서 표준으로
    인정한다."""
    for sense in item.get("sense", []):
        definition = sense.get("definition") or ""
        if any(marker in definition for marker in _NONSTANDARD_REDIRECT_MARKERS) and "미확정" not in definition:
            return False
    return True


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


def word_exists(query: str) -> bool:
    """표준국어대사전 또는 우리말샘에 정확히 일치하는 표제어가 있는지 확인.

    표준국어대사전(규범 사전)을 먼저 확인하고, 없으면 우리말샘(개방형 사전)도
    확인한다. 신조어·구어체 표현은 표준국어대사전에는 없지만 우리말샘에는
    등재된 경우가 많아, 우리말샘도 국립국어원 공식 자료인 이상 정답 근거로
    함께 사용한다.

    우리말샘 쪽은 반드시 표제어가 정확히 일치하는지(`_opendict_item_is_standard`로
    비표준 표기 여부까지) 확인한다 — 검색 API가 "스노우"로 조회해도 "스노우
    체인", "스노우맨"처럼 그 단어가 포함된 여러 단어(구)를 함께 돌려주기
    때문에, 총 검색 건수(`total`)만 보면 실제로는 등재되지 않은 단어까지
    "존재함"으로 오판하게 된다.

    두 사전 어디에도 없는 경우, gananda_precedents(온라인가나다 판례 축적본)에
    이 표현에 대한 확인된 판례가 있는지도 마지막으로 확인한다 — 실시간 사전
    데이터가 항상 우선이고, 판례는 사전에 아무 답이 없을 때만 보조로 쓴다.

    표준국어대사전에 표제어가 있어도 곧바로 True를 반환하지 않는다 —
    "요오드"처럼 표준국어대사전 자체엔 비표준 안내가 없지만 우리말샘에는
    "표준 용어는 '아이오딘'이다"라고 새로 갱신된 안내가 있는 경우(전문
    용어 표준화가 표준국어대사전보다 우리말샘에 먼저/추가로 반영된 것으로
    보임)를 놓치게 된다 — 실사용 검증으로 발견됨. 그래서 표준국어대사전에
    있어도 우리말샘에 정확히 일치하는 표제어가 있으면 그 비표준 안내
    여부까지 항상 확인한다."""
    stdict_hit = int(search_stdict(query).get("channel", {}).get("total", 0)) > 0
    opendict_result = search_opendict(query)
    opendict_matches = [
        item
        for item in opendict_result.get("channel", {}).get("item", [])
        if (item.get("word") or "").replace("-", "").replace("^", "") == query
    ]
    # "집"처럼 같은 표제어 아래 여러 동형이의어가 있을 수 있다("집"=거처인
    # 표준 표기 vs "집"=즙의 비표준 표기가 우연히 같은 글자). 하나라도
    # 비표준으로 확인되면 전체를 비표준으로 단정하지 않는다 — 그중 표준으로
    # 확인되는 동형이의어가 하나라도 있으면 그 뜻으로 정상 존재하는 단어로
    # 본다. 반대로, 검색된 동형이의어 전부가 비표준으로 명시되어 있으면
    # (예: "요오드" — 일치하는 항목이 이것 하나뿐이고 그마저 비표준) 표준
    # 국어대사전 등재 여부와 무관하게 비표준으로 판단한다.
    if opendict_matches:
        if any(_opendict_item_is_standard(item) for item in opendict_matches):
            return True
        return False
    if stdict_hit:
        return True
    precedent = check_precedent(query)
    if precedent is not None:
        return precedent
    return False


def compound_status(word: str) -> str | None:
    """word(붙여 쓴 형태)가 표준국어대사전 또는 우리말샘에 하나의 표제어로
    등재되어 있는지 확인하고, 등재되어 있다면 합성어인지 명사구인지 구분해
    돌려준다. 표준국어대사전을 먼저 확인하고, 없으면 우리말샘도 확인한다.

    두 사전 모두 합성어를 하이픈으로("노천-카페"), 명사구를 캐럿으로
    ("예방^접종")로 표시하는 동일한 표기 관례를 쓴다. 표준국어대사전은
    `pos` 필드로도 구분되지만(하이픈 표제어는 `pos` 있음, 캐럿 표제어는
    `pos: "품사 없음"`), 우리말샘 검색 결과는 표제어 단위 `pos`가 없어
    하이픈/캐럿 표기 자체로만 판단한다 — 구분자가 전혀 없는 표제어는
    합성어인지 단순 일치인지 애매하므로 안전하게 판단을 보류한다(None).

    반환값:
    - "합성어": 무조건 붙여 써야 하는 단어 (표제어 자체가 하나의 단어)
    - "명사구": 띄어쓰기가 원칙이지만 붙여 써도 허용되는 구
    - None: 두 사전 어디에도 이 형태로 등재된 표제어가 없거나 판단 근거가 불충분함
    """
    result = search_stdict(word)
    for item in result.get("channel", {}).get("item", []):
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword == word:
            return "명사구" if item.get("pos") == "품사 없음" else "합성어"

    opendict_result = search_opendict(word)
    for item in opendict_result.get("channel", {}).get("item", []):
        raw_word = item.get("word") or ""
        headword = raw_word.replace("-", "").replace("^", "")
        if headword != word or not _opendict_item_is_standard(item):
            continue
        if "-" in raw_word:
            return "합성어"
        if "^" in raw_word:
            return "명사구"
    return None


def _opendict_examples_for_target(target_code) -> list[str]:
    """우리말샘 상세보기(view) API로 target_code(뜻풀이 하나)에 딸린 실제
    용례 문장들을 가져온다. 예문의 {중괄호} 강조 표시는 벗겨서 돌려준다."""
    if not OPENDICT_API_KEY:
        raise RuntimeError("OPENDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": OPENDICT_API_KEY, "method": "target_code", "q": target_code, "req_type": "json"}
    response = requests.get(OPENDICT_VIEW_URL, params=params, timeout=10)
    response.raise_for_status()
    if not response.text.strip():
        return []
    data = response.json()
    sense_info = data.get("channel", {}).get("item", {}).get("senseInfo", {})
    return [
        example["example"].replace("{", "").replace("}", "")
        for example in sense_info.get("example_info", [])
        if example.get("example")
    ]


def usage_examples(word: str, limit: int = 2) -> list[str]:
    """우리말샘에서 word와 정확히 일치하는 표제어의 실제 용례(예문)를 가져온다.

    순화어처럼 사람이 문맥으로 직접 판단해야 하는 플래그 항목에 참고 예문을
    덧붙여, 번역가가 사전을 따로 찾아보지 않고도 바로 문맥을 확인할 수 있게
    돕기 위함이다. 용례가 없거나
    조회에 실패해도 플래그 판단 자체에는 영향이 없어야 하므로, 이 경우 빈
    리스트만 돌려준다."""
    try:
        result = search_opendict(word)
        for item in result.get("channel", {}).get("item", []):
            headword = (item.get("word") or "").replace("-", "").replace("^", "")
            if headword != word:
                continue
            for sense in item.get("sense", []):
                target_code = sense.get("target_code")
                if not target_code:
                    continue
                examples = _opendict_examples_for_target(target_code)
                if examples:
                    return examples[:limit]
    except (RuntimeError, requests.RequestException, ValueError):
        return []
    return []


def registered_ending(candidate: str) -> str | None:
    """candidate가 표준국어대사전/우리말샘에 "-candidate" 형태(어간·선어말
    어미 등에 붙는 접미형 표제어 — 어미·조사·접사가 공통으로 쓰는 표기
    관례)로 정확히 등재되어 있으면 그 표제어(하이픈 포함)를 돌려준다.

    kiwi는 "있잖아"("있"+"지"+"않"+"아"), "없다잖나"("없다"+"고"+"하"+"지"
    +"않"+"나")처럼 압축된 구어체 표현을 내부적으로 여러 형태소로 억지로
    분해하다가, 그 형태소들의 위치가 서로 겹치거나 길이가 0인 등 스스로도
    확신 없는 재구성을 만들어낸다(사용자 지적: "kiwi는 참고일 뿐, 사전의
    표제어와 용례를 기준으로 해야 한다"). 이런 압축형 자체가 이미 사전에
    하나의 표제어로 등재되어 있는 경우(예: "-잖다", "-잖아", "-거든",
    "-ㄹ걸")는, kiwi의 내부 형태소 분해 결과와 무관하게 그 표제어 등재
    사실 자체를 근거로 삼아 "이 뒤에는 공백을 넣지 않는다"고 판단할 수
    있다."""
    for search in (search_stdict, search_opendict):
        result = search(candidate)
        for item in result.get("channel", {}).get("item", []):
            if (item.get("word") or "") == f"-{candidate}":
                return item["word"]
    return None


@lru_cache(maxsize=4096)
def search_kornorms(keyword: str) -> list[dict]:
    """외래어·로마자 표기 용례를 조회한다 (한국어 어문 규범 Open API).

    검색어가 이미 알려진 잘못된 표기(relate_mark_o)와 일치해도, 그 잘못된
    표기가 딸려있는 정답 항목을 찾아준다.
    """
    if not KORNORMS_API_KEY:
        raise RuntimeError("KORNORMS_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {
        "serviceKey": KORNORMS_API_KEY,
        "pageNo": 1,
        "numOfRows": 10,
        "langType": "0003",  # 외래어
        "searchKeyword": keyword,
        "searchEquals": "equal",
        "resultType": "json",
    }
    try:
        response = requests.get(KORNORMS_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        # search_stdict/search_opendict와 같은 원칙: 조회 실패는 "등재된
        # 표기 없음"과 동일하게 처리해 loanword_fix()가 자동 반영 없이
        # 넘어가게 한다(원문 그대로 유지, 크래시 대신 안전하게 무처리).
        return []
    return data.get("response", {}).get("items", []) or []


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
# 온용어(K-term) API — "다듬은 말", "표준 전문용어" 등 조회
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def search_onyongeo(query: str, glossary_type: str = "다듬은 말") -> list[dict]:
    """온용어(K-term) API에서 query를 검색한다.

    glossary_type으로 용어집 종류를 필터링할 수 있다:
    - "다듬은 말": 일반 순화어 (기본값)
    - "표준 전문용어": 전문 분야 표준 용어
    - "다듬을 말": 추후 순화 예정인 표현
    - "일치어": 동의어 관계의 표준 표기

    반환값: [{"word": "표제어", "definition": "정의", "glossary": "용어집 이름",
             "translation": "대역어", "use_ex": "사용 예시", ...}, ...]
    """
    if not ONYONGEO_KEY:
        return []
    params = {
        "key": ONYONGEO_KEY,
        "apiSearchWord": query,
        "start": 1,
        "num": 10,
        "sort": "wt",
    }
    try:
        response = requests.get(ONYONGEO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return []
    if not data:
        return []
    channel = data.get("channel", {})
    # glossary_type 필터: 특정 용어집만 선택
    results = []
    for return_obj in channel.get("return_object", []):
        if return_obj.get("returnCode") != 1:
            continue
        for item in return_obj.get("resultlist", []):
            item_glossary = item.get("glossary", "")
            if glossary_type and glossary_type not in item_glossary:
                continue
            results.append(item)
    return results


# ---------------------------------------------------------------------------
# 한국어기초사전 API — 초급자 대상 사전 (뜻풀이·용례·발음)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def search_krdict(query: str) -> dict:
    """한국어기초사전 API에서 query를 검색한다.

    반환값: {"channel": {"total": int, "items": [{"word": str, "definition": str,
             "example": str, "pronunciation": str, "pos": str, "word_grade": str}, ...]}}
    """
    if not KRDICT_KEY:
        return {"channel": {"total": 0, "items": []}}
    params = {
        "key": KRDICT_KEY,
        "q": query,
        "start": 1,
        "num": 10,
        "sort": "dict",
        "part": "word",
    }
    try:
        response = requests.get(KRDICT_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return {"channel": {"total": 0, "items": []}}
    if not response.text.strip():
        return {"channel": {"total": 0, "items": []}}
    # XML 파싱
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return {"channel": {"total": 0, "items": []}}
    total_el = root.find("total")
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    items = []
    for item_el in root.findall("item"):
        word_el = item_el.find("word")
        pos_el = item_el.find("pos")
        pron_el = item_el.find("pronunciation")
        grade_el = item_el.find("word_grade")
        sense_el = item_el.find("sense")
        defn_el = sense_el.find("definition") if sense_el is not None else None
        ex_el = sense_el.find("example") if sense_el is not None else None
        items.append({
            "word": word_el.text if word_el is not None else "",
            "pos": pos_el.text if pos_el is not None else "",
            "pronunciation": pron_el.text if pron_el is not None else "",
            "word_grade": grade_el.text if grade_el is not None else "",
            "definition": defn_el.text if defn_el is not None else "",
            "example": ex_el.text if ex_el is not None else "",
        })
    return {"channel": {"total": total, "items": items}}


# ---------------------------------------------------------------------------
# 지역어 종합 정보 API — 방언↔표준어 대응 조회
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def search_dialect(query: str) -> list[dict]:
    """지역어 종합 정보 API에서 query를 검색한다.

    반환값: [{"word": "지역어", "std_word": "대응 표준어", "region": "시도 코드",
             "city": "시군구", "source": "출처", "year": "조사 연도"}, ...]
    """
    if not DIALECT_API_KEY:
        return []
    params = {
        "apiKey": DIALECT_API_KEY,
        "searchWord": query,
    }
    try:
        response = requests.get(DIALECT_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return []
    if not data:
        return []
    if data.get("returnCode") != 60000:
        return []
    results = []
    for item in data.get("resultList", []):
        results.append({
            "word": item.get("dltTp", ""),
            "std_word": item.get("stdTp", ""),
            "region": item.get("sidoCd", ""),
            "city": item.get("sigunguNm", ""),
            "source": item.get("source", ""),
            "year": item.get("basisYear", ""),
        })
    return results


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


# ---------------------------------------------------------------------------
# 사투리 마커 — 지역별 특징적 어미·조사·어휘 패턴
# ---------------------------------------------------------------------------

DIALECT_MARKERS: dict[str, dict[str, list[str]]] = {
    "경상도": {
        "어미": ["스라", "나요", "라요", "이까", "으이라", "니", "아이가", "monton"],
        "조사": ["한테루", "한테가", "한테서"],
        "어휘": ["마이시", "예뿌다", "기rab다", "좋다", "아이가", "모려"],
    },
    "제주도": {
        "어미": ["수다", "주와", "수과", "ᄒᆞ다", "ありが다", "이우다", "라버"],
        "조사": ["한테가", "한데서"],
        "어휘": ["하르방", "마르", " Ấ리", "꼬닥", "phins"],
    },
    "전라도": {
        "어미": ["이", "라", "재", "네", "수룩", "래"],
        "조사": ["한테랑", "한테나"],
        "어휘": ["아주머니", "총각", "여라자"],
    },
    "충청도": {
        "어미": ["지", "제", "쥬", "유", "잉"],
        "어휘": ["adio", "기냥", "거시기"],
    },
}

# 양방향 사투리 변환 맵 — {사투리표현: 표준어} 형태
# 어미·조사·어휘를 구분하지 않고 하나의 딕셔너리로 관리
DIALECT_TO_STANDARD: dict[str, dict[str, str]] = {
    "경상도": {
        "아이가": "그래",
        "마이시": "많이",
        "예뿌다": "예쁘다",
        "기rab다": "기르다",
        "모려": "몰라",
        "한테루": "한테",
        "한테가": "한테",
        "나요": "나요",
        "라요": "라요",
        "이까": "이야",
        "으이라": "이야",
        "스라": "지",
    },
    "제주도": {
        "하르방": "아버지",
        "마르": "배고프다",
        "꼬닥": "꼭",
        "ᄒᆞ다": "하다",
        "수다": "것이다",
        "주와": "줄을",
        "이우다": "이르다",
    },
    "전라도": {
        "수룩": "금세",
        "래": "라고",
        "아주머니": "아줌마",
        "총각": "청년",
        "여라자": "여자",
    },
    "충청도": {
        "거시기": "저것",
        "기냥": "그냥",
        "adio": "아이고",
    },
}

# 역방향: 표준어→사투리 변환용 (각 지역별로 어떤 표준어를 어떤 사투리로 바꿀 수 있는지)
STANDARD_TO_DIALECT: dict[str, dict[str, str]] = {}
for _region, _map in DIALECT_TO_STANDARD.items():
    STANDARD_TO_DIALECT[_region] = {v: k for k, v in _map.items()}

# 사투리 마커를 정규표현식으로 변환 (미리 컴파일)
_DIALECT_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _get_dialect_pattern(region: str) -> re.Pattern:
    """특정 지역의 사투리 마커를 하나의 정규표현식으로 반환."""
    if region in _DIALECT_PATTERN_CACHE:
        return _DIALECT_PATTERN_CACHE[region]
    markers = DIALECT_MARKERS.get(region, {})
    all_markers: list[str] = []
    for category in ("어미", "조사", "어휘"):
        all_markers.extend(markers.get(category, []))
    if not all_markers:
        pattern = re.compile("(?!x)x")  # 아무것도 매칭 안 되는 패턴
    else:
        escaped = [re.escape(m) for m in sorted(all_markers, key=len, reverse=True)]
        pattern = re.compile("|".join(escaped))
    _DIALECT_PATTERN_CACHE[region] = pattern
    return pattern


def detect_dialect_ratio(text: str, region: str) -> float:
    """text에서 특정 지역 사투리 마커의 비율(0.0~1.0)을 반환.

    텍스트의 어미·조사·어휘 영역에서 사투리 패턴이 차지하는 비율을 계산한다.
    0.0이면 사투리 없음, 1.0이면 전부 사투리."""
    pattern = _get_dialect_pattern(region)
    matches = pattern.findall(text)
    if not matches:
        return 0.0
    # 매칭된 문자열의 총 길이를 텍스트 길이로 나눔
    total_len = sum(len(m) for m in matches)
    return min(total_len / max(len(text), 1), 1.0)


def detect_speaker_dialect(texts: list[str]) -> str | None:
    """여러 대사 텍스트에서 사투리 종류를 자동 감지.

    각 지역별 마커 비율을 계산해, 임계값(0.15) 이상인 지역 중 가장 높은 비율의
    지역을 돌려준다. 어떤 지역도 임계값에 도달하지 못하면 None을 돌려준다.

    반환값: "경상도", "제주도", "전라도", "충청도" 중 하나 또는 None
    """
    if not texts:
        return None
    combined = " ".join(texts)
    best_region = None
    best_ratio = 0.0
    threshold = 0.15
    for region in DIALECT_MARKERS:
        ratio = detect_dialect_ratio(combined, region)
        if ratio >= threshold and ratio > best_ratio:
            best_ratio = ratio
            best_region = region
    return best_region


def convert_dialect(text: str, region: str, direction: str) -> str:
    """사투리↔표준어 양방향 변환.

    direction:
        - "to_standard": 사투리→표준어 (예: "아이가" → "그래")
        - "to_dialect": 표준어→사투리 (예: "그래" → "아이가")

    변환 규칙:
        - 긴 표현을 먼저 치환 (예: "한테루"를 "한테"보다 먼저)
        - 이미 변환된 부분은 재변환하지 않음
        - 단어 경계 고려 없이 문자열 치환 (사투리는 어미·조사에 붙는 경우가 많음)

    반환값: 변환된 텍스트
    """
    if direction == "to_standard":
        mapping = DIALECT_TO_STANDARD.get(region, {})
    elif direction == "to_dialect":
        mapping = STANDARD_TO_DIALECT.get(region, {})
    else:
        return text

    if not mapping:
        return text

    result = text
    # 긴 표현부터 치환 (이중 치환 방지)
    for old, new in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(old, new)
    return result
