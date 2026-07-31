#!/bin/bash
# .claude/hooks/activate-env.sh

if [ -n "$CLAUDE_ENV_FILE" ]; then
  VENV_PATH="$(pwd)/.venv"
  echo "export PATH=\"$VENV_PATH/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  echo "export VIRTUAL_ENV=\"$VENV_PATH\""      >> "$CLAUDE_ENV_FILE"
fi
exit 0
