"""held-out 평가셋에 새 항목을 넣기 전에, 정답 라벨을 사전으로 검증한다.

**왜 필요한가**: 평가셋의 gold가 틀리면 정확도 숫자 자체가 거짓이 된다. 엔진을
고치는 게 아니라 눈금자를 휘게 만드는 것이라 더 위험하다. `.claude/skills/
grammar-rule-verify-then-code`가 교정 규칙에 요구하는 "검증표 먼저"를 평가셋
라벨에도 똑같이 적용한다.

낱말의 표준어 여부를 표준국어대사전·우리말샘으로 조회해 아래 셋 중 하나로 찍는다.

- `표준`   : 표준국어대사전 표제어이거나 우리말샘의 표준어 항목
- `비표준` : 어느 사전에도 표제어로 없거나, 우리말샘이 "규범 표기는 ~" 안내를 단 항목
- `조회불가`: API 오류 등으로 판정 못 함 (라벨 근거로 쓰지 말 것)

    python tools/verify_eval_labels.py 로보트 로봇 몇일 며칠
    python tools/verify_eval_labels.py --file examples/eval/candidates.txt

`--file`은 `비표준<탭 또는 공백>표준` 쌍을 한 줄에 하나씩 적은 파일을 받아
"고칠 말은 실제로 비표준이고, 고친 말은 실제로 표준인가"를 쌍 단위로 판정한다.
쌍 검사에서 OK가 아닌 줄은 평가셋에 넣지 말 것.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from subtitle_corrector.dictionary.clients import (  # noqa: E402
    search_opendict,
    search_stdict,
)
from subtitle_corrector.dictionary.headwords import (  # noqa: E402
    _opendict_item_is_standard,
    is_contemporary_general_word,
)


def _with_sense_list(item: dict) -> dict:
    """표준국어대사전은 뜻이 하나면 `sense`를 리스트가 아니라 객체로 준다.
    우리말샘은 항상 리스트라 엔진 쪽 판정 함수는 리스트만 받는다 — 여기서 맞춘다."""
    sense = item.get("sense")
    if isinstance(sense, dict):
        return {**item, "sense": [sense]}
    return item


def _stdict_item_is_standard(item: dict) -> bool:
    """표준국어대사전 항목이 '표준 표기'로 등재된 것인지.

    이 사전은 비표준 표기도 표제어로 싣고 뜻풀이를 화살표 한 줄로만 적는다
    ('설겆-이' -> "→ 설거지."). 우리말샘의 "⇒규범 표기는 ~" 안내와 문구가 달라서
    엔진 쪽 판정(`_opendict_item_is_standard`)만으로는 걸러지지 않는다 —
    이 도구를 만들며 '설겆이·초콜렛·컨텐츠'가 모두 '표준'으로 잘못 찍혀 발견했다.
    뜻이 여럿이면 화살표가 아닌 뜻이 하나라도 있을 때 표준으로 본다."""
    senses = item.get("sense", [])
    if not senses:
        return True
    for sense in senses:
        definition = (sense.get("definition") or "").strip()
        if definition.startswith("→") or definition.startswith("⇒"):
            continue
        if "북한어" in definition:
            continue
        return True
    return False


def status(word: str) -> tuple[str, str]:
    """(판정, 근거) 를 돌려준다."""
    try:
        std = search_stdict(word)
    except Exception as exc:  # API 키 없음·네트워크 오류 등
        return "조회불가", f"표준국어대사전 조회 실패: {exc}"

    # 표준국어대사전도 '설겆이'·'로보트'류 비표준 표기를 표제어로 싣는다.
    # 표제어가 잡혔다는 사실만으로 표준으로 보면 안 된다.
    for item in std.get("channel", {}).get("item", []) or []:
        if item.get("word", "").replace("-", "").replace("^", "") != word:
            continue
        if _stdict_item_is_standard(_with_sense_list(item)):
            pos = item.get("pos", "")
            return "표준", f"표준국어대사전 표제어({pos})" if pos else "표준국어대사전 표제어"

    try:
        opend = search_opendict(word)
    except Exception as exc:
        return "조회불가", f"우리말샘 조회 실패: {exc}"

    saw_nonstandard = False
    saw_regional = False
    for item in opend.get("channel", {}).get("item", []) or []:
        if item.get("word", "").replace("-", "").replace("^", "") != word:
            continue
        if not _opendict_item_is_standard(item):
            saw_nonstandard = True
            continue
        # '깨끗히'·'움추리다'는 우리말샘에 "'깨끗이'의 방언"으로 실려 있다.
        # 재지정 안내가 아니라 표제어라 위 판정은 표준으로 보지만, 평가셋
        # 라벨 근거로는 못 쓴다 — 이 엔진은 지역어를 보호 대상으로 다루므로
        # 고쳐야 할 오표기인지 살릴 사투리인지가 라벨 하나로 갈리지 않는다.
        if is_contemporary_general_word(word):
            return "표준", "우리말샘 표준어 항목"
        saw_regional = True

    if saw_regional:
        return "지역어·옛말", "우리말샘 표제어이나 방언·옛말·북한어 뜻뿐 (라벨 근거로 쓰지 말 것)"
    if saw_nonstandard:
        return "비표준", "우리말샘에 있으나 규범 표기가 따로 있음"
    return "비표준", "두 사전 모두 표제어 없음"


def report_words(words: list[str]) -> int:
    worst = 0
    for word in words:
        verdict, why = status(word)
        if verdict == "조회불가":
            worst = max(worst, 2)
        print(f"{word:12} {verdict:6} {why}")
    return worst


def report_pairs(path: Path) -> int:
    bad = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"[형식오류] {raw}")
            bad += 1
            continue
        wrong, right = parts
        wrong_verdict, wrong_why = status(wrong)
        right_verdict, right_why = status(right)
        ok = wrong_verdict == "비표준" and right_verdict == "표준"
        mark = "OK" if ok else "확인필요"
        if not ok:
            bad += 1
        print(
            f"{wrong:10} -> {right:10} {mark:6} "
            f"| 입력={wrong_verdict}({wrong_why}) | 정답={right_verdict}({right_why})"
        )
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--file":
        return report_pairs(Path(args[1]))
    return report_words(args)


if __name__ == "__main__":
    raise SystemExit(main())
