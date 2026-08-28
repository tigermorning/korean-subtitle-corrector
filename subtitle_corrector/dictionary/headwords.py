"""
"이 표기가 사전에 있는가" 계열 판정.

표제어 존재·합성어 등재 여부·뜻풀이 표지처럼, 답이 "있다/없다"로 끝나는 조회다.
그 표기를 무엇으로 바꿔야 하는지는 `terms.py`가 다룬다.
"""

import re
from functools import lru_cache
import requests
from ..gananda_precedents import check_precedent
import xml.etree.ElementTree as ET

from .clients import (
    _opendict_examples_for_target,
    search_opendict,
    search_stdict,
    search_stdict_view,
)

_NONSTANDARD_REDIRECT_MARKERS = ("규범 표기는", "표준 용어는")


def _opendict_item_is_standard(item: dict) -> bool:
    """우리말샘은 이미 알려진 비표준 표기("초코렛", "스노우 체인" 등)도
    하나의 표제어처럼 등재해 두고, 그 뜻풀이 끝에 "⇒규범 표기는 'OO'이다"라고
    정답을 안내한다. 화학·의학 등 전문 용어는 "⇒표준 용어는 'OO'이다"라는
    다른 문구를 쓴다(예: "요오드"⇒"표준 용어는 '아이오딘'이다" — 실사용
    검증으로 발견, "규범 표기는"만 확인하던 코드가 이 문구를 놓치고 있었음).
    이런 항목은 "표제어가 존재는 하지만 틀린 표기"이므로 존재 확인 근거로
    쓰면 안 된다 — 하나라도 이 안내가 없는 뜻풀이가 있으면 표준 표기로 본다.

    다만 "⇒규범 표기는 미확정이다"(예: "쉴더병")는 다른 대안 표기를
    안내하는 게 아니라 국립국어원이 아직 표준 표기를 정하지 못했다는
    뜻이다 — 이 표기 자체가 현재로선 유일하게 등재된 표기이므로, 다른
    대안이 있는 경우("규범 표기는/표준 용어는 'X'이다")와 구분해서 표준으로
    인정한다."""
    senses = item.get("sense", [])
    if not senses:
        return True
    # 뜻풀이가 여럿인 표제어는(예: "흩어지다" — 뜻1은 표준 '흩어지다', 뜻2·3만
    # "⇒규범 표기는 '흐트러지다'") 재지정 안내가 '없는' 뜻이 하나라도 있으면
    # 그 표기 자체는 표준으로 등재된 것이다. 모든 뜻이 다른 표기로 재지정될
    # 때만("요오드"⇒"아이오딘") 비표준으로 본다.
    for sense in senses:
        definition = sense.get("definition") or ""
        redirects = (
            any(marker in definition for marker in _NONSTANDARD_REDIRECT_MARKERS)
            and "미확정" not in definition
        )
        # '북한어' 뜻(예: "'로봇'의 북한어.")은 남한 표준어가 아니므로 표준 자격
        # 뜻으로 치지 않는다 — 이게 없으면 '로보트'(재지정 뜻 + 북한어 뜻)가
        # 표준으로 오판되어 외래어 교정(로보트→로봇)이 막힌다. 방언은 제외하지
        # 않는다(건숭 등 방언 표제어는 존재하는 단어로 인정해야 오탐지를 막는다).
        is_north_korean = "북한어" in definition
        if not redirects and not is_north_korean:
            return True
    return False


# 현대 일반 문장의 근거로 삼을 수 없는 표제어 분야. 사전에 있다는 사실만으로 붙여
# 쓰면 안 되는 말들이다 — 2026-08-02 실사용에서 '미림이도 오고 했는데'가
# '오고했는데'로 붙자는 제안을 받았는데, 근거였던 '오고하다'는 五考하다(역사: 벼슬아치
# 고과)와 제주 방언뿐이었다. 지금 쓰는 말이 아니다.
_NON_CONTEMPORARY_FIELDS = frozenset({"역사", "방언", "옛말", "북한어", "은어"})


# 우리말샘은 지역어를 분야(cat) 없이 뜻풀이 안에 표시하는 경우가 있다
# ("제주 지역에서는 '오고다'로도 적는다"). 분야만 보면 이런 뜻이 일반어로 잡힌다.
_NON_CONTEMPORARY_PHRASES = ("지역에서는", "지역어", "옛말", "북한어", "은어로")


@lru_cache(maxsize=4096)
def is_contemporary_general_word(word: str) -> bool:
    """표제어에 **현대 일반어로 쓰이는 뜻**이 하나라도 있는지.

    분야 표시가 없는 뜻(일반어)이 하나라도 있으면 참이다. 모든 뜻이 역사·방언·옛말·
    은어 같은 특수 분야에만 달려 있으면 거짓 — 사전에 있다는 사실만으로 현대 문장의
    표기 근거로 삼을 수 없다.

    분야(cat)는 우리말샘만 제공하므로 그쪽을 본다. 조회 실패는 참으로 흡수한다
    (근거가 없으면 기존 동작을 바꾸지 않는다).
    """
    try:
        items = search_opendict(word).get("channel", {}).get("item", [])
    except Exception:
        return True
    if isinstance(items, dict):
        items = [items]
    fields = []
    for item in items:
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword != word:
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        for sense in senses:
            # 우리말샘은 분야를 `cat`, 어휘 구분을 `type`으로 따로 준다. 방언·북한어·
            # 옛말은 `cat`이 비고 `type`에만 들어오는 항목이 있다("깨끗히" -> cat="",
            # type="방언"). `cat`만 보던 코드는 이런 표제어를 일반어로 통과시켜,
            # 방언 표기가 붙여쓰기 근거로 쓰였다(2026-08-03 평가셋 라벨 검증 중 발견).
            field = (sense.get("cat") or "").strip()
            lexical_type = (sense.get("type") or "").strip()
            definition = sense.get("definition") or ""
            marked = field in _NON_CONTEMPORARY_FIELDS or lexical_type in _NON_CONTEMPORARY_FIELDS or any(
                phrase in definition for phrase in _NON_CONTEMPORARY_PHRASES
            )
            fields.append(marked)
    if not fields:
        return True  # 우리말샘에 없으면 판단 근거가 없다 -> 기존 동작 유지
    return not all(fields)


@lru_cache(maxsize=4096)
def appears_in_standard_headword(word: str) -> bool:
    """word가 우리말샘 표제어의 **구성 요소**로 등장하는지 확인한다.

    단독 표제어가 없어도 '빌리지 뱅가드', '그리니치 빌리지', '스마트 빌리지'처럼
    그 말을 구성 요소로 쓰는 표제어가 국립국어원 사전에 여럿 있으면, 그건 한국어에서
    통용되는 표기라는 근거다(2026-08-02 실사용: '빌리지'를 "사전에 없는 단어"로
    플래그한 오탐지).

    **비표준 안내가 붙은 표제어는 근거로 인정하지 않는다.** 이 구분이 없으면
    '스노우 체인'(비표준, 표준은 '스노체인') 때문에 '스노우'가 통과해 확정 교정이
    무력해진다 — 실측으로 확인했다: 스노우 관련 표제어 3건은 전부 비표준 판정,
    빌리지 관련 표제어 6건은 전부 표준 판정이었다.
    """
    try:
        items = search_opendict(word).get("channel", {}).get("item", [])
    except Exception:
        return False
    if isinstance(items, dict):
        items = [items]
    for item in items:
        headword = item.get("word") or ""
        parts = [part for part in re.split(r"[\s^\-]", headword) if part]
        if len(parts) < 2 or word not in parts:
            continue  # 단독 표제어는 word_exists가 이미 확인했다
        if _opendict_item_is_standard(item):
            return True
    return False


@lru_cache(maxsize=4096)
def definition_markers(word: str) -> frozenset:
    """word의 표준국어대사전 뜻풀이에 나타나는 '맥락 경쟁' 표지를 돌려준다.
    - '준말': 다른 말의 준말(예: 큰애='큰아이'의 준말)
    - '비유적': 비유어(예: 턱밑='아주 가까운 곳'을 비유적으로)
    - '은어': 특정 집단의 말(예: 새발=은어로 '젓가락') — 2026-08-02 실사용에서
      '새 발의 피'가 '새발의 피'로 잘못 병합됐다. '새발'은 은어(젓가락)와 해조류
      이름뿐이라, 일반 문장의 '새 발'(새의 발)과 의미가 경쟁한다.
    이런 표지가 있으면 그 붙여쓰기 형태는 띄어 쓴 구(句)와 의미가 경쟁하므로,
    합성어라도 문맥 없이 자동으로 붙이면 안 된다는 신호다. 조회 실패는 빈
    집합으로 흡수한다."""
    markers = set()
    try:
        items = search_stdict(word).get("channel", {}).get("item", [])
    except Exception:
        return frozenset()
    if isinstance(items, dict):
        items = [items]
    for item in items:
        headword = (item.get("word") or "").replace("-", "").replace("^", "")
        if headword != word:
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        for sense in senses:
            definition = sense.get("definition") or ""
            if "준말" in definition:
                markers.add("준말")
            if "비유적" in definition:
                markers.add("비유적")
            if "은어로" in definition:
                markers.add("은어")
    return frozenset(markers)


def only_sino_korean_headword(word: str) -> bool:
    """word와 정확히 일치하는 표준국어대사전 표제어가 **전부 한자어**인지 확인한다.

    한자 원어 정보(`origin`)가 있으면 그 표제어는 한자어이고, 접두사·접미사가 붙은
    고유어 파생어가 아니다. 이 구분이 필요한 이유(2026-08-04 사용자 지적):

        처-먹다   origin=''        접두사 '처-'(마구/속되게) 파생어  -> '쳐먹다'의 정답
        처-하다   origin='處하다'   한자어 處하다(형편에 놓이다)      -> '쳐 하다'의 정답이 아니다

    `word_exists('처하다')`는 True라서, 그것만 근거로 삼으면 `쳐 하든가`를
    `처하든가`로 고치자고 제안한다 — 뜻이 전혀 다른 낱말이다(§58이 말하는
    긍정 근거 사고). 조회 실패·미등재는 False로 흡수한다(근거 없음).
    """
    try:
        items = search_stdict(word).get("channel", {}).get("item", [])
    except Exception:
        return False
    if isinstance(items, dict):
        items = [items]
    matches = [
        item
        for item in items
        if (item.get("word") or "").replace("-", "").replace("^", "") == word
    ]
    if not matches:
        return False
    return all((item.get("origin") or "").strip() for item in matches)


def sino_korean_origin(word: str) -> str:
    """word 표제어의 한자 원어 표기를 돌려준다('처하다' -> '處하다'). 없으면 빈 문자열.

    플래그 사유에 **근거를 그대로 싣기 위한** 도우미다 — "그 표제어는 한자어 處하다라
    뜻이 다르다"고 말할 수 있어야 번역가가 판단할 수 있다."""
    try:
        items = search_stdict(word).get("channel", {}).get("item", [])
    except Exception:
        return ""
    if isinstance(items, dict):
        items = [items]
    for item in items:
        if (item.get("word") or "").replace("-", "").replace("^", "") != word:
            continue
        origin = (item.get("origin") or "").strip()
        if origin:
            return origin
    return ""


def standard_headword_example(word: str) -> tuple[str, str]:
    """word를 구성 요소로 쓰는 **표준** 우리말샘 표제어 하나와 그 원어를 돌려준다.

    플래그 사유에 근거를 그대로 싣기 위한 도우미다(§66). `쉴러`에 대해
    `('쉴러 검사', 'Schiller檢査')`를 돌려주므로, "같은 원어인데 사전은 이렇게 적는다"를
    사용자가 눈으로 확인할 수 있다 — 2026-08-05 사용자 지적("schiller는 사전상 쉴러")을
    도구가 스스로 보여 주게 만든 것이다.

    조각 수가 적은 표제어를 고른다(짧은 것이 대표적이다). 없으면 빈 쌍.
    """
    try:
        items = search_opendict(word).get("channel", {}).get("item", [])
    except Exception:
        return "", ""
    if isinstance(items, dict):
        items = [items]
    candidates = []
    for item in items:
        headword = item.get("word") or ""
        parts = [part for part in re.split(r"[\s^\-]", headword) if part]
        if len(parts) < 2 or word not in parts:
            continue
        if not _opendict_item_is_standard(item):
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        origin = ""
        for sense in senses:
            origin = (sense.get("origin") or "").strip()
            if origin:
                break
        candidates.append((len(parts), " ".join(parts), origin))
    if not candidates:
        return "", ""
    _size, headword, origin = sorted(candidates)[0]
    return headword, origin


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
    "존재함"으로 오판하게 된다.

    두 사전 어디에도 없는 경우, gananda_precedents(온라인가나다 판례 축적본)에
    이 표현에 대한 확인된 판례가 있는지도 마지막으로 확인한다 — 실시간 사전
    데이터가 항상 우선이고, 판례는 사전에 아무 답이 없을 때만 보조로 쓴다.

    표준국어대사전에 표제어가 있어도 곧바로 True를 반환하지 않는다 —
    "요오드"처럼 표준국어대사전 자체엔 비표준 안내가 없지만 우리말샘에는
    "표준 용어는 '아이오딘'이다"라고 새로 갱신된 안내가 있는 경우(전문
    용어 표준화가 표준국어대사전보다 우리말샘에 먼저/추가로 반영된 것으로
    보임)를 놓치게 된다 — 실사용 검증으로 발견됨. 그래서 표준국어대사전에
    있어도 우리말샘에 정확히 일치하는 표제어가 있으면 그 비표준 안내
    여부까지 항상 확인한다."""
    stdict_hit = int(search_stdict(query).get("channel", {}).get("total", 0)) > 0
    opendict_result = search_opendict(query)
    opendict_matches = [
        item
        for item in opendict_result.get("channel", {}).get("item", [])
        if (item.get("word") or "").replace("-", "").replace("^", "") == query
    ]
    # "집"처럼 같은 표제어 아래 여러 동형이의어가 있을 수 있다("집"=거처인
    # 표준 표기 vs "집"=즙의 비표준 표기가 우연히 같은 글자). 하나라도
    # 비표준으로 확인되면 전체를 비표준으로 단정하지 않는다 — 그중 표준으로
    # 확인되는 동형이의어가 하나라도 있으면 그 뜻으로 정상 존재하는 단어로
    # 본다. 반대로, 검색된 동형이의어 전부가 비표준으로 명시되어 있으면
    # (예: "요오드" — 일치하는 항목이 이것 하나뿐이고 그마저 비표준) 표준
    # 국어대사전 등재 여부와 무관하게 비표준으로 판단한다.
    if opendict_matches:
        if any(_opendict_item_is_standard(item) for item in opendict_matches):
            return True
        return False
    if stdict_hit:
        return True
    precedent = check_precedent(query)
    if precedent is not None:
        return precedent
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


def usage_examples(word: str, limit: int = 2) -> list[str]:
    """우리말샘에서 word와 정확히 일치하는 표제어의 실제 용례(예문)를 가져온다.

    순화어처럼 사람이 문맥으로 직접 판단해야 하는 플래그 항목에 참고 예문을
    덧붙여, 번역가가 사전을 따로 찾아보지 않고도 바로 문맥을 확인할 수 있게
    돕기 위함이다. 용례가 없거나
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


def registered_ending(candidate: str) -> str | None:
    """candidate가 표준국어대사전/우리말샘에 "-candidate" 형태(어간·선어말
    어미 등에 붙는 접미형 표제어 — 어미·조사·접사가 공통으로 쓰는 표기
    관례)로 정확히 등재되어 있으면 그 표제어(하이픈 포함)를 돌려준다.

    kiwi는 "있잖아"("있"+"지"+"않"+"아"), "없다잖나"("없다"+"고"+"하"+"지"
    +"않"+"나")처럼 압축된 구어체 표현을 내부적으로 여러 형태소로 억지로
    분해하다가, 그 형태소들의 위치가 서로 겹치거나 길이가 0인 등 스스로도
    확신 없는 재구성을 만들어낸다(사용자 지적: "kiwi는 참고일 뿐, 사전의
    표제어와 용례를 기준으로 해야 한다"). 이런 압축형 자체가 이미 사전에
    하나의 표제어로 등재되어 있는 경우(예: "-잖다", "-잖아", "-거든",
    "-ㄹ걸")는, kiwi의 내부 형태소 분해 결과와 무관하게 그 표제어 등재
    사실 자체를 근거로 삼아 "이 뒤에는 공백을 넣지 않는다"고 판단할 수
    있다."""
    for search in (search_stdict, search_opendict):
        result = search(candidate)
        for item in result.get("channel", {}).get("item", []):
            if (item.get("word") or "") == f"-{candidate}":
                return item["word"]
    return None


# `norm_info`의 설명문에는 잘못된 표기를 감싸는 `<IN>…</IN>` 태그가 섞여 온다
# (`'<IN>부디치다</IN>'로 적지 않고`). 사람이 읽을 문장이므로 태그만 벗긴다.
_NORM_INLINE_TAG = re.compile(r"</?[A-Za-z_]+>")


@lru_cache(maxsize=1024)
def spelling_norm_note(word: str) -> str:
    """표준국어대사전이 그 표기의 **한글 맞춤법 근거**로 적어 둔 설명문을 돌려준다.

    검색 API에는 없고 사전 내용 API(`view.do`)의 `norm_info`에만 있다
    (`docs/BACKLOG.md` 6번). 예를 들어 `곰곰이`에는 "부사에 '-이'가 붙어서 뜻을
    더하는 경우에는 그 부사의 원형을 밝혀 적는다는 규정(한글 맞춤법 제25항)과
    부사의 끝음절이 분명히 '이'로만 나는 것은 '-이'로 적는다는 규정(제51항)에
    따라…"가 실려 있다.

    이 도구가 "사전 근거 있음"이라고만 말하던 자리에 **규정 조항을 그대로 인용**하기
    위한 도우미다 — 번역가가 근거를 스스로 확인할 수 있어야 제안을 판단할 수 있다.

    `type`이 '한글 맞춤법'인 것만 쓴다(다른 type은 표준어 규정·외래어 표기법 등이라
    이 자리에서 인용하면 어긋난다). 없으면 빈 문자열.
    """
    items = search_stdict(word).get("channel", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    for item in items:
        # 표제어의 하이픈 표기(`곰곰-이`)를 벗겨 정확히 그 낱말인 것만 본다.
        if (item.get("word") or "").replace("-", "").replace("^", " ") != word:
            continue
        body = search_stdict_view(item.get("target_code") or "")
        if not body:
            continue
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            continue
        for info in root.iter("norm_info"):
            if (info.findtext("type") or "").strip() != "한글 맞춤법":
                continue
            desc = (info.findtext("desc") or "").strip()
            if desc:
                return _NORM_INLINE_TAG.sub("", desc)
    return ""


def _exact_senses(word: str) -> list[dict]:
    """우리말샘에서 **정확히 그 표제어**인 항목의 뜻 목록."""
    try:
        items = search_opendict(word).get("channel", {}).get("item", [])
    except Exception:
        return []
    if isinstance(items, dict):
        items = [items]
    senses: list[dict] = []
    for item in items:
        if (item.get("word") or "").replace("-", "").replace("^", "") != word:
            continue
        found = item.get("sense", [])
        found = found if isinstance(found, list) else [found]
        senses.extend(s for s in found if isinstance(s, dict))
    return senses


@lru_cache(maxsize=2048)
def sense_fields(word: str) -> frozenset:
    """word의 뜻에 달린 전문 분야 표시(우리말샘 `cat`) 집합.

    `힘줄집` -> {'의학'}, `원기둥` -> {'수학'}. 일반어 뜻에는 표시가 없으므로
    **비어 있다고 해서 전문어가 아니라는 뜻은 아니다** — `환자`·`치료`처럼 흔한
    의학 관련 낱말도 표시가 없거나 엉뚱한 분야만 달려 있다(`환자` -> 경제·역사).
    그래서 이 신호는 "있으면 근거", "없으면 모름"으로만 쓴다.
    """
    return frozenset(f for s in _exact_senses(word) if (f := (s.get("cat") or "").strip()))


@lru_cache(maxsize=2048)
def headword_definitions(word: str) -> tuple:
    """word의 뜻풀이 전체(우리말샘). 문맥 판정에서 낱말 겹침을 볼 때 쓴다."""
    return tuple(d for s in _exact_senses(word) if (d := (s.get("definition") or "").strip()))
