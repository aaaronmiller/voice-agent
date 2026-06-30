#!/usr/bin/env bash

# Limit ONNX Runtime thread pools for idle efficiency
# (Drops from 39 threads to ~1 without affecting wake word speed)
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

# Disable Python thread-unsafe warnings from onnxruntime
export PYTHONWARNINGS=ignore

echo_node_export_nvidia_libs() {
  local root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
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
