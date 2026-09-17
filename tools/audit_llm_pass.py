"""언어 모델 패스를 평가셋으로 재는 도구(2026-08-12, 2026-09-16 개편).

**무엇을 묻는가.** "로컬 언어 모델이 한국어 교정에 도움이 되는가"는 의견으로 답할
물음이 아니다. 이 도구가 숫자로 낸다.

    ① 규칙별 정밀도·재현율   전용 평가셋(`examples/eval/llm_pass/llm_pass.jsonl`)의
                              positive(오류 있음)·negative(같은 규칙의 맞는 표기)로 잰다
    ② forbid 위반            규칙과 무관한 구어체 대사에 제안을 낸 횟수 — 0이어야 한다
    ③ 표준어 침범 건수       **모델이 이미 표준인 표기를 바꾸려 한 횟수**

②·③이 핵심이다. 국립국어원이 이미 인정한 표기를 모델이 다른 표기로 바꾸려 든다면
그건 교정이 아니라 임의 치환이고 이 프로젝트가 처음부터 금지한 것이다(`options.py`의
구두점 기본값을 `keep`으로 되돌린 이유, 평가셋 t12 `도리어`→`되레` 거부). ③의 판정
근거는 하드코딩한 목록이 아니라 표준국어대사전 조회다(`invaded_standard`).

②·③과 negative 과교정은 **게이트가 막은 제안까지 포함해서** 따로도 센다. 살아남은
것만 세면 "게이트가 막아 줬다"가 "위험이 없다"로 잘못 읽힌다 — 첫 실행에서 그 착오가 났다.

**2026-09-16에 바꾼 것**(모두의연구소 고객응대 에이전트 과정 검토에서 나온 것):

- 기본 코퍼스를 전용 평가셋으로 바꿨다. 예전 코퍼스(`heldout`·`작업자자료` 71건)에는
  이 패스가 맡는 문장이 4건뿐이었다. `--corpus legacy`로 여전히 돌릴 수 있다.
- 시스템 프롬프트 예시와 같은 표현이 든 문항은 채점에서 뺀다(`prompt_leaks`). 예시로
  보여 준 문제로 시험을 치면 점수가 부풀려진다 — 예: heldout t11 `학생으로서`.
- 배치 크기를 실사용 기본값으로 잰다. 예전엔 `batch_size=1` 고정이라 정작 기본값(4)
  조건을 잰 적이 없었다. `--batch-size`로 바꿔 가며 비교하고, 문항 순서는 `--seed`로
  섞는다(평가셋이 규칙별로 모여 있어 그대로 묶으면 같은 규칙끼리만 한 배치에 든다).
- `--repeat`로 같은 조건을 여러 번 돌려 흔들림을 본다. 배치 크기를 4로 정한 근거가
  크기당 1~2회 실행뿐이었다(`llm_pass._DEFAULT_BATCH_SIZE` 주석).
- `--srt`로 실제 자막을 흘려보낸다. 골라 만든 평가셋은 정답이 정해지는 문장만 담으므로,
  실제 대사 분포에서 줄당 제안이 얼마나 뜨고 무엇이 막히는지는 따로 봐야 한다.

실행:
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --model exaone3.5:7.8b
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --batch-size 1 --repeat 3
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --corpus legacy --limit 10 --raw
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --srt "7강_과제_신서연_ko_TL.srt"
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from subtitle_corrector.dictionary import word_exists  # noqa: E402
from subtitle_corrector.engine import correct_entries, normalize_llm_settings  # noqa: E402
from subtitle_corrector.engine.kiwi_adapter import _content_lemmas  # noqa: E402
from subtitle_corrector.engine.llm_pass import (  # noqa: E402
    _DEFAULT_BATCH_SIZE,
    _SYSTEM_PROMPT,
    propose_corrections,
)
from subtitle_corrector.file_io import parse_file  # noqa: E402
from subtitle_corrector.parsers import SubtitleEntry  # noqa: E402

# 차단 문구에서 원문과 제안을 다시 꺼내는 자리. 처음에는 살아남은 제안만 ③으로
# 검사했는데, 그러면 **게이트가 먼저 막은 것이 통째로 안 보인다**(2026-08-12 실측:
# 4건 전부 차단돼 ③이 0건으로 나왔고, 그 안에 '달궜다 -> 달렸다'라는 훼손이
# 들어 있었다). 게이트가 막아 준 것과 위험이 없는 것은 전혀 다른 말이다.
_BLOCK_PAIR = re.compile(r"'([^']*)'\s*->\s*'([^']*)'")
_BLOCK_LINE = re.compile(r"(\d+)번 줄")

EVAL_DIR = ROOT / "examples" / "eval"
LLM_CORPUS = EVAL_DIR / "llm_pass" / "llm_pass.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        item["_file"] = path.name
        items.append(item)
    return items


def load_corpus(name: str, limit: int = 0) -> list[dict]:
    """`llm`이면 전용 평가셋, `legacy`면 예전 평가셋 두 벌(`examples/eval/*.jsonl`)."""
    if name == "legacy":
        items = [i for path in sorted(EVAL_DIR.glob("*.jsonl")) for i in _read_jsonl(path)]
    else:
        items = _read_jsonl(LLM_CORPUS)
    return items[:limit] if limit else items


def _prompt_example_lines() -> list[str]:
    """시스템 프롬프트의 예시 입력 줄(`번호<탭>내용`)만 꺼낸다."""
    return [m.group(1) for m in re.finditer(r"^\d+\t(.+)$", _SYSTEM_PROMPT, flags=re.M)]


def prompt_leaks(text: str) -> list[str]:
    """문항이 프롬프트 예시와 겹치는 어절을 돌려준다. 비어 있으면 겹치지 않는다.

    어절 단위(문장부호를 뗀 3글자 이상)로 본다. 두 글자 어절(`했다`·`그 일`)까지
    보면 거의 모든 문장이 걸리고, 문장 통째 일치만 보면 `학생으로서 할 일을 했다`처럼
    핵심 표현만 같은 변형을 놓친다.
    """
    def words(s: str) -> set[str]:
        return {w.strip(".,?!…\"'") for w in s.split()} - {""}

    example_words = set().union(*(words(line) for line in _prompt_example_lines()))
    return sorted(w for w in words(text) & example_words if len(w) >= 3)


def invaded_standard(before: str, after: str) -> list[str]:
    """모델이 **없앤 표제어**를 돌려준다. 비어 있으면 표준어를 건드리지 않은 것이다.

    낱말을 그대로 조회하면 활용형(`달궜다`)은 표제어가 아니라 늘 "없음"이 나온다.
    그래서 kiwi로 기본형을 복원한 뒤(`달궜다` -> `달구다`) 표준국어대사전에 묻는다.
    원문에는 있었는데 제안에서 사라진 기본형이 표제어라면, 모델이 **이미 맞는
    낱말**을 다른 것으로 바꾼 것이다.

    판정 근거를 하드코딩한 복수 표준어 목록에서 가져오지 않는 이유: 목록은 낡고
    규범은 개정된다. 조회는 오늘 것을 준다.
    """
    try:
        gone = [w for w in _content_lemmas(before) if w not in set(_content_lemmas(after))]
    except Exception:
        return []
    hits = []
    for lemma in gone:
        try:
            if word_exists(lemma):
                hits.append(lemma)
        except Exception:
            continue
    return hits


# 기각 사유를 갈라 센다. "게이트가 몇 건 막았다"만으로는 무엇을 고쳐야 할지 알 수
# 없다 — 모델이 위험한 짓을 해서 막힌 것과, 형식을 못 맞춰서 막힌 것은 대응이 다르다.
_BLOCK_KINDS = {
    "밝히지 않아": "근거 미기재",
    "근거 없이 낱말을": "근거와 불일치",
    "원문을 다르게 인용": "원문 오인용",
    "줄바꿈 개수": "줄바꿈 변경",
    "재작성": "한 줄 재작성",
    "존재하지 않는 줄": "없는 줄 번호",
    "실제 내용이 그": "이름표 불일치",
    "다루는 규칙이 아니라": "범위 밖 규칙",
    "실제로 없는": "밝힌 변경 없음",
}


def classify_block(message: str) -> str:
    for needle, label in _BLOCK_KINDS.items():
        if needle in message:
            return label
    return "기타"


def run_pass(texts: list[str], settings) -> dict[int, dict]:
    """줄 목록을 규칙 교정 → 모델 패스에 통과시키고, 줄 번호(1부터)별 결과를 모은다.

    반환값: {번호: {"after_rules", "proposals": [FlagItem], "blocked": [(종류, 원문, 제안, 문구)]}}.
    여러 줄을 한 번에 넘기므로 모델 패스가 실사용과 같은 배치 크기로 묶는다.
    """
    entries = [
        SubtitleEntry(index=n, start="00:00:00,000", end="00:00:04,000", text=text)
        for n, text in enumerate(texts, 1)
    ]
    # 규칙 교정을 먼저 끝낸다. 모델이 보는 것은 그 결과다 — 실사용과 같은 조건.
    corrected, _flags, _log = correct_entries(entries, doc_type="subtitle")
    by_line = {e.index: {"after_rules": e.text, "proposals": [], "blocked": []} for e in corrected}
    line_by_text = {e.text.strip(): e.index for e in corrected}

    proposals, notes = propose_corrections(corrected, settings)
    for flag in proposals:
        by_line[flag.line_index]["proposals"].append(flag)
    for note in notes:
        if "차단" not in note.message:
            continue
        pair = _BLOCK_PAIR.search(note.message)
        index = None
        line_match = _BLOCK_LINE.search(note.message)
        if line_match:
            index = int(line_match.group(1))
        elif pair:  # edit_guard 문구에는 줄 번호가 없다 — 원문으로 찾는다
            index = line_by_text.get(pair.group(1).strip())
        if index not in by_line:
            index = 0
            by_line.setdefault(0, {"after_rules": "", "proposals": [], "blocked": []})
        by_line[index]["blocked"].append((
            classify_block(note.message),
            pair.group(1) if pair else "",
            pair.group(2) if pair else "",
            note.message,
        ))
    return by_line


def score_eval(items: list[dict], by_line: dict[int, dict]) -> dict:
    """전용 평가셋 채점. 규칙마다 TP·오교정·놓침·과교정을 세고 forbid 위반을 따로 센다."""
    rules: dict[str, dict] = {}
    forbid = {"lines": 0, "surfaced": 0, "attempted": 0}
    details: list[str] = []
    standard_hits: list[tuple[str, str, str]] = []

    for n, item in enumerate(items, 1):
        got = by_line.get(n, {"proposals": [], "blocked": [], "after_rules": item["input"]})
        fixes = [f.suggested_fix.strip() for f in got["proposals"]]
        attempted = len(got["proposals"]) + len(got["blocked"])
        split = item.get("split")

        for flag in got["proposals"]:
            # gold와 같은 제안은 ③에서 뺀다. 라벨은 사전으로 확인한 정답이고, kiwi가 오류
            # 표기를 다른 표제어로 읽는 일이 있다 — 실측: `받지 안는다 -> 않는다`에서
            # '안는다'를 '안다'(껴안다)로 읽어 정답 제안을 표준어 침범으로 셌다.
            if split == "positive" and flag.suggested_fix.strip() == item["gold"].strip():
                continue
            for lemma in invaded_standard(flag.original_text, flag.suggested_fix):
                standard_hits.append((item["id"], lemma, flag.suggested_fix))
        for _kind, before, after, _msg in got["blocked"]:
            if before:
                for lemma in invaded_standard(before, after):
                    standard_hits.append((item["id"], lemma, f"{after} (게이트 차단됨)"))

        # outscope(패스 범위에서 뺀 규칙의 문항)도 forbid와 같은 잣대다 — 무엇이든 제안하면 위반.
        if split in ("forbid", "outscope"):
            forbid["lines"] += 1
            forbid["surfaced"] += bool(fixes)
            forbid["attempted"] += bool(attempted)
            if attempted:
                details.append(f"{item['id']} [{split} 위반] {item['input']!r} -> {fixes or '(차단됨)'}")
            continue

        bucket = rules.setdefault(item["rule"], {
            "positive": 0, "tp": 0, "wrong": 0, "miss": 0,
            "negative": 0, "overfix": 0, "overfix_attempted": 0, "rule_fixed": 0,
        })
        if split == "positive" and not attempted and got["after_rules"].strip() == item["gold"].strip():
            # 규칙 엔진이 모델 패스 전에 이미 고친 문항. 모델이 볼 오류가 없으니 놓침으로
            # 세면 재현율이 근거 없이 떨어진다(2026-09-17 되/돼 자동 교정 도입, §104).
            # 모델 채점에서 빼고 따로 센다.
            bucket["rule_fixed"] += 1
            continue
        if split == "positive":
            bucket["positive"] += 1
            if item["gold"].strip() in fixes:
                bucket["tp"] += 1
            elif fixes:
                bucket["wrong"] += 1
                details.append(f"{item['id']} [오교정] {item['input']!r} -> {fixes} (gold {item['gold']!r})")
            else:
                bucket["miss"] += 1
        else:
            bucket["negative"] += 1
            bucket["overfix"] += bool(fixes)
            bucket["overfix_attempted"] += bool(attempted)
            if attempted:
                details.append(f"{item['id']} [과교정] {item['input']!r} -> {fixes or '(차단됨)'}")

    for bucket in rules.values():
        surfaced = bucket["tp"] + bucket["wrong"] + bucket["overfix"]
        bucket["precision"] = bucket["tp"] / surfaced if surfaced else None
        bucket["recall"] = bucket["tp"] / bucket["positive"] if bucket["positive"] else None
        p, r = bucket["precision"] or 0.0, bucket["recall"] or 0.0
        bucket["f1"] = 2 * p * r / (p + r) if p + r else 0.0
    macro_f1 = sum(b["f1"] for b in rules.values()) / len(rules) if rules else 0.0
    return {"rules": rules, "macro_f1": macro_f1, "forbid": forbid,
            "details": details, "standard_hits": standard_hits}


def score_legacy(items: list[dict], by_line: dict[int, dict]) -> dict:
    """예전 평가셋 채점 — gold 정확 일치와 표준어 침범만 본다."""
    gold_match = gold_miss = 0
    standard_hits = []
    for n, item in enumerate(items, 1):
        got = by_line.get(n, {"proposals": [], "blocked": []})
        for flag in got["proposals"]:
            if item.get("gold"):
                if flag.suggested_fix.strip() == item["gold"].strip():
                    gold_match += 1
                else:
                    gold_miss += 1
            for lemma in invaded_standard(flag.original_text, flag.suggested_fix):
                standard_hits.append((item.get("id", "?"), lemma, flag.suggested_fix))
        for _kind, before, after, _msg in got["blocked"]:
            if before:
                for lemma in invaded_standard(before, after):
                    standard_hits.append((item.get("id", "?"), lemma, f"{after} (게이트 차단됨)"))
    return {"gold_match": gold_match, "gold_miss": gold_miss, "standard_hits": standard_hits}


def gate_summary(by_line: dict[int, dict]) -> dict:
    surfaced = sum(len(v["proposals"]) for v in by_line.values())
    blocks: dict[str, int] = {}
    samples: list[str] = []
    by_rule: dict[str, int] = {}
    for v in by_line.values():
        for flag in v["proposals"]:
            by_rule[flag.rule] = by_rule.get(flag.rule, 0) + 1
        for kind, _b, _a, message in v["blocked"]:
            blocks[kind] = blocks.get(kind, 0) + 1
            if len(samples) < 20:
                samples.append(f"[{kind}] {message}")
    blocked = sum(blocks.values())
    return {"surfaced": surfaced, "blocked": blocked, "total": surfaced + blocked,
            "blocks": blocks, "by_rule": by_rule, "blocked_samples": samples}


def print_gate(gate: dict) -> None:
    print(f"모델이 낸 제안       {gate['total']}건")
    print(f"  게이트가 차단      {gate['blocked']}건")
    for kind, count in sorted(gate["blocks"].items(), key=lambda kv: -kv[1]):
        print(f"      {kind:<14} {count}건")
    print(f"  목록에 오름        {gate['surfaced']}건  {gate['by_rule'] or ''}")


def print_standard_hits(hits: list) -> None:
    print(f"③ 표준어 침범        {len(hits)}건  (차단된 제안 포함)  "
          f"{'← 원칙 위반. 탐지기로 강등할 근거다' if hits else '← 없음'}")
    for item_id, source, fix in hits[:15]:
        print(f"    {item_id}: '{source}'은(는) 이미 표준국어대사전 표제어인데 바꾸려 했다 -> {fix}")


def _fmt(value) -> str:
    return "  -  " if value is None else f"{value:.2f}"


def print_eval(score: dict, show_details: bool) -> None:
    print(f"{'규칙':<8} {'정밀도':>6} {'재현율':>6} {'F1':>5}  "
          f"{'맞힘':>4} {'오교정':>5} {'놓침':>4} {'과교정(차단 포함)':>16} {'규칙이 먼저 고침':>8}")
    for rule, b in sorted(score["rules"].items()):
        print(f"{rule:<8} {_fmt(b['precision']):>6} {_fmt(b['recall']):>6} {b['f1']:5.2f}  "
              f"{b['tp']:>2}/{b['positive']:<2} {b['wrong']:>5} {b['miss']:>4} "
              f"{b['overfix']:>6}/{b['negative']} ({b['overfix_attempted']}) {b['rule_fixed']:>8}")
    print(f"macro F1             {score['macro_f1']:.3f}")
    f = score["forbid"]
    print(f"② forbid·outscope 위반 {f['surfaced']}/{f['lines']}줄 (차단 포함 {f['attempted']})  "
          f"{'← 0이어야 한다' if f['attempted'] else '← 없음'}")
    if show_details:
        for line in score["details"]:
            print(f"    {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--backend", default="auto", choices=["auto", "http", "cli"])
    parser.add_argument("--corpus", default="llm", choices=["llm", "legacy"],
                        help="llm=전용 평가셋(기본), legacy=heldout·작업자자료")
    parser.add_argument("--srt", nargs="+", default=[], help="평가셋 대신 실제 자막 파일을 흘려보낸다")
    parser.add_argument("--batch-size", type=int, default=_DEFAULT_BATCH_SIZE,
                        help=f"모델 패스 배치 크기 (기본 {_DEFAULT_BATCH_SIZE} = 실사용 기본값)")
    parser.add_argument("--repeat", type=int, default=1, help="같은 조건을 몇 번 돌릴지")
    parser.add_argument("--seed", type=int, default=0, help="문항 순서를 섞는 시드 (-1이면 섞지 않음)")
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 이만큼만")
    parser.add_argument("--raw", action="store_true", help="차단 사유·실패 사례를 전부 찍는다")
    parser.add_argument("-o", "--out", default="", help="상세 결과를 JSON으로 저장")
    args = parser.parse_args()

    settings = normalize_llm_settings(
        enabled=True, model=args.model, backend=args.backend, batch_size=args.batch_size
    )
    if not settings.enabled:
        print("모델에 닿을 수 없습니다. LLM_BASE_URL을 지정하거나 ollama를 설치하세요.")
        return 1
    print(f"모델 {settings.model} / 경로 {settings.backend} / 배치 {settings.batch_size}줄"
          f" / 반복 {args.repeat}회\n")

    results = []

    if args.srt:
        for path in args.srt:
            entries = parse_file(Path(path))
            texts = [e.text for e in entries][: args.limit or None]
            for run in range(args.repeat):
                by_line = run_pass(texts, settings)
                gate = gate_summary(by_line)
                hits = [
                    (str(n), lemma, flag.suggested_fix)
                    for n, v in by_line.items() for flag in v["proposals"]
                    for lemma in invaded_standard(flag.original_text, flag.suggested_fix)
                ]
                print("=" * 62)
                print(f"{Path(path).name} — {len(texts)}줄 (실행 {run + 1}/{args.repeat})")
                print_gate(gate)
                per100 = 100 * gate["surfaced"] / len(texts) if texts else 0.0
                print(f"  100줄당 제안       {per100:.1f}건")
                print_standard_hits(hits)
                if args.raw:
                    for n, v in sorted(by_line.items()):
                        for flag in v["proposals"]:
                            print(f"    {n}: {flag.original_text!r} -> {flag.suggested_fix!r} — {flag.reason}")
                    for sample in gate["blocked_samples"]:
                        print(f"    · {sample}")
                results.append({"file": Path(path).name, "run": run + 1, "lines": len(texts),
                                "gate": gate, "standard_hits": hits})
    else:
        items = load_corpus(args.corpus, args.limit)
        leaked = [(i.get("id", "?"), prompt_leaks(i.get("input", ""))) for i in items]
        leaked = [(item_id, words) for item_id, words in leaked if words]
        if leaked:
            skip = {item_id for item_id, _ in leaked}
            items = [i for i in items if i.get("id", "?") not in skip]
            print("[프롬프트 예시와 겹쳐 채점에서 뺌] "
                  + ", ".join(f"{item_id}({'·'.join(words)})" for item_id, words in leaked) + "\n")
        items = [i for i in items if (i.get("input") or "").strip()]
        if args.seed >= 0:
            random.Random(args.seed).shuffle(items)

        macro = []
        for run in range(args.repeat):
            by_line = run_pass([i["input"] for i in items], settings)
            gate = gate_summary(by_line)
            print("=" * 62)
            print(f"{args.corpus} 평가 {len(items)}건 (실행 {run + 1}/{args.repeat})")
            print_gate(gate)
            print("-" * 62)
            if args.corpus == "legacy":
                score = score_legacy(items, by_line)
                print(f"정답(gold) 일치      {score['gold_match']}건 / 불일치 {score['gold_miss']}건")
            else:
                score = score_eval(items, by_line)
                print_eval(score, args.raw)
                macro.append(score["macro_f1"])
            print_standard_hits(score["standard_hits"])
            if args.raw:
                for sample in gate["blocked_samples"]:
                    print(f"    · {sample}")
            results.append({"run": run + 1, "gate": gate,
                            "score": {k: v for k, v in score.items()}})
        if len(macro) > 1:
            print("=" * 62)
            print(f"macro F1 {args.repeat}회: " + ", ".join(f"{m:.3f}" for m in macro)
                  + f"  (최소 {min(macro):.3f} / 최대 {max(macro):.3f})")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                                  encoding="utf-8")
        print(f"상세 결과: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
