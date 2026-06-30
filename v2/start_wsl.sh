#!/usr/bin/env bash
# Start Echo-Node on WSL2 / Linux (sounddevice backend, no tmux)
#
# Usage:
#   ./start_wsl.sh              # run in foreground
#   ./start_wsl.sh --bg         # run in background with nohup

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Source environment
source env.sh
echo_node_export_nvidia_libs "$ROOT"

# Pick config
CONFIG="${1:-config.wsl.yaml}"
if [[ "$CONFIG" == "--bg" ]]; then
  CONFIG="config.wsl.yaml"
  shift
fi

if [[ "${1:-}" == "--bg" ]]; then
  nohup .venv/bin/python assistant_v2.py --config "$CONFIG" > /tmp/echo-node.log 2>&1 &
  echo "Echo-Node started in background (PID $!)"
  echo "tail -f /tmp/echo-node.log to see output"
else
  .venv/bin/python assistant_v2.py --config "$CONFIG"
fi
