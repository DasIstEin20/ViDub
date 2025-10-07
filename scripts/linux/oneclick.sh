#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR%/scripts/linux}"

if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
  source "$PROJECT_ROOT/venv/bin/activate"
elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  source "$PROJECT_ROOT/.venv/bin/activate"
fi

python -m pip install -r "$PROJECT_ROOT/requirements.txt"
python "$PROJECT_ROOT/app.py"
