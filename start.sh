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

echo "[run] syncing dependencies from uv.lock..."
uv sync --frozen

echo "[run] starting BeeAgent..."
uv run --frozen python3 config/start.py "$@"