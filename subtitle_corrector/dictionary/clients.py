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
import time
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


# 요청에 **이 프로그램이 무엇인지** 밝힌다(2026-09-01 추가, §79).
#
# 국립국어원 어문 규범 서버(`korean.go.kr/kornorms`)가 도구 기본 User-Agent를 막기
# 시작했다. 실측: `python-requests/…` 403, `curl/…` 403, 이름을 밝힌 UA 200. 키를 빼고
# 보내도 403이라 인증 문제가 아니라 요청 본문을 보기 전에 걸러 내는 차단이다.
#
# **브라우저를 흉내 내지 않는다.** `Mozilla/5.0`으로도 통과하지만 그건 우리가 사람인
# 척하는 것이고, 공공 오픈 API를 정식 키로 부르는 클라이언트가 할 일이 아니다. 프로그램
# 이름과 연락처를 밝히는 쪽이 맞고 그것으로 통과한다 — 서버 관리자가 트래픽을 보고
# 누구인지 알 수 있어야 한다.
#
# 다른 사전 API(표준국어대사전·우리말샘·지역어)는 지금 이 차단이 없지만 같은 기관이
# 운영하므로 한곳에 두고 전부 붙인다. 다음에 같은 일이 생겨도 여기만 고치면 된다.
_HEADERS = {"User-Agent": "korean-subtitle-corrector/1.0 (+https://github.com/tigermorning)"}


STDICT_URL = "https://stdict.korean.go.kr/api/search.do"


# 표준국어대사전 "사전 내용" API. 검색 API가 주지 않는 것을 준다 — 그중 이 도구에
# 쓸모 있는 것은 `norm_info`(그 표기가 왜 그렇게 적히는지, 한글 맞춤법 조항을 든
# 설명문)와 뜻풀이별 용례다.
#
# **`req_type=json`을 주면 본문이 빈 채로 200이 온다**(2026-08-05 실측). 검색 API는
# JSON을 주는데 이쪽만 XML 전용이다. 실패가 아니라 빈 응답으로 오기 때문에, 모르고
# JSON을 요청하면 "등재된 근거가 없다"로 조용히 오해하게 된다.
STDICT_VIEW_URL = "https://stdict.korean.go.kr/api/view.do"


OPENDICT_URL = "https://opendict.korean.go.kr/api/search"


OPENDICT_VIEW_URL = "https://opendict.korean.go.kr/api/view"


KORNORMS_URL = "https://korean.go.kr/kornorms/exampleReqList.do"


ONYONGEO_URL = "https://kli.korean.go.kr/term/api/search.do"


KRDICT_URL = "https://krdict.korean.go.kr/api/search"


DIALECT_URL = "https://dialect.korean.go.kr/dialect/openAPI/data"


def _empty_channel() -> dict:
    return {"channel": {"total": 0, "item": []}}


# 조회 **시도와 실패 건수**. 조회 실패는 "등재된 표기 없음"과 같은 경로로 흡수하는데
# (크래시보다 안전하다), 그러면 **교정이 조용히 건너뛰어진다** — 2026-08-04에 kornorms가
# DNS 단계에서 안 붙는 동안 '판넬 -> 패널'·'리모콘 -> 리모컨'이 그냥 통과했고, 사용자는
# 교정이 안 된 것을 알 방법이 없었다. 그래서 어느 API가 죽었는지 기록해 리포트에 싣는다.
#
# 이름만 모으지 않고 건수를 세는 이유(2026-08-04 사용자 보고): 우리말샘은 정상인데
# "이 사전이 담당하는 교정은 이번 결과에 반영되지 않았습니다"가 계속 떠서 연결이 끊긴
# 줄 알았다. 실제로는 수천 건 중 한두 건이 순간적으로 실패한 것이었다 — **한 건 실패와
# 전부 불통을 구분하지 못하는 집계**가 문구를 과장하게 만들었다(§62).
_LOOKUP_STATS: dict[str, dict] = {}


def _stats_for(api: str) -> dict:
    return _LOOKUP_STATS.setdefault(
        api, {"attempts": 0, "failures": 0, "queries": [], "streak": 0, "skipped": 0}
    )


def note_lookup_attempt(api: str) -> None:
    """조회를 한 번 시도했다(성공·실패 확정 전)."""
    _stats_for(api)["attempts"] += 1


def note_lookup_failure(api: str, query: str = "") -> None:
    """재시도까지 다 쓰고도 실패했다. `query`는 리포트에 실을 표본이다."""
    stats = _stats_for(api)
    stats["failures"] += 1
    stats["streak"] += 1
    if query and len(stats["queries"]) < 5 and query not in stats["queries"]:
        stats["queries"].append(query)


def failed_lookups() -> list[str]:
    """이번 실행에서 조회에 실패한 API 목록(정렬)."""
    return sorted(api for api, s in _LOOKUP_STATS.items() if s["failures"])


def lookup_stats() -> dict[str, dict]:
    """API별 {attempts, failures, queries}. 리포트 문구가 "일부 실패"와 "전부
    불통"을 가려 말하려면 건수가 필요하다."""
    return {api: dict(s) for api, s in _LOOKUP_STATS.items() if s["failures"]}


def reset_failed_lookups() -> None:
    _LOOKUP_STATS.clear()


class _LookupFailed(Exception):
    """재시도 뒤에도 조회가 실패했다.

    이 예외를 쓰는 이유는 **lru_cache가 예외는 캐시하지 않는다**는 점이다. 실패를
    빈 응답으로 바꿔 돌려주면 그 값이 캐시에 남아, 순간적인 실패 하나가 그 낱말에
    대한 판정을 문서 끝까지(서버 프로세스가 사는 동안 계속) 오염시킨다. 예외로
    올려 보내면 다음 줄에서 같은 낱말을 다시 조회한다."""


# 재시도 대기(초). 국립국어원 API는 수천 건을 연속 조회하는 동안 한두 건이 순간적으로
# 실패한다 — 재시도 없이 실패로 확정하면 리포트가 "사전 불통"을 알린다(§62).
_RETRY_WAITS = (0.4, 1.2)


# **차단기**(circuit breaker). API가 정말로 죽으면 재시도가 독이 된다 — 자막 40줄에
# 조회가 1,119건 나가므로(실측), 한 건에 10초 타임아웃 3번이면 실행이 사실상 멈춘다.
# 연속 실패가 이 수를 넘기면 그 API 조회를 건너뛰고, 그 뒤로는 일정 간격으로만
# 한 번씩 찔러 본다(복구를 놓치지 않기 위해).
_BREAKER_STREAK = 5
_BREAKER_PROBE_EVERY = 20


def _get_json(url: str, params: dict, api: str, timeout: int = 10) -> dict:
    """JSON 조회 + 재시도. 결과가 없으면 빈 dict, 실패 확정이면 `_LookupFailed`.

    응답이 JSON이 아닌 경우(국립국어원 API는 잘못된 검색어에 XML `<error>`를 200으로
    돌려준다 — `'/'`·`'^'` 실측)도 실패로 본다. 전에는 `response.json()`이 그대로
    터져 파이프라인이 멈출 수 있었다.
    """
    note_lookup_attempt(api)
    query = str(params.get("q") or params.get("searchKeyword") or params.get("searchWord") or "")
    stats = _stats_for(api)
    if stats["streak"] >= _BREAKER_STREAK:
        # 차단 중. 일정 간격으로만 한 번 찔러 보고, 그 사이에는 네트워크를 쓰지 않는다.
        if stats["skipped"] < _BREAKER_PROBE_EVERY:
            stats["skipped"] += 1
            note_lookup_failure(api, query)
            raise _LookupFailed(api)
        stats["skipped"] = 0
        waits: tuple[float, ...] = ()  # 찔러 보는 요청은 재시도하지 않는다
    else:
        waits = _RETRY_WAITS
    for attempt in range(len(waits) + 1):
        try:
            response = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
            response.raise_for_status()
            body = response.text.strip()
            # 응답이 왔으면 차단기를 푼다(API가 복구된 것이다).
            stats["streak"] = 0
            if not body:
                return {}  # 검색 결과 없음(정상 응답) — API가 빈 본문을 준다
            if body.startswith("<"):
                # 국립국어원 API는 오류를 200 + XML `<error>`로 돌려준다. 이걸
                # json()에 넘기면 그대로 터진다(전에는 파이프라인이 멈출 수 있었다).
                code = _api_error_code(body)
                if code == "100":
                    # "Incorrect query request" — 검색어가 API 문법에 맞지 않는다
                    # ('/'·'^' 실측). 서버 장애가 아니므로 **불통으로 세지 않는다**.
                    # 그 낱말만 조회하지 못한 것이라 결과 없음과 같게 다룬다.
                    return {}
                note_lookup_failure(api, f"{query} (error_code={code or '?'})")
                raise _LookupFailed(api)
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt < len(waits):
                time.sleep(waits[attempt])
    note_lookup_failure(api, query)
    raise _LookupFailed(api)


def _api_error_code(body: str) -> str | None:
    """200으로 온 XML `<error>` 응답에서 error_code를 뽑는다."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    if root.tag != "error":
        return None
    code = root.findtext("error_code")
    return code.strip() if code else None


@lru_cache(maxsize=4096)
def _fetch_stdict(query: str) -> dict:
    if not STDICT_API_KEY:
        raise RuntimeError("STDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    data = _get_json(STDICT_URL, {"key": STDICT_API_KEY, "q": query, "req_type": "json"}, "표준국어대사전")
    return data or _empty_channel()


def search_stdict(query: str) -> dict:
    """표준국어대사전 검색. 실패는 "찾지 못함"과 똑같이 처리한다 — 이 함수의 판단
    근거가 불확실하다는 뜻이므로, 호출부는 이미 "등재 안 됨/판단 근거 불충분"일 때와
    같은 경로(확인 플래그)로 넘어간다. 실패 사실은 리포트에 실린다."""
    try:
        return _fetch_stdict(query)
    except _LookupFailed:
        return _empty_channel()


@lru_cache(maxsize=4096)
def _fetch_opendict(query: str) -> dict:
    if not OPENDICT_API_KEY:
        raise RuntimeError("OPENDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    data = _get_json(OPENDICT_URL, {"key": OPENDICT_API_KEY, "q": query, "req_type": "json"}, "우리말샘")
    return data or _empty_channel()


def search_opendict(query: str) -> dict:
    """우리말샘 검색. 실패 처리 원칙은 `search_stdict()`와 같다."""
    try:
        return _fetch_opendict(query)
    except _LookupFailed:
        return _empty_channel()


def _opendict_examples_for_target(target_code) -> list[str]:
    """우리말샘 상세보기(view) API로 target_code(뜻풀이 하나)에 딸린 실제
    용례 문장들을 가져온다. 예문의 {중괄호} 강조 표시는 벗겨서 돌려준다."""
    if not OPENDICT_API_KEY:
        raise RuntimeError("OPENDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {"key": OPENDICT_API_KEY, "method": "target_code", "q": target_code, "req_type": "json"}
    response = requests.get(OPENDICT_VIEW_URL, params=params, headers=_HEADERS, timeout=10)
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


@lru_cache(maxsize=2048)
def _fetch_stdict_view(target_code: str) -> str:
    if not STDICT_API_KEY:
        raise RuntimeError("STDICT_API_KEY가 .env에 설정되어 있지 않습니다.")
    # req_type을 주지 않는다 — 이 API는 XML만 돌려준다(위 상수 주석 참고).
    params = {"key": STDICT_API_KEY, "method": "target_code", "q": target_code}
    api = "표준국어대사전(사전 내용)"
    note_lookup_attempt(api)
    for attempt in range(3):
        try:
            response = requests.get(STDICT_VIEW_URL, params=params, headers=_HEADERS, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt == 2:
                break
    note_lookup_failure(api, target_code)
    raise _LookupFailed(api)


def search_stdict_view(target_code: str) -> str:
    """표준국어대사전 사전 내용 조회(XML 본문 그대로). 실패는 빈 문자열이다 —
    호출부는 "그 표제어에 실린 추가 정보가 없다"와 같은 경로로 넘어간다."""
    if not target_code:
        return ""
    try:
        return _fetch_stdict_view(str(target_code))
    except _LookupFailed:
        return ""


def search_kornorms(keyword: str) -> list[dict]:
    """완전 일치 용례 조회. 실패는 빈 목록(= 등재된 표기 없음)으로 흡수한다."""
    try:
        return _fetch_kornorms(keyword)
    except _LookupFailed:
        return []


def search_kornorms_partial(keyword: str, rows: int = 30) -> list[dict]:
    """부분 일치 용례 조회. 실패는 빈 목록으로 흡수한다."""
    try:
        return _fetch_kornorms_partial(keyword, rows)
    except _LookupFailed:
        return []


@lru_cache(maxsize=4096)
def _fetch_kornorms(keyword: str) -> list[dict]:
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
    # 조회 실패는 "등재된 표기 없음"과 동일하게 처리해 loanword_fix()가 자동 반영
    # 없이 넘어가게 한다(원문 그대로 유지, 크래시 대신 안전하게 무처리).
    data = _get_json(KORNORMS_URL, params, "어문 규범 용례(kornorms)")
    return data.get("response", {}).get("items", []) or []


@lru_cache(maxsize=4096)
def _fetch_kornorms_partial(keyword: str, rows: int = 30) -> list[dict]:
    """kornorms 외래어 용례를 **부분 일치**로 조회한다.

    `search_kornorms()`는 `searchEquals=equal`로 완전 일치만 찾는다. 원어(로마자)로
    찾을 때는 그것만으로는 부족하다 — 인명 용례의 원어 표기가 `Ruth, Babe`,
    `Rutherford, Ernest`처럼 성·이름을 함께 담고 있어 `Ruth` 완전 일치로는 0건이
    나온다(2026-08-04 실측). 사용자가 원어를 입력해 확인하는 기능(§61)이 이걸 쓴다.

    부분 일치는 무관한 항목까지 함께 걸리므로(`Russ` -> `truss교`) **순위 판정은
    호출부가 한다** — `terms.lookup_by_source()` 참고.
    """
    if not KORNORMS_API_KEY:
        raise RuntimeError("KORNORMS_API_KEY가 .env에 설정되어 있지 않습니다.")
    params = {
        "serviceKey": KORNORMS_API_KEY,
        "pageNo": 1,
        "numOfRows": rows,
        "langType": "0003",  # 외래어
        "searchKeyword": keyword,
        "resultType": "json",
    }
    data = _get_json(KORNORMS_URL, params, "어문 규범 용례(kornorms)")
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
        response = requests.get(ONYONGEO_URL, params=params, headers=_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        note_lookup_failure("온용어(다듬은 말)")
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
        response = requests.get(KRDICT_URL, params=params, headers=_HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        note_lookup_failure("한국어기초사전")
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
def _fetch_dialect(query: str) -> list[dict]:
    """지역어 종합 정보 API에서 query를 검색한다(원시 조회, 실패는 예외로 올린다).

    `_LookupFailed`를 여기서 잡아 빈 리스트로 바꾸지 않는다 — lru_cache는
    예외를 캐시하지 않으므로, 여기서 흡수하면 순간적인 장애 하나가 그
    낱말의 판정을 프로세스가 사는 동안 계속 오염시킨다(§79 사고와 같은
    자리, `_LookupFailed` 클래스 설명 참고).
    """
    if not DIALECT_API_KEY:
        return []
    params = {
        "apiKey": DIALECT_API_KEY,
        "searchWord": query,
    }
    data = _get_json(DIALECT_URL, params, "지역어 종합 정보")
    if not data or data.get("returnCode") != 60000:
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


def search_dialect(query: str) -> list[dict]:
    """지역어 종합 정보 API에서 query를 검색한다.

    실패 처리 원칙은 `search_stdict()`/`search_opendict()`와 같다 — 조회
    실패(5xx 등)는 "매칭 없음"과 똑같이 빈 리스트로 흡수한다. 이전에는 이
    함수가 직접 `requests.get()`을 불러 재시도·차단기 없이 실패를 삼켰는데
    (AGENTS.md가 지적한 사고 지점), 그 경로는 `note_lookup_attempt()`도
    부르지 않아 리포트의 시도/실패 집계에서도 빠졌다. `_get_json()`을
    쓰도록 고쳐 다른 사전 조회와 같은 재시도·차단기·집계 경로를 타게
    했다. 실패 사실 자체는 `note_lookup_failure()`를 거쳐
    `failed_lookups()`/`lookup_stats()`로 리포트에 실린다 — 반환값만
    보고는 "장애"와 "매칭 없음"을 구분할 수 없다는 한계는 여전하지만
    (이 프로젝트 전역의 의도된 흡수 설계, AGENTS.md 참고), 그 사실이
    조용히 사라지지는 않는다.

    반환값: [{"word": "지역어", "std_word": "대응 표준어", "region": "시도 코드",
             "city": "시군구", "source": "출처", "year": "조사 연도"}, ...]
    """
    try:
        return _fetch_dialect(query)
    except _LookupFailed:
        return []
