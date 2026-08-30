#!/bin/bash
# SessionStart hook: load this project's cross-session memory into context.
#
# Two sources get folded in:
#   1. .claude/memory/session-log.md  - the curated, running summary (may be
#      empty at first; grows only when a past session actually consolidated
#      into it).
#   2. .claude/memory/inbox/*.md      - raw per-session excerpts captured by
#      the SessionEnd hook that haven't been consolidated yet. These are
#      injected verbatim (not summarized here - a shell script can't judge
#      what matters) along with a nudge for Claude to fold the useful parts
#      into session-log.md and clear the inbox once it gets the chance.
set -euo pipefail

input="$(cat)"
source_kind="$(printf '%s' "$input" | jq -r '.source // "startup"')"

# On a mid-session compact, the conversation already has this context loaded
# once; re-injecting it would just be noise.
[ "$source_kind" = "compact" ] && exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
memory_dir="$project_dir/.claude/memory"
log="$memory_dir/session-log.md"
inbox="$memory_dir/inbox"
mkdir -p "$memory_dir" "$inbox"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
wrote_anything=0

if [ -s "$log" ]; then
  {
    echo "## 이 프로젝트의 이전 세션 기억 (.claude/memory/session-log.md)"
    echo
    cat "$log"
    echo
  } >> "$tmp"
  wrote_anything=1
fi

pending=()
while IFS= read -r -d '' f; do pending+=("$f"); done < <(find "$inbox" -maxdepth 1 -name '*.md' -type f -print0 2>/dev/null | sort -z)

if [ "${#pending[@]}" -gt 0 ]; then
  {
    echo "## 아직 정리되지 않은 최근 세션 기록 (.claude/memory/inbox/, ${#pending[@]}개)"
    echo
    for f in "${pending[@]}"; do
      cat "$f"
      echo
    done
    echo "---"
    echo "위 inbox 기록을 대화 초반 적당한 시점에 훑어보고, 앞으로도 기억할 가치가 있는 핵심만 골라"
    echo ".claude/memory/session-log.md에 append하세요. 반영한 inbox 파일은 지워서 다음 세션이"
    echo "같은 내용을 중복해서 보지 않게 하세요. 사소하거나 이미 끝난 작업이면 그냥 지워도 됩니다."
  } >> "$tmp"
  wrote_anything=1
fi

if [ "$wrote_anything" -eq 1 ]; then
  jq -n --rawfile ctx "$tmp" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
fi
