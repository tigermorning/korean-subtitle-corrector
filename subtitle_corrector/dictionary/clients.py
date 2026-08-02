"""국립국어원 오픈API 클라이언트 — 요청을 보내고 응답을 그대로 돌려주는 계층.

여기서는 **판정하지 않는다**. 응답을 보고 무엇을 결론지을지는 `headwords.py`·
`terms.py`가 정한다. `docs/DESIGN_PRINCIPLES.md` 원리 4(조회 로직 버그)는
거의 전부 그 판정 쪽에서 나므로, 통신과 판정을 한 파일에 섞지 않는다.

조회 함수들에 @lru_cache를 달아 같은 단어를 반복 조회하지 않게 한다(자막에는
"그리고", "저는" 같은 흔한 단어가 반복되므로 실제 API 호출 수가 크게 줄어든다).
이건 §5의 "국립국어원 API에 최대한 의존" 원칙과 충돌하지 않는다 — 매번 최신
데이터를 받아오는 대신 잠깐(서버 프로세스가 살아있는 동안) 같은 답을 재사용
하는 것뿐이고, 로컬에 사전을 통째로 복제해 규정 개정 추적 부담을 떠안는
것과는 다르다. 서버를 재시작하면 캐시도 비워진다.
"""

import os
import xml.etree.ElementTree as ET
from functools import lru_cache
import requests
from dotenv import load_dotenv

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
