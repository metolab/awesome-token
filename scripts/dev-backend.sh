#!/usr/bin/env bash
# Local dev: uses the project micromamba interpreter when available.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/backend"
export DATA_DIR="${DATA_DIR:-${ROOT}/backend/data}"
PY="${PYTHON_EXE:-/root/micromamba/envs/test/bin/python}"
exec "${PY}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
