"""국립국어원 표준국어대사전 / 우리말샘 오픈API 연동.

조회 함수들에 @lru_cache를 달아 같은 단어를 반복 조회하지 않게 한다(자막에는
"그리고", "저는" 같은 흔한 단어가 반복되므로 실제 API 호출 수가 크게 줄어든다).
이건 §5의 "국립국어원 API에 최대한 의존" 원칙과 충돌하지 않는다 — 매번 최신
데이터를 받아오는 대신 잠깐(서버 프로세스가 살아있는 동안) 같은 답을 재사용
하는 것뿐이고, 로컬에 사전을 통째로 복제해 규정 개정 추적 부담을 떠안는
것과는 다르다. 서버를 재시작하면 캐시도 비워진다.
"""

import difflib
import os
from functools import lru_cache

import requests
from dotenv import load_dotenv

load_dotenv()

STDICT_API_KEY = os.getenv("STDICT_API_KEY")
OPENDICT_API_KEY = os.getenv("OPENDICT_API_KEY")
KORNORMS_API_KEY = os.getenv("KORNORMS_API_KEY")

STDICT_URL = "https://stdict.korean.go.kr/api/search.do"
OPENDICT_URL = "https://opendict.korean.go.kr/api/search"
OPENDICT_VIEW_URL = "https://opendict.korean.go.kr/api/view"
KORNORMS_URL = "https://korean.go.kr/kornorms/exampleReqList.do"


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


def _opendict_item_is_standard(item: dict) -> bool:
    """우리말샘은 이미 알려진 비표준 표기("초코렛", "스노우 체인" 등)도
    하나의 표제어처럼 등재해 두고, 그 뜻풀이 끝에 "⇒규범 표기는 'OO'이다"라고
    정답을 안내한다. 이런 항목은 "표제어가 존재는 하지만 틀린 표기"이므로
    존재 확인 근거로 쓰면 안 된다 — 하나라도 이 안내가 없는 뜻풀이가 있으면
    표준 표기로 본다."""
    return any("규범 표기는" not in (sense.get("definition") or "") for sense in item.get("sense", []))


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
    "존재함"으로 오판하게 된다."""
    stdict_result = search_stdict(query)
    if int(stdict_result.get("channel", {}).get("total", 0)) > 0:
        return True
    opendict_result = search_opendict(query)
    for item in opendict_result.get("channel", {}).get("item", []):
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword == query and _opendict_item_is_standard(item):
            return True
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

    헷갈리는 표현(제57항 동음이의어)이나 순화어처럼 사람이 문맥으로 직접
    판단해야 하는 플래그 항목에 참고 예문을 덧붙여, 번역가가 사전을 따로
    찾아보지 않고도 바로 문맥을 확인할 수 있게 돕기 위함이다. 용례가 없거나
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
