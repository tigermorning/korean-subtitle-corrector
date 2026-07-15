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


def compound_status(word: str) -> str | None:
    """word(붙여 쓴 형태)가 표준국어대사전에 하나의 표제어로 등재되어 있는지
    확인하고, 등재되어 있다면 합성어인지 명사구인지 구분해 돌려준다.

    사전은 합성어를 하이픈으로("노천-카페", 품사 있음), 명사구를 캐럿으로
    ("예방^접종", `pos`가 "품사 없음")로 표시한다. 즉 `pos` 필드만 보면
    구분된다.

    반환값:
    - "합성어": 무조건 붙여 써야 하는 단어 (표제어 자체가 하나의 단어)
    - "명사구": 띄어쓰기가 원칙이지만 붙여 써도 허용되는 구
    - None: 사전에 이 형태로 등재된 표제어가 없음 (판단 근거 없음)
    """
    result = search_stdict(word)
    for item in result.get("channel", {}).get("item", []):
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword == word:
            return "명사구" if item.get("pos") == "품사 없음" else "합성어"
    return None


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
