"""국립국어원 표준국어대사전 / 우리말샘 오픈API 연동"""

import difflib
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
    - 일반 용어: 확인 불필요 (조용히 자동 반영), 맥락 정보 없음
    - 인명·지명: 원지음 표기 원칙에 따라 우선 자동 반영하되, 같은 이름에
      성경식 표기와 현대 인명 표기처럼 서로 다른 관례가 동시에 존재할 수
      있어 실제 발음은 영상을 들어야만 확정할 수 있다 — 그래서 항상
      "확인 필요"로 표시하고, 사람이 리포트에서 바로 판단할 수 있도록
      원어 표기 전체("srclang_mark -> korean_mark")를 맥락으로 함께 준다.
    """
    for item in search_kornorms(token):
        correct = item.get("korean_mark")
        if not correct:
            continue
        segment = _closest_segment(token, correct)
        if segment != token:
            needs_review = item.get("foreign_gubun") != "일반 용어"
            context = f"{item.get('srclang_mark')} -> {correct}" if needs_review else None
            return segment, needs_review, context
    return None, False, None
