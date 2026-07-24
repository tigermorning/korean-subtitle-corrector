---
name: non-ascii-via-file
description: When a shell command's argument contains non-ASCII text (Korean, etc.) — curl -d, git commit -m, python -c, env vars, and similar — write the text to a file first and have the command read the file, instead of inlining it. On Windows/Git Bash, inline non-ASCII arguments silently get mangled before the target program ever sees them, producing errors that look like real bugs but aren't.
---

# Non-ASCII via File

터미널 명령어에 한글 등 비ASCII 텍스트를 **직접** 넣지 마세요. 파일에 먼저 써두고, 명령어는 그 파일을 읽게 하세요.

## 왜 이 스킬이 필요한가

Windows의 Git Bash(그리고 비슷한 일부 터미널 환경)는 명령어 인자에 한글 같은 비ASCII 문자를
직접 넣으면 실제 프로그램에 전달되기 전에 인코딩을 깨뜨립니다. 예를 들어:

```bash
curl -d '{"title":"필라테스"}' http://example.com/api
```

이렇게 실행하면 서버가 `{"detail":"There was an error parsing the body"}` 같은 에러를 냅니다.
**이건 서버나 API의 버그가 아닙니다** — 한글이 명령어에 도달하기 전에 이미 깨져서 들어간 겁니다.
실제로 이 문제 때문에 멀쩡한 기능을 "버그"로 착각하고 애먼 코드를 의심하며 시간을 낭비하기 쉽습니다.

## 절차

1. 실행하려는 셸 명령어의 인자에 한글(또는 다른 비ASCII 문자)이 포함되는지 확인하세요.
2. 포함된다면, 그 텍스트를 **먼저 파일로 저장**하세요 (에디터의 파일 쓰기 기능처럼 인코딩을
   명시적으로 다루는 방법을 쓰세요 — 셸의 `echo`나 heredoc은 터미널에 따라 이 문제를
   똑같이 겪을 수 있습니다).
3. 명령어에서는 텍스트를 직접 타이핑하는 대신 그 파일을 참조하게 하세요.
   - curl: `curl --data-binary @body.json ...`
   - git: `git commit -F message.txt`
   - python: 파일을 읽어서 처리하거나 `python script.py < input.txt`
4. 실행 후 임시로 만든 파일은 정리하세요.
5. 비ASCII 텍스트가 포함된 명령어에서 "파싱 에러"나 "형식이 이상하다"는 에러가 나면,
   대상 시스템의 버그를 의심하기 **전에** 먼저 이 인코딩 문제부터 의심하세요.

## 하지 않는 것

- 한글이 포함된 값을 명령어에 직접 타이핑해서 넘기지 않기
- 이런 에러가 나왔을 때 곧바로 "앱이 이상하다"고 결론 내리지 않기 — 먼저 인코딩 경로부터 배제하기
