#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -x "$SKILL_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$SKILL_DIR/.venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN=$(command -v python3.12)
else
  echo "Python 3.12 is required. Run scripts/bootstrap.sh first." >&2
  exit 2
fi

"$PYTHON_BIN" -m unittest discover -s "$SKILL_DIR/scripts" -p 'test_*.py' -v
"$PYTHON_BIN" -m py_compile "$SKILL_DIR/scripts/read_garmin_activity.py"
