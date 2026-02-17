#!/usr/bin/env bash
set -euo pipefail

# Если uv не установлен - ставим
if ! command -v uv >/dev/null 2>&1; then
  echo "[install] uv не найден, устанавливаю..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # подхватываем uv в текущей сессии (обычно ставится в ~/.local/bin)
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[run] syncing dependencies..."
uv sync
echo "[run] starting BeeAgent..."
uv run python3 config/start.py "$@"