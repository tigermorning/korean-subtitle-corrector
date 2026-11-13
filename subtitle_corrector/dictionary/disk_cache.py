"""사전 API 응답을 디스크(SQLite 한 파일)에 남겨, 다음 실행에서 같은 조회를 건너뛴다.

`@lru_cache`는 프로세스가 사는 동안만 남는다 — 명령줄로 자막 한 편을 교정하면
매번 수천 건을 처음부터 다시 조회하고, 한 편에 25~34분이 걸렸다(2026-11-13 실측,
대부분 사전 조회 대기). 그래서 성공한 응답만 디스크에 남긴다.

켜는 법: `.env`에 `DICT_CACHE_DIR=<폴더>`. 비어 있으면 아무것도 하지 않는다(시험은
`tests/conftest.py`가 끈다). 오래된 응답은 `DICT_CACHE_DAYS`(기본 30일)가 지나면 다시
조회한다 — 사전은 고쳐지므로 영원히 믿지 않는다.

**실패는 남기지 않는다.** 감싸는 함수가 실패를 예외(`_LookupFailed`)로 올리는 것만
이 장식자를 쓴다. 실패를 빈 결과로 바꿔 돌려주는 함수(온용어·한국어기초사전 조회)에
쓰면 순간적인 장애가 "없는 낱말"로 디스크에 굳는다 — `clients.py`의 `_LookupFailed`
설명과 같은 이유다. 결과의 일부만 믿을 수 있는 함수는 `keep`으로 거른다.

API 키는 키(key)에 넣지 않는다 — 인자(검색어)만 넣는다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from functools import wraps
from typing import Any, Callable

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_CONN_DIR: str | None = None


def _cache_dir() -> str:
    return (os.getenv("DICT_CACHE_DIR") or "").strip()


def _max_age() -> float:
    try:
        return float(os.getenv("DICT_CACHE_DAYS") or 30) * 86400
    except ValueError:
        return 30 * 86400


def _db(folder: str) -> sqlite3.Connection:
    global _CONN, _CONN_DIR
    if _CONN is None or _CONN_DIR != folder:
        os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(os.path.join(folder, "dict_cache.sqlite3"), check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, at REAL NOT NULL)")
        conn.commit()
        _CONN, _CONN_DIR = conn, folder
    return _CONN


def disk_cache(name: str, keep: Callable[[Any], bool] = lambda _v: True,
               decode: Callable[[Any], Any] = lambda v: v):
    """`name`은 API 구분용. `keep(결과)`가 거짓이면 남기지 않는다. `decode`는 JSON에서
    되살릴 때 쓴다(튜플은 JSON에서 리스트가 되므로)."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            folder = _cache_dir()
            if not folder:
                return fn(*args, **kwargs)
            key = name + "|" + json.dumps([args, kwargs], ensure_ascii=False, sort_keys=True, default=str)
            try:
                with _LOCK:
                    row = _db(folder).execute("SELECT v, at FROM kv WHERE k = ?", (key,)).fetchone()
            except sqlite3.Error:
                row = None  # 캐시가 망가져도 교정은 계속한다
            if row and time.time() - row[1] < _max_age():
                return decode(json.loads(row[0]))
            value = fn(*args, **kwargs)  # 실패면 예외가 그대로 올라가 남지 않는다
            if keep(value):
                try:
                    with _LOCK:
                        conn = _db(folder)
                        conn.execute("INSERT OR REPLACE INTO kv (k, v, at) VALUES (?, ?, ?)",
                                     (key, json.dumps(value, ensure_ascii=False), time.time()))
                        conn.commit()
                except (sqlite3.Error, TypeError, ValueError):
                    pass
            return value

        return wrapper

    return deco
