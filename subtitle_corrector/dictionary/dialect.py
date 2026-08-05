"""사투리 표지 사전과 지역 판정.

국립국어원 지역어 오픈API(`clients.search_dialect`)는 서버측 500 장애가 이어져
실질적으로 쓸 수 없다(`docs/BACKLOG.md` 5번). 그래서 이 파일의 표지 사전이
현재 사투리 판정의 유일한 근거다.
"""

import re

# ---------------------------------------------------------------------------
# 사투리 마커 — 지역별 특징적 어미·조사·어휘 패턴
# ---------------------------------------------------------------------------

# 2026-08-03 전수 감사로 대부분을 지웠고(아래 "사투리 표 감사" 주석), 2026-08-05에
# 우리말샘 근거로 다시 채웠다(`docs/BACKLOG.md` 25번).
#
# **넣는 조건**: 우리말샘 표제어의 뜻풀이가 "'X'의 방언"이고, 사전 내용 API의
# `senseInfo.region_info`가 그 지역을 직접 밝힐 것. 지역은 사람이 추측하지 않고
# 이 필드가 정한다 — 지역을 짐작해 넣는 것이 §52 사고의 출발점이었다.
#
# 감지(`detect_dialect_ratio`)에는 **뜻이 갈리는 낱말도 넣는다.** 어느 뜻이든 그
# 지역 방언이라는 사실 자체는 맞으므로 화자 판별 근거로는 쓸 수 있다. 반면
# 아래 `DIALECT_TO_STANDARD`(텍스트를 실제로 바꾸는 표)에는 뜻이 하나로 확정되는
# 것만 넣는다.
#
# 지역 키는 네 개뿐이라 `region_info`가 강원·경기·평안·함경·황해로만 나오는 낱말은
# 넣지 않았다. 확인한 34개 중 그 지역에만 속하는 것은 없었다(강원 낱말은 전부
# 경상·충청과 겹친다).
DIALECT_MARKERS: dict[str, dict[str, list[str]]] = {
    "경상도": {
        # region_info에 경상/경남/경북이 든 것. 2026-08-05 우리말샘 확인.
        "어휘": [
            "정구지",  # '부추'의 방언 (경상·전북·충청)
            "머스마",  # '사내아이'의 방언 (강원·경상·전북·충청)
            "가시나",  # '계집아이'의 방언 (경상·전남)
            "단디",  # '단단히'의 방언 (경상)
            "억수로",  # '대단히'의 방언 (경상)
            "쪼매",  # '조금'의 방언 (강원·경상·전남·충북)
            "언나",  # '어린아이'의 방언 (강원·경상·평안·함남)
            "디비다",  # '뒤지다'/'뒤집다'의 방언 (경상·함경)
            "문디",  # '문둥이'/'달팽이'의 방언 (경상·경북)
            "새첩다",  # '예쁘다'의 방언 (경남)
            "보이소",  # '여보시오'의 방언 (경남)
            "오메",  # '엄마'/'어머'의 방언 (경북·전라/경남)
            "마카",  # '말끔'/'모두'/'참외'의 방언 (강원·경상/강원·경북/전남)
            "지둘리다",  # '기다리다'의 방언 (경남)
            "냅두다",  # '놓아두다'의 방언 (경북·전라)
            "할망",  # '할머니'/'딴전'의 방언 (경북·제주/전남)
            "아방",  # '아욱'/'아버지'의 방언 (경북/제주)
            "어멍",  # '어머니'/'엄살'의 방언 (경남·제주/경남)
            "기여",  # '기어이'/'그래'의 방언 (경남/제주)
            "맹키로",  # '처럼'의 방언 (경남·전남)
            "겁나",  # '굉장히'의 방언 (경상·전남)
        ],
    },
    "제주도": {
        "어휘": [
            "하르방",  # '할아버지'의 방언 (제주)
            "할망",  # '할머니'의 방언 (경북·제주)
            "아방",  # '아버지'의 방언 (제주)
            "어멍",  # '어머니'의 방언 (경남·제주)
            "폭낭",  # '팽나무'의 방언 (제주)
            "지꺼지다",  # '기뻐하다'의 방언 (제주)
            "보말",  # '보말고둥'의 방언 (제주)
            "조베기",  # '수제비'의 방언 (제주)
            "기냥",  # '그냥'의 방언 (강원·경기·전남·제주·황해)
            "이녁",  # '자기'의 방언 (전남·제주)
            "기여",  # '그래'의 방언 (제주)
        ],
    },
    "전라도": {
        "어휘": [
            "깔끄막",  # '벼랑'의 방언 (전남)
            "포도시",  # '간신히'의 방언 (전라)
            "싸목싸목",  # '천천히'의 방언 (전남)
            "야그",  # '이야기'의 방언 (전남)
            "겁나",  # '굉장히'의 방언 (경상·전남)
            "맹키로",  # '처럼'의 방언 (경남·전남)
            "이녁",  # '자기'의 방언 (전남·제주)
            "냅두다",  # '놓아두다'의 방언 (경북·전라)
            "오메",  # '엄마'의 방언 (경북·전라)
            "가시나",  # '계집아이'의 방언 (경상·전남)
            "기냥",  # '그냥'의 방언 (강원·경기·전남·제주·황해)
            "쪼매",  # '조금'의 방언 (강원·경상·전남·충북)
            "마카",  # '참외'의 방언 (전남)
        ],
    },
    "충청도": {
        "어휘": [
            "워디",  # '어디'의 방언 (강원·충남)
            "정구지",  # '부추'의 방언 (경상·전북·충청)
            "머스마",  # '사내아이'의 방언 (강원·경상·전북·충청)
            "쪼매",  # '조금'의 방언 (강원·경상·전남·충북)
        ],
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
# 2026-08-05 다시 채웠다(`docs/BACKLOG.md` 25번). 이 표는 텍스트를 **실제로 바꾸므로**
# 감지용 표(`DIALECT_MARKERS`)보다 조건이 하나 더 붙는다 — **우리말샘에서 그 낱말의
# 뜻이 하나로 확정될 것.** 방언 뜻이 둘 이상이거나 방언 아닌 뜻이 함께 있으면
# 넣지 않는다. 확인한 34개 중 18개만 이 조건을 통과했다.
#
# 걸러낸 16개와 그 이유(그대로 넣었으면 전부 오교정이 됐다):
#   뜻이 갈린다  마카(말끔/모두/참외) 디비다(뒤지다/뒤집다) 문디(문둥이/달팽이)
#                오메(엄마/어머) 할망(할머니/딴전) 아방(아버지/아욱) 어멍(어머니/엄살)
#                기여(기어이/그래)
#   방언 아닌 뜻이 함께 있다
#                이녁(표준 이인칭 대명사) 워디(마소에게 왼쪽으로 돌라는 소리)
#                단디('단지'의 옛말) 겁나('겁나하다'의 어근) 보말(아름다운 버선)
#                마커(필기구 marker) 야그(YAG, 이트륨알루미늄 산화물) 가시나(노래 제목)
#
# 남은 한계: 용언은 기본형만 바뀐다(`지둘리다` -> `기다리다`). 활용형(`지둘려`)은
# 문자열이 달라 걸리지 않는다 — 이 표는 어휘 대조표이지 형태소 규칙이 아니다.
DIALECT_TO_STANDARD: dict[str, dict[str, str]] = {
    "경상도": {
        "정구지": "부추",
        "머스마": "사내아이",
        "억수로": "대단히",
        "쪼매": "조금",
        "언나": "어린아이",
        "새첩다": "예쁘다",
        "보이소": "여보시오",
        "지둘리다": "기다리다",
        "냅두다": "놓아두다",
        "맹키로": "처럼",
    },
    "제주도": {
        "하르방": "할아버지",
        "폭낭": "팽나무",
        "지꺼지다": "기뻐하다",
        "조베기": "수제비",
        "기냥": "그냥",
    },
    "전라도": {
        "깔끄막": "벼랑",
        "포도시": "간신히",
        "싸목싸목": "천천히",
        "냅두다": "놓아두다",
        "맹키로": "처럼",
        "기냥": "그냥",
        "쪼매": "조금",
    },
    "충청도": {
        "정구지": "부추",
        "머스마": "사내아이",
        "쪼매": "조금",
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
        result = _replace_with_particle(result, old, new)
    return result


# 받침 유무로 갈리는 조사 이형태. 낱말을 바꾸면 뒤 조사도 함께 바뀐다.
_JOSA_PAIRS = {
    "이": ("이", "가"),
    "가": ("이", "가"),
    "은": ("은", "는"),
    "는": ("은", "는"),
    "을": ("을", "를"),
    "를": ("을", "를"),
    "과": ("과", "와"),
    "와": ("과", "와"),
}


def _has_batchim(syllable: str) -> bool:
    if not syllable:
        return False
    code = ord(syllable[-1])
    if not (0xAC00 <= code <= 0xD7A3):
        return False
    return (code - 0xAC00) % 28 != 0


def _replace_with_particle(text: str, old: str, new: str) -> str:
    """낱말을 바꾸면서 **바로 뒤 조사의 이형태도 맞춘다**.

    `하르방이 왔다`를 그냥 치환하면 `할아버지이 왔다`가 된다(2026-08-05 실측).
    원문의 조사는 바뀌기 전 낱말의 받침에 맞춰져 있으므로 함께 고쳐야 한다.

    조사 뒤가 **한글이 아닐 때만** 바꾼다. `하르방이다`의 '이'는 서술격 조사라
    주격 '이/가'와 다르게 움직이는데, 표면만으로는 갈리지 않는다 — 뒤에 글자가
    이어지면 손대지 않고 원문 형태를 지킨다.
    """
    out = []
    cursor = 0
    while True:
        at = text.find(old, cursor)
        if at == -1:
            out.append(text[cursor:])
            return "".join(out)
        out.append(text[cursor:at])
        out.append(new)
        after = at + len(old)
        josa = text[after : after + 1]
        pair = _JOSA_PAIRS.get(josa)
        tail_is_hangul = _has_batchim(text[after + 1 : after + 2]) or (
            len(text) > after + 1 and 0xAC00 <= ord(text[after + 1]) <= 0xD7A3
        )
        if pair and not tail_is_hangul:
            with_batchim, without_batchim = pair
            out.append(with_batchim if _has_batchim(new[-1:]) else without_batchim)
            after += 1
        cursor = after
