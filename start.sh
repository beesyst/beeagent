#!/usr/bin/env bash
set -euo pipefail

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
  uv sync --frozen
fi

echo "[run] resolving extractor profile and syncing environment..."
uv run --frozen --no-sync python3 config/start.py bootstrap

echo "[run] starting BeeAgent..."
uv run --frozen --no-sync python3 config/start.py "$@"
