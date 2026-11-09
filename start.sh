#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: Virtual environment not found. Run ./install.sh first."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: Ollama is not installed or is not on PATH."
  echo "Install Ollama from https://ollama.com/download"
  exit 1
fi

set -a
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi
set +a

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_LLM_MODEL="${OLLAMA_LLM_MODEL:-llama3.2:3b}"
OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

if ! curl -s --max-time 2 "${OLLAMA_HOST}/api/tags" >/dev/null; then
  echo "Starting Ollama service..."
  ollama serve >/tmp/ollama.log 2>&1 &
  sleep 3
fi

echo "Checking required Ollama models..."
ollama list
echo "If ${OLLAMA_LLM_MODEL} or ${OLLAMA_EMBED_MODEL} is missing, run:"
echo "  ollama pull ${OLLAMA_LLM_MODEL}"
echo "  ollama pull ${OLLAMA_EMBED_MODEL}"

echo "Starting FastAPI on http://${APP_HOST}:${APP_PORT}/"
exec .venv/bin/python -m app
