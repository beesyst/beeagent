#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${1:-}" == "beescan" && "${2:-}" == "review" ]]; then
  if [[ ! -x .venv/bin/python3 ]]; then
    echo "BeeScan review requires an already installed host environment" >&2
    exit 3
  fi
  exec .venv/bin/python3 config/start.py "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[install] uv не найден, устанавливаю..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  export PATH="$HOME/.local/bin:$PATH"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  echo "[init] .env not found, creating from .env.example"
  cp .env.example .env
  chmod 600 .env 2>/dev/null || true
fi

if ! uv run --frozen --no-sync python3 -c "import config.start" >/dev/null 2>&1; then
  echo "[run] bootstrapping base environment from uv.lock..."
  uv sync --frozen --no-dev
fi

echo "[run] syncing selected dependencies and preparing native providers..."
uv run --frozen --no-sync python3 config/start.py bootstrap

echo "[run] starting BeeAgent..."
uv run --frozen --no-sync python3 config/start.py "$@"
