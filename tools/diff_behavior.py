"""리팩터링 전후 동작이 **완전히 같은지** 바이트 단위로 증명하는 도구.

왜 필요한가: 테스트 통과는 "테스트가 보는 것"만 보장한다. 구조를 바꾸는 작업
(모듈 분할, 함수 이동)에서 필요한 보장은 그보다 강하다 — **어떤 입력에도 결과가
같아야 한다**. 이 도구는 실제 코퍼스를 여섯 가지 설정 조합으로 통과시켜 교정문·
자동 교정 로그·플래그를 전부 JSON으로 덤프한다. 두 덤프의 SHA256이 같으면
동작이 같다.

사용법:

    # 1) 옛 코드를 다른 경로에 꺼내 놓는다
    git archive <옛-커밋> | tar -x -C /tmp/old_tree

    # 2) 양쪽에서 같은 덤프를 뜬다 (PYTHONPATH로 트리를 고른다)
    PYTHONPATH=/tmp/old_tree python tools/diff_behavior.py dump /tmp/old.json
    PYTHONPATH=. python tools/diff_behavior.py dump /tmp/new.json

    # 3) 대조
    python tools/diff_behavior.py compare /tmp/old.json /tmp/new.json

주의: 이 도구는 실시간 사전 API를 호출한다. 두 덤프가 다르면 먼저 같은 트리에서
두 번 떠서 대조해 볼 것 — API 일시 장애로 인한 차이와 코드로 인한 차이를 구분해야
한다(`search_stdict` 등은 통신 실패를 "찾지 못함"으로 삼킨다).

코퍼스는 `tests/`의 한글 문자열 리터럴 + `examples/`의 예제 자막 + held-out
평가셋에서 만든다. 이 저장소가 실제로 회귀를 고정해 온 문장들이라, 새 규칙이
추가될 때마다 코퍼스도 저절로 넓어진다.
"""

import ast
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANGUL = re.compile(r"[가-힣]")

# 콘솔이 cp949면 대조 결과를 찍다가 UnicodeEncodeError로 죽는다(줄표 '—' 하나에
# 터졌다, 2026-08-03). 덤프까지 다 돌려 놓고 마지막 출력에서 잃는 건 아깝다.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build_corpus() -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip()
        if not s or len(s) > 200 or not HANGUL.search(s) or s in seen:
            return
        seen.add(s)
        lines.append(s)

    for f in sorted((ROOT / "tests").glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                add(node.value)
    for name in ("sample.srt", "sample_dialect.srt"):
        path = ROOT / "examples" / name
        if path.exists():
            for raw in path.read_text(encoding="utf-8-sig").splitlines():
                add(raw)
    heldout = ROOT / "examples" / "eval" / "heldout.jsonl"
    if heldout.exists():
        for raw in heldout.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                item = json.loads(raw)
                for key in ("text", "input", "original"):
                    if key in item:
                        add(item[key])
    return lines


# 설정 조합. 교정 결과를 바꾸는 축(사용목적·제47항 기준·사투리 지정 방식·자막 표지)을
# 각각 한 번씩은 태운다.
def _combos():
    from subtitle_corrector.engine import (
        normalize_punctuation_style,
        normalize_subtitle_markers,
    )

    return {
        "A_subtitle_principle": dict(
            doc_type="subtitle", spacing_mode="principle",
            style=normalize_punctuation_style("char", "full"),
            markers=normalize_subtitle_markers('"', "|", r"{\an8}", "[]", "()"),
        ),
        "B_subtitle_allowance": dict(doc_type="subtitle", spacing_mode="allowance"),
        "C_prose_principle": dict(doc_type="prose", spacing_mode="principle"),
        "D_dialect_to_standard": dict(
            doc_type="subtitle", spacing_mode="principle",
            dialect_region="경상도", dialect_mode="to_standard",
        ),
        "E_dialect_assist": dict(
            doc_type="subtitle", spacing_mode="principle",
            dialect_region="전라도", dialect_mode="assist",
        ),
        "F_speaker_map": dict(
            doc_type="subtitle", spacing_mode="principle",
            dialect_map={"민수": "경상도", "영희": "제주도"},
            dialect_modes={"민수": "to_standard", "영희": "protect"},
        ),
    }


def dump(out_path: Path) -> None:
    from subtitle_corrector.engine import correct_entries
    from subtitle_corrector.parsers import SubtitleEntry

    lines = build_corpus()

    def entries():
        # 화자를 섞어 넣어 화자 승계·화자별 사투리 경로까지 태운다.
        return [
            SubtitleEntry(
                index=i + 1,
                start="00:00:%02d,000" % (i % 60),
                end="00:00:%02d,000" % ((i % 60) + 1),
                text=text,
                speaker=("민수" if i % 7 == 0 else ("영희" if i % 11 == 0 else None)),
            )
            for i, text in enumerate(lines)
        ]

    result = {}
    for name, kwargs in _combos().items():
        corrected, flags, applied = correct_entries(entries(), **kwargs)
        result[name] = {
            "texts": [e.text for e in corrected],
            # 옛 커밋의 덤프와 대조해야 하므로 사람이 읽는 한 줄로 눌러 담는다
            # (2026-08-04에 applied_log가 AppliedNote 목록이 됐다).
            "applied_log": [n.text() for n in applied],
            "flags": [asdict(f) for f in flags],
        }
        print(f"{name}: 자동 교정 {len(applied)}건, 플래그 {len(flags)}건", file=sys.stderr)

    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    print(f"코퍼스 {len(lines)}줄 -> {out_path}", file=sys.stderr)


def compare(path_a: Path, path_b: Path) -> int:
    a = json.loads(path_a.read_text(encoding="utf-8"))
    b = json.loads(path_b.read_text(encoding="utf-8"))
    total = 0
    for combo in sorted(set(a) | set(b)):
        ra, rb = a.get(combo, {}), b.get(combo, {})
        text_diffs = [
            (i, x, y)
            for i, (x, y) in enumerate(zip(ra.get("texts", []), rb.get("texts", [])))
            if x != y
        ]
        log_a, log_b = ra.get("applied_log", []), rb.get("applied_log", [])
        key = lambda f: json.dumps(f, ensure_ascii=False, sort_keys=True)  # noqa: E731
        flags_a = [key(f) for f in ra.get("flags", [])]
        flags_b = [key(f) for f in rb.get("flags", [])]
        extras = (
            [("A에만 있는 자동 교정", x) for x in log_a if x not in log_b]
            + [("B에만 있는 자동 교정", x) for x in log_b if x not in log_a]
            + [("A에만 있는 플래그", x) for x in flags_a if x not in flags_b]
            + [("B에만 있는 플래그", x) for x in flags_b if x not in flags_a]
        )
        n = len(text_diffs) + len(extras)
        total += n
        print(f"[{combo}] {'동일' if n == 0 else f'차이 {n}건'}")
        for i, x, y in text_diffs[:10]:
            print(f"    줄{i + 1} A: {x!r}\n    줄{i + 1} B: {y!r}")
        for label, x in extras[:10]:
            print(f"    {label}: {x}")
    print(f"\n총 차이: {total}건")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "dump":
        dump(Path(sys.argv[2]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "compare":
        sys.exit(compare(Path(sys.argv[2]), Path(sys.argv[3])))
    else:
        print(__doc__)
        sys.exit(2)
