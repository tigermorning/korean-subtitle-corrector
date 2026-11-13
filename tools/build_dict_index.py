"""내려받은 국립국어원 사전 전체 데이터(JSON)로 로컬 조회 색인(SQLite)을 만든다.

쓰는 법:
    python tools/build_dict_index.py <데이터 폴더> [<색인 파일>]
    예) python tools/build_dict_index.py D:/korean-dict-data D:/korean-dict-data/index/dict_index.sqlite3

<데이터 폴더> 아래 `stdict/*.json`(표준국어대사전), `opendict/*.json`(우리말샘)을 읽는다.
색인 파일 기본 위치는 `<데이터 폴더>/index/dict_index.sqlite3` — 교정기는 `.env`의
`DICT_LOCAL_DIR=<데이터 폴더>`로 이 파일을 찾는다.

**색인은 저장소 안에 두지 않는다.** 우리말샘은 CC BY-SA이고 저장소는 공개라, 사전 내용이
들어 있는 이 파일을 저장소에 넣으면 안 된다. 데이터 폴더 쪽에 둔다.

원본 항목을 거의 그대로(용례 `example_info`만 빼고) 넣는다. API 응답 모양은 조회할 때
`subtitle_corrector/dictionary/local_dict.py`가 만든다 — 응답 모양 규칙을 고쳐도 색인을
다시 만들 필요가 없게 하려는 것이다.

한국어기초사전(krdict)은 넣지 않는다: 실제 API 응답을 남겨 둔 것이 없어 같은 결과인지
대조할 수 없다(`local_dict.py` 설명 참고).
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from subtitle_corrector.dictionary.local_dict import SCHEMA_VERSION, headword_key  # noqa: E402


def _drop_examples(node):
    if isinstance(node, dict):
        return {k: _drop_examples(v) for k, v in node.items() if k != "example_info"}
    if isinstance(node, list):
        return [_drop_examples(v) for v in node]
    return node


def _items(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = (data.get("channel") or {}).get("item") or []
    return [items] if isinstance(items, dict) else items


def build(data_dir: str, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE stdict (key TEXT NOT NULL, raw TEXT NOT NULL);
        CREATE TABLE opendict (key TEXT NOT NULL, word TEXT NOT NULL, group_code INTEGER,
                               group_order INTEGER, target_code INTEGER, raw TEXT NOT NULL);
        """
    )
    started = time.time()
    for name, table in (("stdict", "stdict"), ("opendict", "opendict")):
        files = sorted(glob.glob(os.path.join(data_dir, name, "*.json")))
        if not files:
            raise SystemExit(f"{name} 파일이 없다: {os.path.join(data_dir, name)}")
        count = 0
        for path in files:
            rows = []
            for item in _items(path):
                item = _drop_examples(item)
                if table == "stdict":
                    word = (item.get("word_info") or {}).get("word") or ""
                    rows.append((headword_key(word), json.dumps(item, ensure_ascii=False)))
                else:
                    word = (item.get("wordinfo") or {}).get("word") or ""
                    rows.append((headword_key(word), word, item.get("group_code"), item.get("group_order"),
                                 item.get("target_code"), json.dumps(item, ensure_ascii=False)))
            if table == "stdict":
                conn.executemany("INSERT INTO stdict VALUES (?, ?)", rows)
            else:
                conn.executemany("INSERT INTO opendict VALUES (?, ?, ?, ?, ?, ?)", rows)
            count += len(rows)
            print(f"{name}: {os.path.basename(path)} ({count}건, {time.time() - started:.0f}초)", flush=True)
        conn.execute("INSERT INTO meta VALUES (?, ?)", (f"{name}_files", str(len(files))))
        conn.execute("INSERT INTO meta VALUES (?, ?)", (f"{name}_rows", str(count)))
    conn.execute("CREATE INDEX stdict_key ON stdict (key)")
    conn.execute("CREATE INDEX opendict_key ON opendict (key)")
    conn.execute("CREATE INDEX opendict_group ON opendict (group_code)")
    conn.execute("INSERT INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
    conn.execute("INSERT INTO meta VALUES ('built_at', ?)", (time.strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()
    os.replace(tmp, out_path)
    print(f"완료: {out_path} ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data_dir = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(data_dir, "index", "dict_index.sqlite3")
    build(data_dir, out)
