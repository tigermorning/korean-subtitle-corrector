@AGENTS.md

# Claude Code에만 해당하는 것

## 이 파일이 왜 있나

**Claude Code는 `AGENTS.md`를 읽지 않는다.** 세션 시작에 자동으로 실리는 것은
`CLAUDE.md`뿐이다(공식 문서: "Claude Code reads `CLAUDE.md`, not `AGENTS.md`").

이 저장소는 2026-08-14까지 `AGENTS.md`만 갖고 있었다. 그래서 **커밋 238개가 쌓이는
동안 Claude Code 세션에는 이 저장소의 규칙이 한 줄도 실리지 않았다.** 옆 저장소
(자막 및 TC 생성기)에는 `CLAUDE.md`가 있어서 규칙이 매번 실렸고, 그 차이를 아무도
눈치채지 못했다.

맨 윗줄 `@AGENTS.md`가 그것을 고친다 — import라 `AGENTS.md`가 통째로 실린다. 규칙은
계속 `AGENTS.md`에 쓴다. 그래야 opencode·Codex도 같은 것을 읽는다. **규칙을 두 파일에
나눠 적지 않는다** — 갈라지면 어느 쪽이 맞는지 아무도 모른다.

(심링크로도 되지만 Windows에서 심링크는 관리자 권한이 필요해 쓰지 않는다.)

## 커밋 전에 — 기계가 잰다

`tools/hooks/pre-commit`이 커밋 직전에 `tools/check_names.py`를 돌린다. 미해석 이름이
하나라도 나오면 **커밋이 만들어지지 않는다.**

새로 클론하거나 워크트리를 만들면 한 번 켜야 한다:

    git config core.hooksPath tools/hooks

**왜 `pytest`가 아니냐.** 이 저장소의 시험은 표준국어대사전·우리말샘 API를 실시간으로
조회한다. 네트워크와 API 키가 있어야 하고, **국립국어원이 사전을 개정하면 우리 코드가
멀쩡해도 실패한다.** 그런 것을 커밋을 막는 자리에 두면 사람이 곧 `--no-verify`를 손에
익히고, 그러면 훅이 없는 것만 못하다. `pytest`는 사람이 따로 돌린다.

`check_names.py`를 고른 이유는 반대다 — 0.4초, 네트워크 없음, 판정이 흔들리지 않는다.
그리고 이 저장소에서 가장 위험한 실패 모드(시험이 안 밟는 분기의 `NameError`)를
정확히 겨눈다.

## 구조를 바꾼 뒤에는

훅이 잡는 것은 이름뿐이다. 모듈을 나누거나 함수를 옮겼으면 `AGENTS.md`가 시키는
`tools/diff_behavior.py`까지 돌린다 — 순수 이동이라면 SHA256까지 같아야 한다.
