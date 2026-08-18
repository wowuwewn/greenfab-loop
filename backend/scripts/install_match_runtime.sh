#!/usr/bin/env bash
set -euo pipefail

# Render's native runtime and the production Docker image are CPU-only. Install
# PyTorch from its official CPU wheel index before resolving sentence-transformers
# so pip cannot select multi-gigabyte CUDA/NVIDIA runtime packages from PyPI.
readonly TORCH_CPU_VERSION="2.7.1"
readonly TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"

python -m pip install --no-cache-dir \
  "torch==${TORCH_CPU_VERSION}" \
  --index-url "${TORCH_CPU_INDEX}"
python -m pip install --no-cache-dir '.[match,storage]'

python - <<'PY'
import torch

expected = "2.7.1"
installed = torch.__version__.split("+", 1)[0]
if installed != expected:
    raise SystemExit(f"Unexpected torch version: {torch.__version__}; expected {expected}")
if torch.version.cuda is not None:
    raise SystemExit(f"CUDA-enabled torch was installed unexpectedly: {torch.version.cuda}")
print(f"Verified CPU-only torch {torch.__version__}")
PY

python -m pip check
