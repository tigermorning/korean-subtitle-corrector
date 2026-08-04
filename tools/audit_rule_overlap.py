"""붙임 규칙과 분리 규칙의 **관할 겹침**을 코퍼스에서 전수로 뽑는다
(`docs/BACKLOG.md` 29번).

**왜 필요한가**: 같은 어절 경계('생각'+'하')를 세 규칙이 서로 반대 방향으로 만진다.

    correct_particle_spacing        '생각 해' -> '생각해'   (제41항, '하'가 XSV라 붙임)
    correct_adnominal_noun_verb_split '생각해' -> '생각 해'  (관형어가 명사를 꾸미면 가름)
    correct_action_noun_affix       '생각 해' -> '생각해'   (동작성 명사 + 접사)

지금은 파이프라인 호출 순서(붙임 -> 분리 -> 접사 붙임)가 최종 결과를 정한다. 순서에
기대는 설계가 옳은지는 두 가지를 재야 알 수 있다.

  1. **순서 의존**: 두 규칙을 반대 순서로 돌리면 결과가 달라지는가(A(B(x)) != B(A(x)))?
  2. **원문 띄어쓰기 의존**: 같은 문장을 붙여 쓴 것과 띄어 쓴 것이 같은 결과로
     모이는가? 갈리면 사용자가 보는 출력이 원문 표기에 따라 달라진다 —
     29번이 지적한 그 문제다.

     '생각 해'(띄어 쓴 원문)  -> 파이프라인 -> ?
     '생각해'(붙여 쓴 원문)   -> 파이프라인 -> ?   두 결과가 같아야 한다.

  3. **고정점**: 파이프라인 출력을 다시 넣으면 더 바뀌는가? 바뀌면 규칙들이 서로를
     되돌리는 진동이다.

**판정은 사람이 한다** — 이 도구는 겹치는 입력과 그 결과를 전부 보여 줄 뿐이다.

    python tools/audit_rule_overlap.py            # 전체 코퍼스
    python tools/audit_rule_overlap.py --limit 100
    python tools/audit_rule_overlap.py --probe    # 겹침 사례에 띄어쓰기 변형까지 실측
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from subtitle_corrector.engine import (  # noqa: E402
    correct_action_noun_affix,
    correct_adnominal_noun_verb_split,
    correct_particle_spacing,
)
from subtitle_corrector.engine.kiwi_adapter import _kiwi  # noqa: E402

from audit_auto_rules import is_prose_line  # noqa: E402
from diff_behavior import build_corpus  # noqa: E402


def particle(text: str) -> str:
    return correct_particle_spacing(text)[0]


def split_adnominal(text: str) -> str:
    return correct_adnominal_noun_verb_split(text)[0]


def affix(text: str) -> str:
    return correct_action_noun_affix(text)[0]


def pipeline_order(text: str) -> str:
    """파이프라인이 실제로 이 세 규칙을 부르는 순서(pipeline.py:188~195)."""
    return affix(split_adnominal(particle(text)))


def boundary_positions(text: str) -> list[int]:
    """'명사(NNG/NNP) + 하(XSV)' 경계 위치를 (붙어 있든 띄어 있든) 모아 준다.
    이 자리가 세 규칙의 관할이 겹치는 지점이다."""
    positions = []
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        noun, hae = tokens[i - 1], tokens[i]
        if hae.tag != "XSV" or noun.tag not in ("NNG", "NNP"):
            continue
        gap = text[noun.start + noun.len : hae.start]
        if gap not in ("", " "):
            continue
        positions.append(noun.start + noun.len)
    return positions


def spacing_variant(text: str, pos: int) -> str | None:
    """경계 pos의 띄어쓰기를 뒤집은 원문을 만든다(붙임 <-> 띄움).
    같은 문장을 사용자가 반대로 써 왔을 때를 재현하려는 것이다."""
    if pos >= len(text) and pos != len(text):
        return None
    if text[pos : pos + 1] == " ":
        return text[:pos] + text[pos + 1 :]
    return text[:pos] + " " + text[pos:]


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    probe = "--probe" in sys.argv

    corpus = [l for l in build_corpus() if is_prose_line(l)]
    if limit:
        corpus = corpus[:limit]

    order_matters = []  # 두 규칙의 순서를 바꾸면 결과가 다른 줄
    both_touch = []  # 붙임과 분리가 같은 줄을 서로 반대로 만지는 줄
    not_fixed = []  # 출력을 다시 넣으면 또 바뀌는 줄
    variant_diverges = []  # 띄어쓰기만 다른 같은 문장이 다른 결과로 갈리는 줄

    for line in corpus:
        p, s = particle(line), split_adnominal(line)
        forward = split_adnominal(p)  # 파이프라인 순서(붙임 -> 분리)
        backward = particle(s)  # 뒤집은 순서
        if forward != backward:
            order_matters.append((line, forward, backward))
        if p != line and split_adnominal(p) != p:
            both_touch.append((line, p, split_adnominal(p)))

        out = pipeline_order(line)
        again = pipeline_order(out)
        if again != out:
            not_fixed.append((line, out, again))

        if probe:
            for pos in boundary_positions(line):
                variant = spacing_variant(line, pos)
                if variant is None or variant == line:
                    continue
                if pipeline_order(variant) != out:
                    variant_diverges.append((line, out, variant, pipeline_order(variant)))

    print(f"코퍼스 {len(corpus)}줄\n")
    print(f"{'검사':<28} {'건수':>5}")
    print("-" * 34)
    print(f"{'순서 바꾸면 결과 다름':<28} {len(order_matters):>5}")
    print(f"{'붙임을 분리가 되돌림':<28} {len(both_touch):>5}")
    print(f"{'출력이 고정점 아님':<28} {len(not_fixed):>5}")
    if probe:
        print(f"{'원문 띄어쓰기에 따라 갈림':<28} {len(variant_diverges):>5}")

    def dump(title: str, rows: list, cols: tuple[str, ...]) -> None:
        if not rows:
            return
        print(f"\n## {title} ({len(rows)}건)")
        for row in rows:
            print()
            for name, value in zip(cols, row):
                print(f"  {name:<12} {value!r}")

    dump("순서 바꾸면 결과 다름", order_matters, ("원문", "붙임->분리", "분리->붙임"))
    dump("붙임을 분리가 되돌림", both_touch, ("원문", "붙임 후", "분리 후"))
    dump("출력이 고정점 아님", not_fixed, ("원문", "1회", "2회"))
    dump(
        "원문 띄어쓰기에 따라 갈림",
        variant_diverges,
        ("원문", "원문 결과", "표기 변형", "변형 결과"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
