"""한국어기초사전(krdict) 내려받은 JSON에서 '낱말 -> 의미 범주 집합'만 뽑은 작은 색인을 만든다.

쓰는 법:
    python tools/build_krdict_semcat.py <데이터 폴더> [<색인 파일>]
    예) python tools/build_krdict_semcat.py D:/korean-dict-data

<데이터 폴더>/krdict/*.json(LexicalResource 형식)을 읽고, 기본으로
`<데이터 폴더>/index/krdict_semcat.json`에 쓴다. 교정기의 로서/로써 검사
(`subtitle_corrector/engine/rosseo.py`)가 `.env`의 `DICT_LOCAL_DIR`로 이 파일을 찾는다.

**색인은 저장소 안에 두지 않는다.** 한국어기초사전은 CC BY-SA이고 저장소는 공개다.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys


def _as_list(node):
    return node if isinstance(node, list) else [node] if node else []


def build(data_dir: str) -> dict[str, list[str]]:
    cats: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(glob.glob(os.path.join(data_dir, "krdict", "*.json"))):
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        for entry in _as_list(data["LexicalResource"]["Lexicon"]["LexicalEntry"]):
            feats = {f.get("att"): f.get("val") for f in _as_list(entry.get("feat")) if isinstance(f, dict)}
            lemma = (_as_list(entry.get("Lemma")) or [{}])[0]
            lemma_feat = (_as_list(lemma.get("feat")) or [{}])[0]
            word = lemma_feat.get("val") if isinstance(lemma_feat, dict) else None
            if word and feats.get("semanticCategory"):
                cats[word].add(feats["semanticCategory"])
    return {w: sorted(c) for w, c in sorted(cats.items())}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data_dir = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(data_dir, "index", "krdict_semcat.json")
    index = build(data_dir)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False)
    print(f"{len(index)}개 낱말 -> {out}")


if __name__ == "__main__":
    main()
