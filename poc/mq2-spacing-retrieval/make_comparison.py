"""결과 원자료에서 큐별 대조표(정성 자료)를 만든다.

숫자만으로는 "무엇이 어떻게 달라졌는가"가 안 보인다. 이 표가 그것을 보여 준다 —
같은 문장에 대해 arm마다 무엇을 내놓았는지 나란히 놓는다.

    python poc/mq2-spacing-retrieval/make_comparison.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 실험 1(제42항 이중 기능 단어)과 실험 2(실사용 오교정)는 평가셋이 달라 표를 나눈다.
EXPERIMENTS = {
    "comparison.md": (
        "실험 1 — 제42항 이중 기능 단어",
        {"results.json": None, "results_b3.json": "B3(EXAONE)",
         "results_b3_qwen.json": "B3(Qwen)"},
        ["B0", "B1", "B2a", "B2b", "B3(EXAONE)", "B3(Qwen)"],
    ),
    "comparison_realusage.md": (
        "실험 2 — 사용자가 실제로 보고한 오교정",
        {"results_realusage.json": None},
        ["B0", "B4a", "B4b"],
    ),
}


def load(files: dict) -> dict:
    by: dict = {}
    for fname, rename in files.items():
        path = HERE / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for case in data["cases"]:
            arm = rename or case["arm"]
            by.setdefault(case["id"], {})[arm] = case
    return by


def mark(case: dict) -> str:
    if case["correct"]:
        return "O"
    return "X!" if case["overcorrected"] else "X"


def build(title: str, files: dict, order: list, out_name: str) -> bool:
    by = load(files)
    if not by:
        return False
    arms = [a for a in order if any(a in v for v in by.values())]

    lines = [
        f"# 큐별 대조표 — {title}",
        "",
        "`run_poc.py` 결과에서 자동 생성. `make_comparison.py`로 다시 만들 수 있다.",
        "",
        "기호: `O` 정답 / `X` 오답 / `X!` **이미 맞는 문장을 망가뜨림(과잉교정)**",
        "",
        "| id | 난이도 | 입력 | 정답 | " + " | ".join(arms) + " |",
        "|---|---|---|---|" + "---|" * len(arms),
    ]
    for cid in sorted(by):
        row = by[cid]
        any_case = next(iter(row.values()))
        cells = []
        for a in arms:
            c = row.get(a)
            cells.append("—" if c is None else mark(c))
        lines.append(
            f"| {cid} | {any_case['difficulty']} | `{any_case['input']}` | "
            f"`{any_case['gold']}` | " + " | ".join(cells) + " |"
        )

    # 틀린 것만 실제 출력을 보여 준다 — 무엇으로 잘못 고쳤는지가 핵심이다.
    lines += ["", "## 오답 상세 — 무엇으로 잘못 고쳤는가", ""]
    for cid in sorted(by):
        wrong = {a: c for a, c in by[cid].items() if not c["correct"]}
        if not wrong:
            continue
        any_case = next(iter(by[cid].values()))
        lines.append(f"**{cid}** (`{any_case['input']}` → 정답 `{any_case['gold']}`)")
        lines.append("")
        for a, c in wrong.items():
            tag = " **[과잉교정]**" if c["overcorrected"] else ""
            why = c["evidence"][0] if c["evidence"] else "(판정 안 함 — 기권)"
            lines.append(f"- `{a}` → `{c['output']}`{tag}")
            lines.append(f"  - 고른 근거: {why}")
        lines.append("")

    out = HERE / out_name
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{title}: {len(by)}건 -> {out.name}  arm={arms}")
    return True


def main() -> int:
    made = 0
    for name, (title, files, order) in EXPERIMENTS.items():
        if build(title, files, order, name):
            made += 1
    if not made:
        print("결과 파일이 없다. 먼저 run_poc.py를 돌려라.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
