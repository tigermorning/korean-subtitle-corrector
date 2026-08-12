"""착수 조건 확인: 문맥 의존 띄어쓰기 사례가 실제 데이터에 몇 건이나 있는가.

없는 문제를 만들어 내지 않기 위해 먼저 센다. 20건 미만이면 PoC 범위를 바꾼다.
"""
import io, json, re, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CORRECTOR = Path(__file__).resolve().parents[2]
# 옆 프로젝트(자막 및 TC 생성기). 2026-08-12에 저장소 이름이 subtitle-editor에서
# subtitle-tc-generator로 바뀌었다 — 둘 다 본다.
EDITOR = next((CORRECTOR.parent / n for n in ("subtitle-tc-generator", "subtitle-editor")
               if (CORRECTOR.parent / n).is_dir()), CORRECTOR.parent / "subtitle-tc-generator")

# 규범이 양쪽 표기를 모두 인정하되 **뜻이 갈리는** 것들.
# 사전 조회만으로는 어느 쪽인지 정할 수 없는 부류다.
AMBIGUOUS = {
    "한번/한 번": r"한\s?번",
    "잘하다/잘 하다": r"잘\s?하[는다지고셨였]",
    "못하다/못 하다": r"못\s?하[는다지고셨였]",
    "안되다/안 되다": r"안\s?되[는다지고셨였]",
    "다하다/다 하다": r"다\s?하[는다지고]",
    "그동안/그 동안": r"그\s?동안",
    "이때/이 때": r"이\s?때",
    "지난번/지난 번": r"지난\s?번",
    "큰집/큰 집": r"큰\s?집",
    "어느새/어느 새": r"어느\s?새",
    "만하다/만 하다": r"만\s?하[는다지]",
    "의존명사 데": r"[는은ㄴ을]\s?데[에가를는]?\b",
    "의존명사 지": r"[은는ㄴ]\s?지\s?[0-9오이삼사]",
}

def sentences():
    out = []
    for srt in [EDITOR / ".tmp/out-large.srt", EDITOR / ".tmp/out.srt",
                EDITOR / "examples/ko-sdh-sample.srt",
                CORRECTOR / "examples/sample.srt", CORRECTOR / "examples/sample_dialect.srt"]:
        if srt.exists():
            for line in srt.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                line = line.strip()
                if line and not line.isdigit() and "-->" not in line:
                    out.append((srt.name, line))
    for jf in (CORRECTOR / "examples/eval").glob("*.jsonl"):
        for raw in jf.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                item = json.loads(raw)
                for k in ("input", "gold"):
                    if item.get(k):
                        out.append((jf.name, item[k]))
    return out

rows = sentences()
print(f"실제 문장 {len(rows)}개 수집\n")
total, hits = 0, {}
for label, pat in AMBIGUOUS.items():
    found = [(src, s) for src, s in rows if re.search(pat, s)]
    if found:
        hits[label] = found
        total += len(found)
        print(f"{label:18} {len(found):3}건")
        for src, s in found[:3]:
            print(f"      [{src}] {s[:60]}")
print(f"\n합계 {total}건 / 서로 다른 부류 {len(hits)}종")
print("판정:", "착수 가능 (20건 이상)" if total >= 20 else "범위 전환 필요")
