#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -x /opt/homebrew/bin/python3.12 ]; then
  PYTHON_BIN=/opt/homebrew/bin/python3.12
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN=$(command -v python3.12)
else
  echo "Python 3.12 is required. Install it before bootstrapping this skill." >&2
  exit 2
fi

"$PYTHON_BIN" -m venv "$SKILL_DIR/.venv"
"$SKILL_DIR/.venv/bin/python" -m pip install --upgrade -r "$SKILL_DIR/scripts/requirements.txt"
echo "Garmin reader environment ready: $SKILL_DIR/.venv/bin/python"
