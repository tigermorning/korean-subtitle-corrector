#!/bin/bash
# SessionEnd hook: capture a lightweight excerpt of the just-finished session
# into .claude/memory/inbox/, then commit it locally (no push — see below).
#
# SessionEnd hooks share a very tight timeout budget (default ~1.5s across
# ALL SessionEnd hooks combined; the "timeout" key in settings.json raises the
# ceiling for this specific hook), and their output cannot influence the model
# at all (no additionalContext, no decision control) because the session is
# already tearing down. So this script stays purely mechanical: grab the tail
# of the transcript, append it to a per-session file, then commit it. No
# summarization happens here — that's deferred to the SessionStart hook of the
# *next* session, where Claude itself can read and condense it with full
# judgment.
#
# Deliberately no `git push` here. An earlier draft added push (with pull
# --rebase first), which the Claude Code auto-mode safety classifier
# blocked from being installed: a hook that pushes to a remote unsupervised,
# on every single session end, forever, is a materially different risk than
# one that only touches local disk. Committing locally still gets the
# capture out of "uncommitted and about to vanish" into an ordinary git
# commit — an actual `git push` (by Claude, in the course of normal work,
# or by the user) later in this same checkout carries it along like any
# other local commit. That means this alone does NOT guarantee the very
# last session's capture survives if nothing ever pushes again before the
# container is permanently reclaimed — it reduces that risk to the same
# level ordinary uncommitted dev work already has, no better, no worse.
set -euo pipefail

input="$(cat)"
transcript_path="$(printf '%s' "$input" | jq -r '.transcript_path // empty')"
session_id="$(printf '%s' "$input" | jq -r '.session_id // empty')"

[ -n "$transcript_path" ] && [ -f "$transcript_path" ] && [ -n "$session_id" ] || exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
inbox="$project_dir/.claude/memory/inbox"
out="$inbox/$session_id.md"

# Idempotent: if this session already has an inbox entry, don't duplicate it.
[ -f "$out" ] && exit 0

mkdir -p "$inbox"

{
  echo "### $(date -u +"%Y-%m-%dT%H:%M:%SZ") (session $session_id)"
  echo
  tail -n 300 "$transcript_path" | jq -r '
    select(.type == "user" or .type == "assistant")
    | .message.content
    | if type == "array" then (map(select(.type == "text") | .text) | join(" "))
      elif type == "string" then .
      else empty end
    | select(length > 0)
  ' 2>/dev/null | tail -n 40
  echo
} >> "$out"

# --- commit locally, best-effort (no push — see header comment) ---
# Failures here (no git repo, detached HEAD, nothing to commit) are
# swallowed on purpose: SessionEnd output is discarded by the harness
# anyway, so there is no way to surface an error, and this must never
# block the session from actually ending. Restricted to this one file
# (git add -- / commit --only --) so we never sweep up or commit whatever
# else the user had staged mid-work.
(
  cd "$project_dir" || exit 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

  git add -- "$out" || exit 0
  git diff --cached --quiet -- "$out" && exit 0
  git commit -q --only -m "project-session-memory: capture session $session_id" -- "$out" || exit 0
) || true
