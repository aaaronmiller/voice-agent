#!/usr/bin/env bash

# ── Echo-Node v2 environment ────────────────────────────────────────
# Source this before running any Python commands:
#   source v2/env.sh && echo_node_export_nvidia_libs

# Activate the project virtual environment
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

# Limit ONNX Runtime thread pools for idle efficiency
# (Drops from 39 threads to ~1 without affecting wake word speed)
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

# Disable Python thread-unsafe warnings from onnxruntime
export PYTHONWARNINGS=ignore

echo_node_export_nvidia_libs() {
  local root="${1:-$ROOT}"
  if [[ ! -x "$root/.venv/bin/python" ]]; then
    return 0
  fi
  local libs
  libs="$("$root/.venv/bin/python" - <<'PY'
from pathlib import Path
import site

paths = []
for base in site.getsitepackages():
    nvidia = Path(base) / "nvidia"
    if nvidia.exists():
        paths.extend(str(path) for path in nvidia.glob("*/lib"))
print(":".join(paths))
PY
)"
  if [[ -n "$libs" ]]; then
    export LD_LIBRARY_PATH="$libs:${LD_LIBRARY_PATH:-}"
  fi
}
