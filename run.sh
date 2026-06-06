#!/usr/bin/env bash
set -euo pipefail

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run ./setup.sh first." >&2
  exit 1
fi

exec .venv/bin/python local_voice_assistant.py "$@"
