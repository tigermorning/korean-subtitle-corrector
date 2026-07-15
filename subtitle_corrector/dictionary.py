"""국립국어원 표준국어대사전 / 우리말샘 오픈API 연동"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

STDICT_API_KEY = os.getenv("STDICT_API_KEY")
OPENDICT_API_KEY = os.getenv("OPENDICT_API_KEY")

STDICT_URL = "https://stdict.korean.go.kr/api/search.do"
OPENDICT_URL = "https://opendict.korean.go.kr/api/search"


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
