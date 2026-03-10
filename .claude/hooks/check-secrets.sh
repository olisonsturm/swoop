#!/bin/bash
# PreToolUse → Write|Edit (BLOCKING)
# Rule: Never write secrets to files.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Block writing to .env files (except .env.example)
if [[ "$FILE_PATH" == *".env" ]] || [[ "$FILE_PATH" == *".env.local" ]] || [[ "$FILE_PATH" == *".env.production" ]]; then
  BASENAME=$(basename "$FILE_PATH")
  if [ "$BASENAME" != ".env.example" ]; then
    echo "BLOCKED: Cannot write to '$BASENAME'. Never commit .env files with real secrets. See CLAUDE.md Rule #3." >&2
    exit 2
  fi
fi

# Get the content being written/edited
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty')

if [ -z "$CONTENT" ]; then
  exit 0
fi

# Check for JWT tokens (eyJ followed by 100+ base64 chars)
if echo "$CONTENT" | grep -qE 'eyJ[A-Za-z0-9_-]{100,}'; then
  echo "BLOCKED: Content appears to contain a JWT token. Never write secrets to files. See CLAUDE.md Rule #3." >&2
  exit 2
fi

# Check for common API key patterns
if echo "$CONTENT" | grep -qE 'sk-[A-Za-z0-9]{20,}'; then
  echo "BLOCKED: Content appears to contain an API key (sk-...). Never write secrets to files. See CLAUDE.md Rule #3." >&2
  exit 2
fi

exit 0
