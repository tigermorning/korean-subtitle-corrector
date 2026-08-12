"""빈도 신호가 붙임 판정을 가르는가 — 투자 전에 재 본다.

**왜 이걸 먼저 하나.** 오답을 0으로 만들면서 커버리지를 잃지 않는 유일한 수단이
**빈도**로 보인다(`docs/BACKLOG.md` 2안). `word_exists`의 불리언을 "얼마나 쓰이는가"
라는 연속값으로 바꾸는 것이므로, 기존 신호를 재해석하는 것이 아니라 없던 축을
추가하는 것이다 — 그래서 precision과 커버리지를 같이 올릴 수 있다.

그런데 국립국어원 말뭉치를 쓰려면 라이선스 확인이 먼저 걸린다
(`COMMERCIALIZATION.md` 1.1과 같은 종류). **투자하기 전에 신호가 실제로 갈리는지
재야 한다.**

**대리 지표를 쓴다** — 우리말샘 **용례 건수**. 무료고 지금 조회되며 성격이 같다
("얼마나 쓰이는가"). 약한 대리 지표로도 갈리면 진짜 빈도표는 더 잘 갈린다. 아예
안 갈리면 신호 자체가 없다는 뜻이고, 그때는 말뭉치를 구해도 헛수고다.

**측정 대상 — 모집단을 좁혀야 한다.** 빈도 신호가 필요한 자리는 **"붙임형이 표제어로
등재돼 있어서 시스템이 붙이려 드는 자리"**뿐이다. 표제어가 없으면 애초에 안 붙이므로
판정할 것이 없다.

그래서 `word_exists(붙임형)`이 참인 것만 센다. 첫 실행에서 이 필터가 없어
`너뿐이야`·`셋뿐이야`·`큰지` 같은 **체언+조사 어절**이 섞였고(표제어가 아니므로 용례가
0인 것이 당연하다) 신호가 없는 것처럼 보였다(2026-08-12). 제42항 이중 기능 단어는
빈도 문제가 아니라 **앞말 품사 문제**다 — 빈도로 풀 대상이 아니다.

    입력 '요리 하는 게 좋아' -> 정답 '요리하는 게 좋아'   붙임형 요리하다  붙임=정답
    입력 '사진 하러 가'     -> 정답 '사진 하러 가'         붙임형 사진하다  붙임=오답
                                                          (시스템이 붙이려 한 자리)

실행:
    .venv\\Scripts\\python.exe tools\\probe_frequency_signal.py
    .venv\\Scripts\\python.exe tools\\probe_frequency_signal.py --limit 20   (빠른 확인)
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "poc" / "mq2-spacing-retrieval"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from subtitle_corrector.dictionary import (  # noqa: E402
    headword_definitions, usage_examples, word_exists)

# 평가셋 네 벌. 서로 다른 출처라 한쪽에 치우치지 않는다.
SOURCES = [
    ("제42항", ROOT / "poc/mq2-spacing-retrieval/dataset.jsonl"),
    ("실사용", ROOT / "poc/mq2-spacing-retrieval/dataset_realusage.jsonl"),
    ("heldout", ROOT / "examples/eval/heldout.jsonl"),
    ("작업자자료", ROOT / "examples/eval/작업자자료.jsonl"),
]


def load_all() -> list[dict]:
    items = []
    for name, path in SOURCES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            item["_set"] = name
            items.append(item)
    return items


def spacing_changes(before: str, after: str) -> list[tuple[str, str]]:
    """input과 gold의 띄어쓰기 차이를 찾는다.

    반환: (판정, 붙임형) 목록. 판정은 "joined"(붙이는 것이 정답) 또는
    "spaced"(띄우는 것이 정답).

    어절 단위로 훑는다. 낱말 자체가 바뀐 항목(외래어 표기 등)은 이 무늬에 안 걸리고
    자연히 빠진다 — 이 조사의 대상이 아니다.
    """
    a, b = before.split(), after.split()
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1; j += 1
        elif i + 1 < len(a) and b[j] == a[i] + a[i + 1]:
            out.append(("joined", b[j])); i += 2; j += 1      # 띄운 것을 붙였다
        elif j + 1 < len(b) and a[i] == b[j] + b[j + 1]:
            out.append(("spaced", a[i])); i += 1; j += 2      # 붙은 것을 띄웠다
        else:
            i += 1; j += 1
    return out


def probe(items: list[dict], limit: int = 0) -> dict:
    import arms                                    # _lemma_of 재사용

    pairs: dict[str, dict] = {}                    # 낱말 -> 정보
    skipped = 0

    for item in items:
        before, gold = item.get("input") or "", item.get("gold") or ""
        if not before or not gold:
            skipped += 1
            continue
        changes = spacing_changes(before, gold)
        if not changes:
            skipped += 1                           # 띄어쓰기 차이가 없는 항목
            continue
        for verdict, joined_form in changes:
            lemma = arms._lemma_of(joined_form)
            if not lemma or len(lemma) < 2:
                continue
            row = pairs.setdefault(lemma, {
                "lemma": lemma, "surface": joined_form, "verdict": verdict,
                "sets": set(), "ids": [],
            })
            row["sets"].add(item["_set"])
            row["ids"].append(item.get("id", "?"))
            # 같은 낱말이 양쪽 정답으로 나오면 표시해 둔다 — 문맥 의존 낱말이다
            if row["verdict"] != verdict:
                row["verdict"] = "both"

    lemmas = list(pairs.values())
    if limit:
        lemmas = lemmas[:limit]

    print(f"평가셋 {len(items)}건 -> 띄어쓰기 차이가 있는 낱말 {len(pairs)}개 "
          f"(대상 아님 {skipped}건)\n")

    for n, row in enumerate(lemmas, 1):
        try:
            row["examples"] = len(usage_examples(row["lemma"]) or [])
            row["defs"] = len(headword_definitions(row["lemma"]) or [])
            row["exists"] = bool(word_exists(row["lemma"]))
        except Exception as exc:
            row["examples"] = row["defs"] = -1
            row["exists"] = None
            row["error"] = f"{type(exc).__name__}"
        mark = "" if row["exists"] else "   (표제어 아님 — 모집단 제외)"
        print(f"[{n}/{len(lemmas)}] {row['lemma']:12} 정답={row['verdict']:6} "
              f"용례={row['examples']:>3} 뜻풀이={row['defs']:>2} "
              f"표제어={row['exists']}{mark}", flush=True)

    return {"lemmas": lemmas, "total_items": len(items), "skipped": skipped}


def report(result: dict) -> None:
    scanned = [r for r in result["lemmas"] if r.get("examples", -1) >= 0]
    # **모집단은 붙임형이 표제어인 것뿐이다.** 표제어가 없으면 시스템이 붙일 근거가
    # 애초에 없어 판정할 것이 없다 — 그런 것을 섞으면 신호가 희석된다.
    rows = [r for r in scanned if r.get("exists")]
    excluded = len(scanned) - len(rows)
    joined = [r for r in rows if r["verdict"] == "joined"]
    spaced = [r for r in rows if r["verdict"] == "spaced"]
    both = [r for r in rows if r["verdict"] == "both"]

    def stat(group, key):
        vals = sorted(r[key] for r in group)
        if not vals:
            return "—"
        mid = vals[len(vals) // 2]
        return f"평균 {sum(vals)/len(vals):.2f} · 중위 {mid} · 0건 {vals.count(0)}/{len(vals)}"

    print("\n" + "=" * 74)
    print(f"조회 {len(scanned)}개 중 **붙임형이 표제어인 것 {len(rows)}개**가 모집단 "
          f"(표제어 아님 {excluded}개 제외 — 체언+조사 어절 등)")
    print(f"  붙임 정답 {len(joined)} · 띄움 정답 {len(spaced)} · 양쪽 {len(both)}")
    print("=" * 74)
    print(f"{'':14}{'용례 건수':<38}{'뜻풀이 개수'}")
    print(f"{'붙임이 정답':14}{stat(joined, 'examples'):<38}{stat(joined, 'defs')}")
    print(f"{'띄움이 정답':14}{stat(spaced, 'examples'):<38}{stat(spaced, 'defs')}")
    print("-" * 74)

    # 판정 기준: 용례 0건이면 안 쓰이는 낱말로 보는 규칙을 세웠을 때의 성능
    if joined and spaced:
        tp = sum(1 for r in spaced if r["examples"] == 0)     # 안 붙여야 하는데 용례 0
        fp = sum(1 for r in joined if r["examples"] == 0)     # 붙여야 하는데 용례 0 (오탐)
        print(f"'용례 0건이면 붙이지 않는다' 규칙을 세우면:")
        print(f"    맞게 막는다   {tp}/{len(spaced)} ({tp/len(spaced):.0%})")
        print(f"    잘못 막는다   {fp}/{len(joined)} ({fp/len(joined):.0%})  <- 이것이 새 오답")
        verdict = ("신호 있음 — 말뭉치 빈도로 넘어갈 근거가 된다"
                   if tp / max(1, len(spaced)) > 0.5 and fp / max(1, len(joined)) < 0.2
                   else "신호 약함 — 용례 건수만으로는 못 가른다")
        print(f"\n  판정: {verdict}")
    print("=" * 74)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("-o", "--out", default="")
    args = ap.parse_args()

    items = load_all()
    result = probe(items, args.limit)
    report(result)

    if args.out:
        dump = {**result, "lemmas": [{**r, "sets": sorted(r["sets"])} for r in result["lemmas"]]}
        Path(args.out).write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n상세: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
