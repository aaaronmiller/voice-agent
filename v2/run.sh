#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run ./setup.sh first." >&2
  exit 1
fi

source "$ROOT/env.sh"
echo_node_export_nvidia_libs "$ROOT"

exec .venv/bin/python assistant_v2.py "$@"
