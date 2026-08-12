"""언어 모델 패스를 평가셋으로 재는 도구(2026-08-12).

**무엇을 묻는가.** "로컬 언어 모델이 한국어 교정에 도움이 되는가"는 의견으로 답할
물음이 아니다. 이 도구가 세 가지를 숫자로 낸다.

    ① 게이트 통과율     모델이 낸 제안 중 몇 개가 edit_guard를 통과하는가
    ② 정답 일치         통과한 제안이 평가셋 gold와 맞는가
    ③ 표준어 침범 건수  **모델이 이미 표준인 표기를 바꾸려 한 횟수** ← 판정 기준

③이 핵심이다. 국립국어원이 이미 인정한 표기(표준국어대사전 표제어)를 모델이 다른
표기로 바꾸려 든다면, 그건 교정이 아니라 **맞는 표기를 다른 맞는 표기로 바꾸는 임의
치환**이고 이 프로젝트가 처음부터 금지한 것이다(`options.py`의 구두점 기본값을
`keep`으로 되돌린 이유, 평가셋 t12 `도리어`→`되레` 거부).

판정은 사람이 하지만 근거는 국립국어원이 준다 — 하드코딩한 복수 표준어 목록을 쓰지
않고, 모델이 **없앤 낱말**을 kiwi로 기본형까지 되돌린 뒤 표준국어대사전에 조회한다
(`invaded_standard`). 목록은 낡지만 조회는 오늘 것을 준다.

③은 **게이트가 막은 제안까지 포함해서** 센다. 살아남은 것만 세면 "게이트가 막아
줬다"가 "위험이 없다"로 잘못 읽힌다 — 실제로 첫 실행에서 그 착오가 났다.

실행:
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --model exaone3.5:7.8b
    .venv\\Scripts\\python.exe tools\\audit_llm_pass.py --limit 10 --raw   (빠른 확인)
"""

import argparse
import json
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
from subtitle_corrector.engine.llm_pass import propose_corrections  # noqa: E402
from subtitle_corrector.parsers import SubtitleEntry  # noqa: E402

# 차단 문구에서 원문과 제안을 다시 꺼내는 자리. 처음에는 살아남은 제안만 ③으로
# 검사했는데, 그러면 **게이트가 먼저 막은 것이 통째로 안 보인다**(2026-08-12 실측:
# 4건 전부 차단돼 ③이 0건으로 나왔고, 그 안에 '달궜다 -> 달렸다'라는 훼손이
# 들어 있었다). 게이트가 막아 준 것과 위험이 없는 것은 전혀 다른 말이다.
_BLOCK_PAIR = re.compile(r"'([^']*)'\s*->\s*'([^']*)'")

EVAL_DIR = ROOT / "examples" / "eval"


def load_corpus(limit: int = 0) -> list[dict]:
    """평가셋 두 벌을 합쳐 읽는다. 파일 이름을 함께 들고 다닌다."""
    items = []
    for path in sorted(EVAL_DIR.glob("*.jsonl")):
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
    return items[:limit] if limit else items


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
}


def classify_block(message: str) -> str:
    for needle, label in _BLOCK_KINDS.items():
        if needle in message:
            return label
    return "기타"


def audit(items: list[dict], settings, show_raw: bool = False) -> dict:
    total_proposals = 0
    gate_blocked = 0
    gold_match = 0
    gold_miss = 0
    blocks: dict[str, int] = {}
    standard_hits: list[tuple[str, str, str]] = []
    blocked_samples: list[str] = []
    samples: list[dict] = []

    for i, item in enumerate(items, 1):
        text = item.get("input") or ""
        if not text.strip():
            continue
        entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:04,000", text=text)

        # 규칙 교정을 먼저 끝낸다. 모델이 보는 것은 그 결과다 — 실사용과 같은 조건.
        corrected, _flags, _log = correct_entries([entry], doc_type="subtitle")
        after_rules = corrected[0].text

        proposals, notes = propose_corrections(corrected, settings)
        blocked_here = 0
        for note in notes:
            if "차단" not in note.message:
                continue
            blocked_here += 1
            kind = classify_block(note.message)
            blocks[kind] = blocks.get(kind, 0) + 1
            if len(blocked_samples) < 20:
                blocked_samples.append(f"{item.get('id', '?')} [{kind}] {note.message}")
            # 막힌 제안도 ③에 넣는다. 게이트가 막아 준 것은 "위험이 없었다"가 아니라
            # "이번에는 막혔다"이고, 모델이 형식만 갖추면 그대로 통과할 것들이다.
            pair = _BLOCK_PAIR.search(note.message)
            if pair:
                for lemma in invaded_standard(pair.group(1), pair.group(2)):
                    standard_hits.append((item.get("id", "?"), lemma,
                                          f"{pair.group(2)} (게이트 차단됨)"))
        gate_blocked += blocked_here
        total_proposals += len(proposals) + blocked_here

        print(f"[{i}/{len(items)}] {item.get('id', '?')} "
              f"제안 {len(proposals)} / 차단 {blocked_here}", flush=True)

        for flag in proposals:
            gold = item.get("gold")
            if gold:
                if flag.suggested_fix.strip() == gold.strip():
                    gold_match += 1
                else:
                    gold_miss += 1

            # ③ 국립국어원에 직접 묻는다: 모델이 없앤 낱말이 이미 표제어였는가.
            for lemma in invaded_standard(flag.original_text, flag.suggested_fix):
                standard_hits.append((item.get("id", "?"), lemma, flag.suggested_fix))

            samples.append({
                "id": item.get("id", "?"),
                "input": text,
                "after_rules": after_rules,
                "proposed": flag.suggested_fix,
                "gold": item.get("gold", ""),
                "reason": flag.reason,
            })

        if show_raw:
            for note in notes:
                print(f"    · {note.message}", flush=True)

    return {
        "items": len(items),
        "total_proposals": total_proposals,
        "gate_blocked": gate_blocked,
        "survived": total_proposals - gate_blocked,
        "gold_match": gold_match,
        "gold_miss": gold_miss,
        "blocks": blocks,
        "blocked_samples": blocked_samples,
        "standard_hits": standard_hits,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--backend", default="auto", choices=["auto", "http", "cli"])
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 이만큼만")
    parser.add_argument("--raw", action="store_true", help="차단 사유를 전부 찍는다")
    parser.add_argument("-o", "--out", default="", help="상세 결과를 JSON으로 저장")
    args = parser.parse_args()

    settings = normalize_llm_settings(
        enabled=True, model=args.model, backend=args.backend, batch_size=1
    )
    if not settings.enabled:
        print("모델에 닿을 수 없습니다. LLM_BASE_URL을 지정하거나 ollama를 설치하세요.")
        return 1
    print(f"모델 {settings.model} / 경로 {settings.backend}\n")

    items = load_corpus(args.limit)
    result = audit(items, settings, args.raw)

    survived = result["survived"]
    print("\n" + "=" * 62)
    print(f"평가 문장            {result['items']}건")
    print(f"모델이 낸 제안       {result['total_proposals']}건")
    print(f"  게이트가 차단      {result['gate_blocked']}건")
    for kind, count in sorted(result["blocks"].items(), key=lambda kv: -kv[1]):
        print(f"      {kind:<14} {count}건")
    print(f"  목록에 오름        {survived}건")
    if result["gold_match"] or result["gold_miss"]:
        print(f"정답(gold) 일치      {result['gold_match']}건 / "
              f"불일치 {result['gold_miss']}건")
    print("-" * 62)
    hits = result["standard_hits"]
    print(f"③ 표준어 침범        {len(hits)}건  (차단된 제안 포함)  "
          f"{'← 원칙 위반. 탐지기로 강등할 근거다' if hits else '← 없음'}")
    for item_id, source, fix in hits[:15]:
        print(f"    {item_id}: '{source}'은(는) 이미 표준국어대사전 표제어인데 "
              f"바꾸려 했다 -> {fix}")
    print("=" * 62)

    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"상세 결과: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
