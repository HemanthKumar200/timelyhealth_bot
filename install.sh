#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Timely Health chatbot installer"
echo "==============================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 was not found on PATH."
  exit 1
fi

python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

echo "Installing Python dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Installing Playwright Chromium for website sync..."
export PLAYWRIGHT_BROWSERS_PATH="${XDG_CACHE_HOME:-$HOME/.cache}/timelyhealth-playwright"
.venv/bin/python -m playwright install chromium || echo "WARNING: Playwright Chromium install failed."

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "WARNING: Ollama was not found on PATH."
else
  echo "Checking Ollama models..."
  ollama list || true
  echo "Required defaults: llama3.2:3b and nomic-embed-text"
fi

mkdir -p data/raw data/chroma_db
echo
echo "Installation complete. Run ./start.sh to launch the application."
