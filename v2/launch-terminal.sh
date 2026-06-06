#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="cd '$ROOT' && ./run.sh"

if command -v ptyxis >/dev/null 2>&1; then
  exec ptyxis -- bash -lc "$CMD"
elif command -v gnome-terminal >/dev/null 2>&1; then
  exec gnome-terminal -- bash -lc "$CMD"
elif command -v kgx >/dev/null 2>&1; then
  exec kgx -- bash -lc "$CMD"
elif command -v xterm >/dev/null 2>&1; then
  exec xterm -e bash -lc "$CMD"
else
  echo "No supported terminal found. Run manually:" >&2
  echo "  cd '$ROOT' && ./run.sh" >&2
  exit 1
fi
