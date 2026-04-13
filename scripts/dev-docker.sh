#!/usr/bin/env bash
# Start dev stack in Docker: only port 5173 is published; API is proxied by Vite to backend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
exec docker compose up --build
