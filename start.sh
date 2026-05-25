#!/usr/bin/env bash
set -euo pipefail

# Если uv не установлен - ставим
if ! command -v uv >/dev/null 2>&1; then
  echo "[install] uv не найден, устанавливаю..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # подхватываем uv в текущей сессии (обычно ставится в ~/.local/bin)
  export PATH="$HOME/.local/bin:$PATH"
fi

# Инициализация .env по шаблону (если нет)
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "[init] .env not found, creating from .env.example"
  cp .env.example .env
  echo "[init] Please edit .env and set real secrets"
fi

echo "[run] syncing dependencies from uv.lock..."
uv sync --frozen

echo "[run] starting BeeAgent..."
uv run --frozen python3 config/start.py "$@"