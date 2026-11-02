#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Se necesita Python 3.12"'
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
if [[ "$(uname -s)" == "Darwin" ]]; then
  .venv/bin/python -m pip install torch==2.11.0 torchaudio==2.11.0
elif command -v nvidia-smi >/dev/null && [[ "${VOZ_DEVICE:-auto}" != "cpu" ]]; then
  .venv/bin/python -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
else
  .venv/bin/python -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
fi
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/download_models.py
echo 'Instalación completada. Ejecuta bash start.sh.'
