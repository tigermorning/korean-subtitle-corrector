<!--
project-session-memory 스킬의 정제된 누적 요약 파일입니다.
새 세션이 시작될 때 SessionStart 훅(.claude/hooks/session-memory-start.sh)이
이 파일 내용과 .claude/memory/inbox/의 미정리 캡처를 컨텍스트로 불러옵니다.
inbox를 정리할 때 이 파일 아래에 날짜와 함께 핵심만 append하세요.
-->

## 2026-08-30

- 이 프로젝트에는 원래 `durable-session-log`(수동 기록, `SESSION_LOG.md` +
  cat 훅)가 설치돼 있었으나(PR #5), 이후 되돌려졌음(revert). `durable-session-log`는
  `tigermorning/my-skills`에서 `project-session-memory`로 통합됐고, 이 설치가
  그 자리를 대신함.
