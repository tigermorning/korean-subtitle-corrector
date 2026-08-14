"""이 저장소가 **라이브러리로 제공하는 계약**이 그대로인지 정적으로 확인한다.

**왜 필요한가.** 이 교정기는 다른 도구가 `import`해서 쓴다. 그쪽은 우리 함수 이름과
반환 모양에 기대고 있는데, 우리가 그것을 바꿔도 **우리 시험은 통과한다** — 우리 시험은
우리 호출부만 보기 때문이다. 실제로 2026-08-04에 자동 교정 로그가 문자열에서
`AppliedNote`로 바뀌었고(§59), 그때 밖에서 문자열을 파싱하던 코드가 조용히 깨졌다.

**왜 import하지 않고 AST로 보나.** `import`하면 kiwipiepy(약 310MB)와 API 키가 필요해서
네트워크 없는 자리나 커밋 훅에서 돌릴 수 없다. 여기서 확인하는 것은 "이름과 모양"이므로
소스만 읽어도 된다. 0.1초에 끝나고 의존성이 없다.

    python tools/check_public_api.py

계약을 **일부러** 바꿀 때는 이 파일의 `CONTRACT`를 함께 고친다. 그 커밋이 곧
"밖이 깨진다"는 신호다. 무엇이 계약인지는 `docs/PUBLIC_API.md`에 적혀 있다.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (모듈 경로, 이름, 종류, 있어야 하는 것)
CONTRACT: list[tuple[str, str, str, tuple[str, ...]]] = [
    (
        "subtitle_corrector/engine/pipeline.py",
        "correct_entries",
        "function",
        ("entries", "doc_type", "spacing_mode"),
    ),
    (
        "subtitle_corrector/parsers.py",
        "SubtitleEntry",
        "class",
        ("index", "start", "end", "text"),
    ),
    (
        "subtitle_corrector/report.py",
        "FlagItem",
        "class",
        ("line_index", "original_text", "suggested_fix", "reason"),
    ),
    (
        "subtitle_corrector/report.py",
        "AppliedNote",
        "class",
        ("message", "line_index", "is_edit"),
    ),
]

# `AppliedNote`는 사람이 읽는 한 줄을 이 메서드로 준다. 밖에서 문자열을 다시 파싱하지
# 않게 하려고 둔 것이라 사라지면 계약이 깨진다.
REQUIRED_METHODS = {("AppliedNote", "text")}


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find(tree: ast.Module, name: str, kind: str):
    want = (ast.FunctionDef, ast.AsyncFunctionDef) if kind == "function" else (ast.ClassDef,)
    for node in tree.body:
        if isinstance(node, want) and node.name == name:
            return node
    return None


def _params(fn) -> set[str]:
    a = fn.args
    return {p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)}


def _fields(cls: ast.ClassDef) -> set[str]:
    """dataclass 필드와 `self.x = ...`로 만드는 속성을 함께 본다."""
    out = set()
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                        and sub.value.id == "self" and isinstance(sub.ctx, ast.Store):
                    out.add(sub.attr)
    return out


def _methods(cls: ast.ClassDef) -> set[str]:
    return {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main() -> int:
    problems: list[str] = []
    checked = 0

    for rel, name, kind, required in CONTRACT:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{rel} 파일이 없습니다 — {name}")
            continue
        node = _find(_module(path), name, kind)
        if node is None:
            problems.append(f"{rel}: {kind} `{name}`을 찾지 못했습니다")
            continue
        checked += 1
        have = _params(node) if kind == "function" else _fields(node)
        missing = [r for r in required if r not in have]
        if missing:
            problems.append(f"{rel}: `{name}`에 {', '.join(missing)}이(가) 없습니다")
        if kind == "class":
            for cls_name, meth in REQUIRED_METHODS:
                if cls_name == name and meth not in _methods(node):
                    problems.append(f"{rel}: `{name}.{meth}()`가 없습니다")

    print(f"공개 계약 {checked}개 확인, 어긋난 것 {len(problems)}건")
    for p in problems:
        print("  ", p)
    if problems:
        print()
        print("  계약을 일부러 바꿨다면 tools/check_public_api.py의 CONTRACT와")
        print("  docs/PUBLIC_API.md를 함께 고칩니다. 이 검사는 밖에서 이 저장소를")
        print("  라이브러리로 부르는 쪽이 조용히 깨지는 것을 막습니다.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
