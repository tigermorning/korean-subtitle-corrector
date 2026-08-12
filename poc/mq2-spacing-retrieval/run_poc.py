"""PoC 실행기 — 평가셋을 arm마다 돌리고 채점한다.

    python poc/mq2-spacing-retrieval/run_poc.py                 # 전부
    python poc/mq2-spacing-retrieval/run_poc.py --arms B0 B2a   # 일부만
    python poc/mq2-spacing-retrieval/run_poc.py --limit 5       # 빠른 확인

**중간 결과를 전부 보존한다**(`results.json`). 원본 입력·각 arm의 출력·근거·정오를
그대로 남겨야 나중에 실패 사례를 다시 볼 수 있다.

성공 기준(`PROBLEM.md` §5)을 그대로 계산해 출력한다. 기준은 실행 전에 정했고 여기서
바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import arms  # noqa: E402

DATASET = HERE / "dataset.jsonl"
RESULTS = HERE / "results.json"


def load_dataset(limit: int = 0) -> list[dict]:
    items = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    return items[:limit] if limit else items


def normalize(s: str) -> str:
    """비교 전 공백을 정규화한다. 자잘한 차이로 정오가 갈리면 안 된다."""
    return " ".join(s.split())


def evaluate(items: list[dict], arm_names: list[str]) -> dict:
    report: dict = {"arms": {}, "cases": []}

    for name in arm_names:
        fn = arms.ARMS[name]
        correct = wrong = unchanged_wrong = cited = 0
        overcorrected = 0
        elapsed = 0.0

        for item in items:
            started = time.time()
            try:
                out, why = fn(item["input"], item.get("word"))
            except Exception as exc:                      # arm 하나가 죽어도 나머지는 잰다
                out, why = item["input"], [f"오류: {type(exc).__name__}"]
            elapsed += time.time() - started

            ok = normalize(out) == normalize(item["gold"])
            # 이미 맞는 문장을 건드렸는가 — 과잉교정. 이 도구에서 가장 나쁜 실패다.
            already_correct = normalize(item["input"]) == normalize(item["gold"])
            # **기권과 오답을 근거 유무로 가른다.** 출력이 입력과 같다는 것만으로는
            # 갈리지 않는다 — 판정을 내렸는데 그 판정이 마침 원문과 같을 수 있고,
            # 그건 기권이 아니라 틀린 판정이다(2026-08-12 5건 예행에서 드러남).
            abstained = not why
            if ok:
                correct += 1
            else:
                wrong += 1
                if already_correct:
                    overcorrected += 1
                if abstained:
                    unchanged_wrong += 1                 # 판정 자체를 안 한 것
            if why:
                cited += 1

            report["cases"].append({
                "id": item["id"], "arm": name, "word": item.get("word"),
                "input": item["input"], "gold": item["gold"], "output": out,
                "correct": ok, "overcorrected": (not ok) and already_correct,
                "difficulty": item.get("difficulty"), "evidence": why,
            })

        total = len(items)
        report["arms"][name] = {
            "총건수": total,
            "정답": correct,
            "정확도": round(correct / total, 3) if total else 0.0,
            "오답": wrong,
            "기권해서_틀림": unchanged_wrong,
            "판정_오답": wrong - unchanged_wrong,
            "오답률": round((wrong - unchanged_wrong) / total, 3) if total else 0.0,
            "과잉교정": overcorrected,
            "근거_제시율": round(cited / total, 3) if total else 0.0,
            "소요초": round(elapsed, 1),
        }
    return report


def print_report(report: dict, items: list[dict]) -> None:
    print("\n" + "=" * 78)
    print(f"평가셋 {len(items)}건 "
          f"(어려움 {sum(1 for i in items if i.get('difficulty') == 'hard')}, "
          f"대조군 {sum(1 for i in items if i.get('difficulty') == 'control')})")
    print("=" * 78)
    head = f"{'arm':5} {'정확도':>8} {'정답':>5} {'판정오답':>8} {'오답률':>7} {'과잉교정':>8} {'근거':>7} {'초':>7}"
    print(head)
    print("-" * 78)
    for name, s in report["arms"].items():
        print(f"{name:5} {s['정확도']:>8.1%} {s['정답']:>5} {s['판정_오답']:>8} "
              f"{s['오답률']:>7.1%} {s['과잉교정']:>8} {s['근거_제시율']:>6.0%} {s['소요초']:>7.1f}")

    # ---- 성공 기준 판정 (PROBLEM.md §5, 실행 전에 정한 것) ----
    if "B0" in report["arms"] and "B2b" in report["arms"]:
        b0, b2 = report["arms"]["B0"], report["arms"]["B2b"]
        print("\n" + "-" * 78)
        print("성공 기준 판정 (실행 전 확정)")
        s1 = b2["정확도"] > b0["정확도"]
        s2 = b2["오답률"] <= 0.05
        s3 = b2["근거_제시율"] >= 0.90
        print(f"  S1 근거검색 정확도 > 현재 시스템   {b2['정확도']:.1%} vs {b0['정확도']:.1%}"
              f"   {'통과' if s1 else '실패'}")
        print(f"  S2 오답률 <= 5%                    {b2['오답률']:.1%}"
              f"{'':16}{'통과' if s2 else '실패'}")
        print(f"  S3 근거 제시율 >= 90%              {b2['근거_제시율']:.0%}"
              f"{'':17}{'통과' if s3 else '실패'}")
        print(f"\n  종합: {'통합할 가치가 있다' if (s1 and s2 and s3) else '통합하지 않는다'}")
    print("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", nargs="*", default=["B0", "B1", "B2a", "B2b"],
                    help="돌릴 arm (기본: B3 제외 — 라이선스 제약으로 결론 근거 아님)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--llm-model", default="", help="B3가 쓸 Ollama 모델")
    ap.add_argument("-o", "--out", default=str(RESULTS))
    args = ap.parse_args()

    if args.llm_model:
        arms.LLM_MODEL = args.llm_model      # B3 모델 교체(라이선스 대안 비교용)
        print(f'B3 모델: {arms.LLM_MODEL}')
    items = load_dataset(args.limit)
    print(f"평가셋 {len(items)}건, arm {args.arms}")
    report = evaluate(items, args.arms)
    print_report(report, items)

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n상세 결과: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
