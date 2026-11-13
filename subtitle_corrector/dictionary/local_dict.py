"""내려받은 국립국어원 사전 전체 데이터로 API 응답과 **같은 모양**을 만들어 주는 로컬 조회.

켜는 법: `.env`에 `DICT_LOCAL_DIR=<데이터 폴더>`(예: `D:/korean-dict-data`). 그 아래
`index/dict_index.sqlite3`를 쓴다(만드는 법: `tools/build_dict_index.py`). 비어 있거나 색인이
없으면 꺼진다 — 그때는 지금처럼 API만 쓴다. 시험은 `tests/conftest.py`가 끈다.

**원칙: 교정 결과가 API만 쓸 때와 달라지면 안 된다.** 그래서 API 응답을 확실히 재현할 수 있는
경우에만 답하고, 나머지는 `None`을 돌려 API로 넘긴다(`clients.py`가 디스크 캐시를 거쳐 부른다).
아래 규칙은 디스크 캐시에 남은 실제 API 응답과 대조해 정했다(2026-11-13).

표준국어대사전 검색(`stdict_search`) — 붙인다.
  - API의 `q` 검색은 **완전 일치**다: 응답 표제어는 하이픈·^·동음어 번호를 벗기면 모두 검색어와
    같았다. 동음어 하나가 항목 하나이고, `sup_no`(동음어 번호, 없으면 0) 순서로 최대 10건,
    `total`은 일치한 동음어 전체 수다.
  - 항목의 `sense`는 첫 뜻풀이 하나, `pos`는 첫 품사, `origin`은 원어를 이어 붙인 것.

우리말샘 검색(`opendict_search`) — 일부만 붙인다.
  - API의 `q` 검색은 완전 일치가 아니다: 완전 일치 그룹이 먼저 오고, 이어서 검색어로
    **시작하는** 표제어가 (하이픈·^를 벗긴 표제어, group_code) 순으로 오며, 그래도 10건이
    안 되면 검색어를 **중간에 포함한** 표제어가 온다. 10건(그룹 단위)까지만 온다.
  - 완전 일치 그룹이 둘 이상이면 그 사이 순서가 group_code·sense_no 어느 것과도 맞지 않아
    재현할 수 없다. 호출부 일부는 첫 일치 항목을 쓰므로(`classify_compound` 등) 순서가 판단을
    바꿀 수 있다 → API로 넘긴다.
  - 완전+앞부분 일치가 10건이 안 되면 중간 포함 항목의 규칙을 몰라 → API로 넘긴다.
  - `total`은 API 값(중간 포함까지 센 수)을 재현하지 못한다. 교정기는 우리말샘 `total`을
    쓰지 않는다(2026-11-13 코드 확인). 여기서는 완전+앞부분 일치 수를 넣는다.

붙이지 않은 것 — 실제 API 응답을 남겨 둔 것이 없어 같은 결과인지 대조할 수 없다:
  - 표준국어대사전 사전 내용(view, XML 본문), 한국어기초사전 검색(krdict).

**로컬에 없으면 API로 다시 확인한다.** 내려받은 판(표준 2026-11-06, 우리말샘 2026-11-04)
뒤에 새로 실린 표제어가 있을 수 있다. "없음"을 로컬만 보고 단정하면 교정기가 새 낱말을 "사전에
없는 말"로 잘못 판단한다. 그래서 일치하는 것이 하나도 없으면 `None`(= API에 물어보라)을 돌려준다.
반대로 로컬에 있는 것은 판 차이로 뜻풀이가 조금 바뀌었을 수 있으나, 낱말이 사전에서 빠지는 일은
드물어 로컬 결과를 믿는다(남은 위험으로 보고됨).
"""
from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import threading

SCHEMA_VERSION = 1

_HOMONYM_NO = re.compile(r"(?<=\D)\d{2,3}$")
_PAGE = 10  # API 기본 num

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_CONN_PATH: str | None = None


def headword_key(word: str) -> str:
    """표제어 비교용 열쇠: 하이픈·^를 벗기고 끝의 동음어 번호('각본02', '과학-기술001')를 뗀다.
    호출부가 표제어를 `.replace("-", "").replace("^", "")`로 비교하는 것과 맞춘다."""
    return _HOMONYM_NO.sub("", (word or "").replace("-", "").replace("^", ""))


def index_path() -> str:
    folder = (os.getenv("DICT_LOCAL_DIR") or "").strip()
    return os.path.join(folder, "index", "dict_index.sqlite3") if folder else ""


def _db() -> sqlite3.Connection | None:
    global _CONN, _CONN_PATH
    path = index_path()
    if not path or not os.path.exists(path):
        return None
    if _CONN is None or _CONN_PATH != path:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        _CONN, _CONN_PATH = conn, path
    return _CONN


def _rows(sql: str, args: tuple) -> list[tuple] | None:
    try:
        with _LOCK:
            conn = _db()
            if conn is None:
                return None
            return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return None  # 색인이 망가져도 교정은 API로 계속한다


# 표준국어대사전 API는 뜻풀이 속 참조 표제어의 동음어 번호·뜻 번호를 지워 준다
# ('‘어04’를 달리 이르는 말.' -> '‘어’를 …', '‘거기01「1」’' -> '‘거기’', '→ 끗02.' -> '→ 끗.').
# 따옴표(‘…’) 안과 '→ ' 뒤에만 적용한다 — 본문의 '제12조' 같은 숫자를 지우지 않으려고.
_REF_MARK = re.compile(r"(?<=[가-힣ㄱ-ㅎㅏ-ㅣ])\d{2,3}|「\d+」|\[\d+\]")
_REF_SPAN = re.compile(r"‘[^’]*’|→ \S+")


def _clean_stdict_definition(text: str) -> str:
    return _REF_SPAN.sub(lambda m: _REF_MARK.sub("", m.group()), text or "")


def _origin(info) -> str:
    return "".join((o.get("original_language") or "") for o in (info or []))


def _split_homonym(word: str) -> tuple[str, int]:
    m = _HOMONYM_NO.search(word or "")
    return (word[: m.start()], int(m.group())) if m else (word or "", 0)


def _stdict_item(raw: dict) -> dict:
    info = raw.get("word_info") or {}
    word, sup_no = _split_homonym(info.get("word") or "")
    pos_info = (info.get("pos_info") or [{}])[0]
    sense = {}
    for pattern in pos_info.get("comm_pattern_info") or []:
        if pattern.get("sense_info"):
            sense = pattern["sense_info"][0]
            break
    code = str(raw.get("target_code"))
    return {
        "sup_no": str(sup_no),
        "origin": _origin(info.get("original_language_info")),
        "word": word,
        "target_code": code,
        "sense": {
            "definition": _clean_stdict_definition(sense.get("definition") or ""),
            "link": f"https://stdict.korean.go.kr/search/searchView.do?word_no={code}&searchKeywordTo=3",
            "type": sense.get("type") or "",
        },
        "pos": pos_info.get("pos") or "",
    }


def stdict_search(query: str) -> dict | None:
    """표준국어대사전 검색 API(`q`, 기본 쪽)와 같은 모양. 재현할 수 없거나 없으면 None."""
    if not query or not index_path() or query != query.strip() or " " in query:
        return None  # 띄어 쓴 검색어는 실제 응답으로 확인한 사례가 없다 → API
        return None
    rows = _rows("SELECT raw FROM stdict WHERE key = ?", (query,))
    if not rows:
        return None  # 꺼짐·오류·로컬에 없음 → API로 다시 확인(모듈 설명)
    items = sorted((_stdict_item(json.loads(r[0])) for r in rows), key=lambda it: int(it["sup_no"]))
    return {"channel": {"total": len(items), "num": _PAGE, "start": 1, "item": items[:_PAGE]}}


def _opendict_sense(raw: dict) -> dict:
    info = raw.get("wordinfo") or {}
    sense = raw.get("senseinfo") or {}
    code = str(raw.get("target_code"))
    return {
        "target_code": code,
        # API는 '품사 없음'과 '일반어'를 빈 값으로 준다(캐시 응답에 두 값이 한 번도 없다).
        "pos": "" if sense.get("pos") == "품사 없음" else (sense.get("pos") or ""),
        "sense_no": sense.get("sense_no") or "",
        "cat": ",".join(c.get("cat") or "" for c in (sense.get("cat_info") or [])),
        "origin": _origin(info.get("original_language_info")),
        "link": f"https://opendict.korean.go.kr/dictionary/view?sense_no={code}",
        # API는 뜻풀이의 '<'·'>'·'&'를 HTML 이스케이프해 준다('&lt;FL&gt;').
        "definition": html.escape(sense.get("definition") or "", quote=False),
        "type": "" if sense.get("type") == "일반어" else (sense.get("type") or ""),
    }


def opendict_search(query: str) -> dict | None:
    """우리말샘 검색 API(`q`, 기본 쪽)와 같은 모양. 순서를 재현할 수 있을 때만 답하고, 아니면 None."""
    if not query or not index_path() or query != query.strip() or " " in query:
        return None  # 띄어 쓴 검색어는 실제 응답으로 확인한 사례가 없다 → API
        return None
    exact = _rows("SELECT DISTINCT group_code FROM opendict WHERE key = ?", (query,))
    if not exact or len(exact) > 1:
        return None  # 없음(판 차이 가능) 또는 완전 일치 그룹 여럿(순서 재현 불가) → API
    # 앞부분 일치: key가 query로 시작하고 query와 같지 않은 것. 범위 검색으로 색인을 탄다.
    prefix = _rows(
        "SELECT DISTINCT key, group_code FROM opendict WHERE key > ? AND key < ? ORDER BY key, group_code LIMIT ?",
        (query, query + "\U0010ffff", _PAGE),
    )
    if prefix is None or 1 + len(prefix) < _PAGE:
        return None  # 중간 포함 항목이 끼어들 수 있다 → API
    groups = [exact[0][0]] + [g for _k, g in prefix[: _PAGE - 1]]
    items = []
    for group in groups:
        rows = _rows("SELECT word, raw FROM opendict WHERE group_code = ? ORDER BY group_order, target_code", (group,))
        if not rows:
            return None
        items.append({"word": rows[0][0], "sense": [_opendict_sense(json.loads(r[1])) for r in rows]})
    return {"channel": {"total": 1 + len(prefix), "num": _PAGE, "start": 1, "item": items}}
