#!/bin/bash
# PreToolUse → Bash (BLOCKING)
# Rule: Commit format must be `<type>: <description>`
# where type is feat|fix|refactor|docs|chore|ci|test.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check git commit commands
if ! echo "$COMMAND" | grep -qE 'git\s+commit'; then
  exit 0
fi

# Skip amend commits
if echo "$COMMAND" | grep -q '\-\-amend'; then
  exit 0
fi

# Extract commit message from heredoc pattern (most common with Claude)
MSG=$(echo "$COMMAND" | sed -n '/<<.*EOF/,/EOF/{//!p;}' | head -1 | sed 's/^[[:space:]]*//')

# Try -m "message" pattern using sed
if [ -z "$MSG" ]; then
  MSG=$(echo "$COMMAND" | sed -n 's/.*-m[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Try -m 'message' pattern using sed
if [ -z "$MSG" ]; then
  MSG=$(echo "$COMMAND" | sed -n "s/.*-m[[:space:]]*'\([^']*\)'.*/\1/p" | head -1)
fi

if [ -z "$MSG" ]; then
  # Can't parse message — allow it (might be complex format)
  exit 0
fi

# Trim leading whitespace
MSG=$(echo "$MSG" | sed 's/^[[:space:]]*//')

# Validate format: <type>: <description>
if ! echo "$MSG" | grep -qE '^(feat|fix|refactor|docs|chore|ci|test): .+'; then
  echo "BLOCKED: Commit message must follow format '<type>: <description>' where type is one of: feat, fix, refactor, docs, chore, ci, test. Got: '$MSG'. See CLAUDE.md Rule #1." >&2
  exit 2
fi

exit 0
