#!/bin/bash
# PostToolUse → Edit|Write (ASYNC, NON-BLOCKING)
# Runs pytest in background after Python file edits.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip non-Python files
case "$FILE_PATH" in
  *.py) ;;
  *) exit 0 ;;
esac

# Skip test files to avoid infinite loops
case "$FILE_PATH" in
  *test_*|*_test.*|*conftest*) exit 0 ;;
esac

PROJECT_DIR="$CLAUDE_PROJECT_DIR"

RESULT=$(cd "$PROJECT_DIR" && python -m pytest tests/ -v -m 'not live' 2>&1 | tail -30)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  jq -n --arg file "$(basename "$FILE_PATH")" \
    '{ systemMessage: ("Tests PASSED after editing " + $file) }'
else
  jq -n --arg file "$(basename "$FILE_PATH")" --arg result "$RESULT" \
    '{ systemMessage: ("Tests FAILED after editing " + $file + ":\n" + $result) }'
fi
