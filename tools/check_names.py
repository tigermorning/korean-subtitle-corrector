"""모듈이 참조하는 전역 이름이 그 모듈에서 전부 해석되는지 정적으로 확인한다.

**왜 필요한가**: 이 저장소에서 가장 위험한 실패 모드는 "테스트가 밟지 않는 분기에서만
NameError"다. 교정 엔진의 분기는 특정 형태소 조합에서만 열리는 것이 많아서, 150건이
넘는 테스트를 통과하고도 실제 원고 한 줄이 파일 전체 교정을 무너뜨릴 수 있다.

실제로 이 검사가 그런 버그를 하나 잡았다: `_protect_unfounded_respacing()`이 다른
함수의 지역 변수 이름(`to_restore`/`insert_at`)을 참조해, 조사+보조 용언을 붙여 쓴
줄('알고는있다')에서만 NameError로 터졌다(2026-08-02 발견·수정,
`docs/IMPLEMENTATION_LOG.md` §49).

    python tools/check_names.py

거짓 양성 없이 0건이 나와야 한다. 모듈을 새로 쪼개거나 함수를 옮긴 뒤에는 반드시
돌릴 것 — import 하나를 빠뜨려도 import 시점에는 조용하고 실행 시점에만 터진다.
"""

import ast
import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "subtitle_corrector"
BUILTINS = set(dir(builtins)) | {"__name__", "__file__", "__all__", "__doc__"}


def module_scope(tree: ast.Module) -> set[str]:
    """모듈 최상위에서 묶이는 이름(import·def·class·대입·for 타깃)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        else:
            names.update(
                n.id for n in ast.walk(node)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
            )
    return names


def all_binds(node: ast.AST) -> set[str]:
    """서브트리 안에서 묶이는 모든 이름 — 중첩 함수·람다·컴프리헨션·except까지.

    함수 하나를 통째로 보므로 클로저 변수는 자연히 '묶인 이름'에 포함된다. 목적은
    스코프를 정확히 흉내 내는 것이 아니라 "이 이름이 이 모듈 어디에서도 나오지
    않는다"는 확실한 경우만 잡는 것이다.
    """
    bound: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.arg):
            bound.add(sub.arg)
        elif isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            bound.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(sub.name)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            bound.add(sub.name)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for alias in sub.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            bound.update(sub.names)
    return bound


def main() -> int:
    problems: list[str] = []
    checked = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scope = module_scope(tree) | BUILTINS
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            checked += 1
            bound = all_binds(node)
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Name)
                    and isinstance(sub.ctx, ast.Load)
                    and sub.id not in scope
                    and sub.id not in bound
                ):
                    problems.append(
                        f"{path.relative_to(ROOT)}:{sub.lineno} "
                        f"{node.name}() -> 미해석 이름 '{sub.id}'"
                    )

    print(f"검사한 최상위 함수 {checked}개, 미해석 전역 이름 {len(problems)}건")
    for p in problems:
        print("  ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
