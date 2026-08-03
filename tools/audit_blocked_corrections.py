"""개별 규칙은 "고치자"고 했는데 최종 출력에는 반영되지 않은 건을 찾는다.

**왜 필요한가**: 이 엔진은 규칙 20여 개가 순서대로 도는데, 뒤에 오는 보호 가드
(`spacing_guards`, 사투리 protect, 된소리 구어형 예외 등)가 앞 규칙의 교정을
되돌리는 경우가 있다. 되돌리는 것이 옳을 때도 많지만, **왜 막혔는지 아무 데도
남지 않아** 사람이 보기에는 "그냥 안 고쳐진 것"과 구분되지 않는다. 평가셋은
41줄만 보므로 이 부류를 놓친다.

각 줄에 대해 아래를 대조한다.

- 규칙 단독 실행: `correct_always_wrong`, `correct_nonstandard_terms`,
  `correct_loanwords`, `correct_discriminatory_terms`
- 파이프라인 최종 출력: `correct_entries`

규칙이 바꾸자고 한 낱말이 최종 출력에 **그대로 남아 있으면** 막힌 것으로 본다.
플래그로 강등된 경우(사람에게 물어보기로 한 경우)는 정상이므로, 그 줄에 관련
플래그가 있는지도 함께 찍어 구분할 수 있게 한다.

    python tools/audit_blocked_corrections.py            # 전체 코퍼스
    python tools/audit_blocked_corrections.py --limit 50 # 앞 50줄만
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from subtitle_corrector.engine import (  # noqa: E402
    correct_always_wrong,
    correct_discriminatory_terms,
    correct_loanwords,
    correct_nonstandard_terms,
    correct_entries,
)
from subtitle_corrector.parsers import SubtitleEntry  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from diff_behavior import build_corpus  # noqa: E402

def _loanwords(text: str) -> tuple[str, list[str]]:
    """correct_loanwords()는 (텍스트, 적용 목록, 플래그용 후보 2종)을 돌려준다.
    여기서는 앞 둘만 쓴다."""
    corrected, applied, _mixed, _proper = correct_loanwords(text)
    return corrected, applied


RULES = {
    "확정오류": correct_always_wrong,
    "규범표기재지정": correct_nonstandard_terms,
    "외래어표기": _loanwords,
    "차별표현": correct_discriminatory_terms,
}


def is_prose_line(line: str) -> bool:
    """코퍼스에는 테스트 파일의 docstring도 섞여 들어온다(줄바꿈·코드 기호 포함).
    감사 결과를 읽을 수 있게 실제 문장처럼 보이는 줄만 남긴다."""
    if "\n" in line or len(line) > 80:
        return False
    return not any(tok in line for tok in ("()", "->", "_", "`", "#", "assert"))


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    corpus = [l for l in build_corpus() if is_prose_line(l)]
    if limit:
        corpus = corpus[:limit]

    blocked = []
    for i, line in enumerate(corpus, start=1):
        proposals = []
        for name, rule in RULES.items():
            try:
                changed, notes = rule(line)
            except Exception as exc:
                print(f"[규칙 오류] {name}: {line!r} -> {exc}")
                continue
            if changed != line:
                proposals.append((name, notes))
        if not proposals:
            continue

        entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=line)
        corrected, flags, _log = correct_entries([entry])
        final = corrected[0].text

        for name, notes in proposals:
            # 최종 출력에 같은 규칙을 다시 걸어 본다. 여전히 같은 교정을 하자고 하면
            # 파이프라인 어딘가가 막은 것이다. 단순 부분 문자열 대조는 '재판장님' 안의
            # '장님'을 막힌 것으로 잘못 세므로(규칙 자신은 토큰 경계를 본다) 쓰지 않는다.
            rule = RULES[name]
            refinal, renotes = rule(final)
            still = [n for n in renotes if n in notes]
            if refinal != final and still:
                flagged = any(
                    n.split(" -> ")[0] in (f.original_text or "") for n in still for f in flags
                )
                blocked.append((i, name, ", ".join(still), line, final, flagged))

    if not blocked:
        print("막힌 교정 0건.")
        return 0

    print(f"막힌 교정 {len(blocked)}건 (플래그로 강등된 것 포함)\n")
    print(f"{'줄':>4} {'규칙':12} {'제안':28} {'플래그':5} 원문 -> 최종")
    print("-" * 100)
    for i, name, note, line, final, flagged in blocked:
        mark = "있음" if flagged else "없음"
        print(f"{i:>4} {name:12} {note:28} {mark:5} {line!r} -> {final!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
