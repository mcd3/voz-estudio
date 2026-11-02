#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1
exec .venv/bin/python -m voz_estudio --port "${VOZ_PORT:-3010}"
