"""Held-out 정확도 평가 하네스.

examples/eval/heldout.jsonl 의 각 문장을 교정 엔진에 통과시켜
gold(정답)와 정확 일치하는지, 사투리/함정 항목의 플래그 기대가
맞는지 검사한다. 카테고리별·전체 정밀도(precision)를 출력한다.

주의:
- 이 코퍼스는 룰을 만들 때 쓰지 않은 새 문장(held-out)이다. 여기 정확도가
  in-sample(examples/sample.srt)보다 낮게 나오는 것이 정상이며, 그 격차가
  바로 "일반화 성능"이다.
- "verify": true 인 항목의 gold는 표준국어대사전/국립국어원 API로 매 실행 시
  재확인해야 한다(규정 개정 가능). 이 스크립트는 재확인 대상만 표시한다.

실행:  .venv\\Scripts\\python.exe examples\\eval\\run_eval.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from subtitle_corrector.engine import correct_entries  # noqa: E402
from subtitle_corrector.parsers import SubtitleEntry  # noqa: E402

CORPUS = Path(__file__).resolve().parent / "heldout.jsonl"


def run_item(item: dict):
    entry = SubtitleEntry(
        index=1,
        start="00:00:00,000",
        end="00:00:02,000",
        text=item["input"],
        speaker=item.get("speaker"),
    )
    dialect_map = {}
    dialect_modes = {}
    if item.get("speaker") and item.get("region"):
        dialect_map[item["speaker"]] = item["region"]
        if item.get("mode"):
            dialect_modes[item["speaker"]] = item["mode"]

    corrected, flags, _log = correct_entries([entry], dialect_map, dialect_modes)
    got = corrected[0].text
    my_flags = [f for f in flags if f.line_index == entry.index]
    return got, my_flags


def judge(item: dict, got: str, flags: list) -> tuple[bool, str]:
    gold = item["gold"]
    text_ok = got == gold

    # 텍스트가 gold와 다르면 대부분 즉시 실패(함정/protect 포함)
    if not text_ok:
        return False, f"텍스트 불일치: got={got!r}"

    # 플래그 기대 검사
    if item.get("expect_no_flag"):
        if flags:
            return False, f"플래그 나오면 안 되는데 {len(flags)}건 나옴"
        return True, "무변경·무플래그 OK"
    if item.get("expect_flag"):
        has_suggestion = any(f.suggested_fix for f in flags)
        if not has_suggestion:
            return False, "제안 플래그(suggested_fix) 기대했으나 없음"
        return True, "무변경 + 제안 플래그 OK"
    if item.get("trap"):
        return True, "원문 보존(과교정 회피) OK"
    return True, "교정 정확"


def main():
    items = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_cat: dict[str, list[bool]] = {}
    to_verify = []
    passed = 0

    print(f"{'id':5} {'cat':22} {'판정':6} 설명")
    print("-" * 78)
    for item in items:
        got, flags = run_item(item)
        ok, why = judge(item, got, flags)
        passed += ok
        by_cat.setdefault(item["category"], []).append(ok)
        if item.get("verify"):
            to_verify.append(item["id"])
        mark = "PASS" if ok else "FAIL"
        print(f"{item['id']:5} {item['category']:22} {mark:6} {why}")

    print("-" * 78)
    total = len(items)
    print(f"\n전체 정밀도: {passed}/{total} = {passed / total * 100:.1f}%\n")
    print("카테고리별:")
    for cat, results in sorted(by_cat.items()):
        p = sum(results)
        print(f"  {cat:24} {p}/{len(results)}")

    if to_verify:
        print(
            "\n[규정 재확인 필요] gold를 표준국어대사전/국립국어원 API로 재검증할 항목: "
            + ", ".join(to_verify)
        )


if __name__ == "__main__":
    main()
