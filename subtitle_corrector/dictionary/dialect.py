"""사투리 표지 사전과 지역 판정.

국립국어원 지역어 오픈API(`clients.search_dialect`)는 서버측 500 장애가 이어져
실질적으로 쓸 수 없다(`docs/BACKLOG.md` 5번). 그래서 이 파일의 표지 사전이
현재 사투리 판정의 유일한 근거다.
"""

import re

# ---------------------------------------------------------------------------
# 사투리 마커 — 지역별 특징적 어미·조사·어휘 패턴
# ---------------------------------------------------------------------------

# 2026-08-03 전수 감사로 대부분을 지웠다. 아래 "사투리 표 감사" 주석 참고.
# 남긴 것은 우리말샘에서 방언 표제어로 확인되는 것뿐이다.
DIALECT_MARKERS: dict[str, dict[str, list[str]]] = {
    "경상도": {},
    "제주도": {
        # 우리말샘: "'할아버지'의 방언" (2026-08-03 확인)
        "어휘": ["하르방"],
    },
    "전라도": {},
    "충청도": {
        # 우리말샘: "'그냥'의 방언" (2026-08-03 확인)
        "어휘": ["기냥"],
    },
}


# 사투리 표 감사 (2026-08-03) — 왜 표가 이렇게 작은가
# ---------------------------------------------------------------------------
# 이 표에 있던 27개 항목을 우리말샘으로 전수 조회한 결과, **검증되는 것이 3개뿐**
# 이었다. 나머지는 세 부류였다.
#   ① 한글이 아닌 쓰레기 항목: "기rab다", "adio", "monton", "ありが다", "phins", " Ấ리"
#   ② 뜻이 틀린 항목: "하르방"->"아버지"(우리말샘은 '할아버지'의 방언),
#      "이까"->"이야"('오징어'의 방언), "모려"->"몰라"(표제어 뜻은 '계략'),
#      "마르"->"배고프다"(화산 지형), "수다"->"것이다"(말수가 많음)
#   ③ 표준어를 사투리로 등록한 항목: "아주머니"->"아줌마", "총각"->"청년",
#      "래"->"라고", "거시기"(표준 대명사)
#
# 왜 지웠나: 이 표는 감지용만이 아니라 **텍스트를 실제로 바꾸는** to_standard
# 모드의 근거였고, 단어 경계 없이 문자열을 치환한다. 그래서 전라도 화자에게
# to_standard를 걸면 '그래 노래를 불렀다'가 '그라고 노라고를 불렀다'로, 제주도
# 화자면 '하르방이 왔다'가 '아버지이 왔다'로 조용히 깨졌다. 근거가 없는 표로
# 원고를 고치는 것은 이 프로젝트의 최우선 원칙("확률적 추측이 아닌 권위 있는
# 규범 근거")과 정면으로 충돌한다.
#
# 되살리려면: 항목마다 우리말샘 방언 표제어(뜻풀이가 "'X'의 방언")로 확인한 뒤
# 근거 주석과 함께 넣는다. 표준어->사투리 역방향은 지금 자동으로 만들 수 없다 —
# 지역어 종합 정보 API는 서버측 500 장애(BACKLOG 5번)이고, 우리말샘 뜻풀이 검색
# (advanced target=뜻풀이)으로 "'빨리'의 방언"을 찾아봤지만 0건이었다.
DIALECT_TO_STANDARD: dict[str, dict[str, str]] = {
    "경상도": {},
    "제주도": {
        # 우리말샘: "'할아버지'의 방언" (2026-08-03 확인). 기존 표의 '아버지'는 오류였다.
        "하르방": "할아버지",
    },
    "전라도": {},
    "충청도": {
        # 우리말샘: "'그냥'의 방언" (2026-08-03 확인)
        "기냥": "그냥",
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
