"""국립국어원 표준국어대사전 / 우리말샘 오픈API 연동"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

STDICT_API_KEY = os.getenv("STDICT_API_KEY")
OPENDICT_API_KEY = os.getenv("OPENDICT_API_KEY")
KORNORMS_API_KEY = os.getenv("KORNORMS_API_KEY")

STDICT_URL = "https://stdict.korean.go.kr/api/search.do"
OPENDICT_URL = "https://opendict.korean.go.kr/api/search"
KORNORMS_URL = "https://korean.go.kr/kornorms/exampleReqList.do"


def _empty_channel() -> dict:
    return {"channel": {"total": 0, "item": []}}


def search_stdict(query: str) -> dict:
    if not STDICT_API_KEY:
        raise RuntimeError("STDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": STDICT_API_KEY, "q": query, "req_type": "json"}
    response = requests.get(STDICT_URL, params=params, timeout=10)
    response.raise_for_status()
    # 검색 결과가 없으면 API가 200 상태코드에 빈 본문을 돌려준다.
    if not response.text.strip():
        return _empty_channel()
    return response.json()


def search_opendict(query: str) -> dict:
    if not OPENDICT_API_KEY:
        raise RuntimeError("OPENDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": OPENDICT_API_KEY, "q": query, "req_type": "json"}
    response = requests.get(OPENDICT_URL, params=params, timeout=10)
    response.raise_for_status()
    if not response.text.strip():
        return _empty_channel()
    return response.json()


def word_exists(query: str) -> bool:
    """표준국어대사전에 정확히 일치하는 표제어가 있는지 확인"""
    result = search_stdict(query)
    channel = result.get("channel", {})
    return int(channel.get("total", 0)) > 0


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
    response = requests.get(KORNORMS_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data.get("response", {}).get("items", []) or []


def known_loanword_fix(token: str) -> str | None:
    """token이 국립국어원이 명시적으로 틀렸다고 표시한 외래어 표기(relate_mark_o에
    '(X)'로 표시)와 일치하면, 공식 정답(korean_mark)을 돌려준다.
    token 자체가 이미 맞는 표기이거나 kornorms에 없는 단어면 None을 돌려준다.
    """
    for item in search_kornorms(token):
        correct = item.get("korean_mark")
        if correct and correct != token:
            return correct
    return None
