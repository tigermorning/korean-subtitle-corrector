"""사투리 표지 사전과 지역 판정.

국립국어원 지역어 오픈API(`clients.search_dialect`)는 서버측 500 장애가 이어져
실질적으로 쓸 수 없다(`docs/BACKLOG.md` 5번). 그래서 이 파일의 표지 사전이
현재 사투리 판정의 유일한 근거다.
"""

import re

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


# 여러 지역 노인 말투에 공통으로 나타나는 어미·조사 사투리 → 표준어 대응.
# 지역별 어휘 사투리(위 DIALECT_TO_STANDARD)와 달리 특정 지역에 국한되지 않는
# 규칙적 음운 변화라, 사투리로 지정된 화자면 지역과 무관하게 to_standard에서
# 함께 적용한다. 예: 비하믄→비하면, 먹으믄→먹으면, 이라믄서→이라면서(믄→면),
# 맛나겄냐→맛나겄냐(겄→겠). 표준어→사투리(역방향)에는 넣지 않는다 — '면'→'믄'을
# 문자열로 치환하면 '화면·국수 면'처럼 무관한 '면'까지 바뀌기 때문이다.
_COMMON_DIALECT_ENDINGS_TO_STANDARD: dict[str, str] = {
    "믄": "면",
    "겄": "겠",
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
        # 지역 어휘 사투리 + 공통 어미 사투리(믄→면, 겄→겠)를 함께 적용한다.
        mapping = {**DIALECT_TO_STANDARD.get(region, {}), **_COMMON_DIALECT_ENDINGS_TO_STANDARD}
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
