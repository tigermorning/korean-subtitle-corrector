"""Held-out 정확도 평가 하네스.

examples/eval/heldout.jsonl 의 각 문장을 교정 엔진에 통과시켜
gold(정답)와 정확 일치하는지, 사투리/함정 항목의 플래그 기대가
맞는지 검사한다. 카테고리별·전체 통과율과, 기대 행동(고침/플래그/유지) 대
실제 행동 혼동표, 위험한 실패(과교정·오교정), 정답 재투입 결과를 출력한다.

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
    # 규정이 둘 다 맞다고 한 자리가 있다. 하나만 정답으로 두면 맞는 답을 틀렸다고
    # 센다 — 작업자 자료에는 (o)가 둘인 항목이 여럿이다(초과근무 했다 / 초과 근무 했다).
    accepted = [gold, *item.get("gold_alt", [])]
    text_ok = got in accepted

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


# 통과/실패 한 줄로는 **어떤 실패인지** 안 보인다. 놓친 것(원문이 그대로 남음)과
# 고치면 안 될 것을 고친 것은 같은 FAIL이지만 무게가 전혀 다르다 — 앞은 사용자가
# 한 번 더 보면 되고, 뒤는 멀쩡한 대사를 망가뜨린다. 그래서 기대 행동과 실제
# 행동을 따로 세서 혼동표로 본다(행=기대, 열=실제).
ACTIONS = ("FIX", "FLAG", "KEEP")


def expected_action(item: dict) -> str:
    if item["input"] != item["gold"]:
        return "FIX"
    return "FLAG" if item.get("expect_flag") else "KEEP"


def actual_action(item: dict, got: str, flags: list) -> str:
    if got != item["input"]:
        return "FIX"
    return "FLAG" if any(f.suggested_fix for f in flags) else "KEEP"


def danger(item: dict, got: str) -> str:
    """사용자가 알아채기 어려운 실패만 이름을 붙여 돌려준다. 없으면 빈 문자열.

    - 과교정: 원문이 맞는데(또는 사람이 볼 자리인데) 텍스트를 바꿨다.
    - 오교정: 고쳐야 하는 자리를 고치긴 했는데 정답이 아닌 쪽으로 바꿨다.
    원문이 그대로 남은 실패(놓침)는 여기 넣지 않는다 — 틀린 텍스트를 새로 만들지는 않았다.
    """
    accepted = [item["gold"], *item.get("gold_alt", [])]
    if got == item["input"] or got in accepted:
        return ""
    return "과교정" if expected_action(item) != "FIX" else "오교정"


def confusion_rows(confusion: dict, expected: str) -> int:
    return sum(confusion[(expected, a)] for a in ACTIONS)


def recheck_gold(item: dict) -> tuple[str, list]:
    """정답 문장을 입력으로 다시 넣는다. 정답이 맞다면 엔진은 그것을 바꾸면 안 된다.

    강의(채점기 자기 검증)에서 가져온 검사다 — 모범 답안이 채점을 통과하지 못하면
    틀린 것은 에이전트가 아니라 자다. 여기서는 방향이 반대로도 읽힌다: 정답을 넣었는데
    텍스트가 바뀌면 gold가 틀렸거나 엔진이 맞는 문장을 과교정하는 것이고, 어느
    쪽이든 사람이 봐야 한다.
    """
    return run_item({**item, "input": item["gold"]})


def main():
    # 코퍼스를 골라 돌린다. 기본은 held-out이고, 작업자 자료 정답지는 따로 둔다
    # — 출처가 다르면 정확도도 따로 읽어야 한다(하나로 합치면 어느 쪽이 나빠졌는지 모른다).
    corpus = Path(sys.argv[1]) if len(sys.argv) > 1 else CORPUS
    if not corpus.is_absolute():
        corpus = Path(__file__).resolve().parent / corpus.name
    print(f"코퍼스: {corpus.name}\n")
    items = [json.loads(l) for l in corpus.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_cat: dict[str, list[bool]] = {}
    to_verify = []
    passed = 0
    confusion = {(e, a): 0 for e in ACTIONS for a in ACTIONS}
    dangers: list[str] = []
    gold_changed: list[str] = []
    gold_flagged: list[str] = []

    print(f"{'id':5} {'cat':22} {'판정':6} 설명")
    print("-" * 78)
    for item in items:
        got, flags = run_item(item)
        ok, why = judge(item, got, flags)
        passed += ok
        by_cat.setdefault(item["category"], []).append(ok)
        if item.get("verify"):
            to_verify.append(item["id"])
        confusion[(expected_action(item), actual_action(item, got, flags))] += 1
        kind = danger(item, got)
        if kind:
            dangers.append(f"{item['id']} [{kind}] {item['input']!r} -> {got!r}")
        mark = "PASS" if ok else "FAIL"
        print(f"{item['id']:5} {item['category']:22} {mark:6} {why}")

        if expected_action(item) == "FIX":
            regot, reflags = recheck_gold(item)
            if regot != item["gold"]:
                gold_changed.append(f"{item['id']} {item['gold']!r} -> {regot!r}")
            elif reflags:
                reasons = "; ".join(f.reason[:50] for f in reflags)
                gold_flagged.append(f"{item['id']} {item['gold']!r} — {reasons}")

    print("-" * 78)
    total = len(items)
    # '정밀도'라고 부르던 값이다. 실제로는 전체 중 통과 비율(정확도)이라 이름을 바로잡았다.
    print(f"\n전체 통과율: {passed}/{total} = {passed / total * 100:.1f}%\n")
    print("카테고리별:")
    for cat, results in sorted(by_cat.items()):
        p = sum(results)
        print(f"  {cat:24} {p}/{len(results)}")

    print("\n행동 혼동표 (행=기대, 열=실제):")
    print(f"  {'':6}" + "".join(f"{a:>6}" for a in ACTIONS))
    for e in ACTIONS:
        print(f"  {e:6}" + "".join(f"{confusion[(e, a)]:6d}" for a in ACTIONS))
    print(f"\n위험한 실패(과교정·오교정): {len(dangers)}건" + ("" if dangers else " — 없음"))
    for line in dangers:
        print(f"  {line}")

    print(f"\n정답 재투입 — 고치는 항목 {confusion_rows(confusion, 'FIX')}건의 gold를 입력으로 다시 넣음")
    print(f"  텍스트가 바뀜: {len(gold_changed)}건 (0이어야 한다 — gold 오류 또는 과교정)")
    for line in gold_changed:
        print(f"    {line}")
    print(f"  플래그가 뜸:   {len(gold_flagged)}건 (실패는 아님 — 맞는 문장에 뜨는 잡음 후보)")
    for line in gold_flagged:
        print(f"    {line}")

    if to_verify:
        print(
            "\n[규정 재확인 필요] gold를 표준국어대사전/국립국어원 API로 재검증할 항목: "
            + ", ".join(to_verify)
        )


if __name__ == "__main__":
    main()
