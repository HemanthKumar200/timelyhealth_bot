# Timely Health / Iryax RAG Chatbot

FastAPI chatbot with ChromaDB retrieval, Ollama generation, website scrape/sync, and an embeddable live-chat widget.

Default models (from `.env.example`): **llama3.2:3b** for answers and **nomic-embed-text** for embeddings.

## Project layout

```text
app/                 Application code
  api/               FastAPI routes and middleware
  rag/               Chat engine, retrieval, and SSE streaming
  scraper/           Full website scrape + index
  sync/              Incremental website sync
  hardware.py        CPU/GPU profile for Ollama settings
config/              Environment and website page settings
frontend/
  index.html         Widget demo page
  chat-widget.js     Single embeddable widget (injects its own CSS)
server.py            FastAPI entrypoint (`uvicorn server:app`)
requirements.txt     Python packages
data/
  website_pages.json Site URLs (edit this, not Python files)
  chroma_db/         Vector index (created at runtime)
scripts/             CLI wrappers
Dockerfile           Production image
docker-compose.yml   App + Ollama
```

Configuration lives in `.env` and `data/website_pages.json`.

## Requirements

- Python 3.10 or newer
- [Ollama](https://ollama.com/download) running locally (or in Docker)
- Packages in `requirements.txt`: FastAPI, Uvicorn, Starlette, Pydantic, python-dotenv, psutil, httpx, ChromaDB, Ollama client, requests, urllib3, BeautifulSoup, lxml, Playwright

Install Python deps:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
.venv/bin/python -m pip install -r requirements.txt           # Linux / macOS
```

Ollama is not a pip package. Pull the models named in `.env`:

```bash
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

## Local setup (Windows)

1. Run `install.bat` (creates `.venv`, installs `requirements.txt`, copies `.env.example` to `.env`).
2. Pull models if they are missing (see above).
3. Run `start.bat`.
4. Open `http://127.0.0.1:8000`.

## Local setup (Linux / macOS)

```bash
chmod +x install.sh start.sh
./install.sh
ollama pull llama3.2:3b
ollama pull nomic-embed-text
./start.sh
```

## Configuration

Copy `.env.example` to `.env`. Important values:

| Variable | Purpose |
|---|---|
| `APP_HOST` / `APP_PORT` | Bind address |
| `CORS_ORIGINS` | Allowed browser origins for the widget |
| `OLLAMA_HOST` | Ollama URL |
| `OLLAMA_LLM_MODEL` | Chat model (default `llama3.2:3b`) |
| `OLLAMA_EMBED_MODEL` | Embedding model (default `nomic-embed-text`) |
| `CHROMA_DB_PATH` | Vector database folder |
| `WEBSITE_PAGES_FILE` | Page map JSON |
| `WEBSITE_SYNC_ENABLED` | Background sync with the API |
| `ADMIN_SYNC_TOKEN` | Protects `POST /api/sync` when set |
| `MAX_REQUEST_CHARS` | Chat message length limit |
| `RATE_LIMIT_PER_MINUTE` | Per-IP chat rate limit |

Edit site URLs in `data/website_pages.json`.

## Useful commands

```bash
python -m app                          # start API
python -m app.scraper.scrape_website   # full scrape + index
python -m app.sync.website             # one-off sync
python -m app.sync.website --force
python scripts/evaluate.py             # accuracy check
```

## Docker deployment

1. Copy `.env.example` to `.env`.
2. Set production values:

```text
APP_ENV=production
APP_HOST=0.0.0.0
CORS_ORIGINS=https://timelyhealth.in,https://www.timelyhealth.in
OLLAMA_HOST=http://ollama:11434
ADMIN_SYNC_TOKEN=<long-random-secret>
```

3. Start:

```bash
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

4. Check:

- App: `http://SERVER:8000`
- Health: `http://SERVER:8000/health`
- Ready: `http://SERVER:8000/ready`
- Sync: `http://SERVER:8000/sync-status`

Put HTTPS in front with nginx or Caddy. Keep Ollama (port 11434) private.

First chat answers need a Chroma index. Sync starts with the API when `WEBSITE_SYNC_ENABLED=1`, or run:

```bash
docker compose exec app python -m app.sync.website
```

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Widget demo |
| GET | `/health` | Status plus Chroma chunk count |
| GET | `/ready` | True when the index has chunks |
| GET | `/sync-status` | Last website sync result |
| POST | `/api/sync` | Trigger sync (`X-Admin-Token` if `ADMIN_SYNC_TOKEN` is set) |
| POST | `/chat` | SSE stream: `{"session_id","message"}` |
| POST | `/reset` | Clears that session's memory |
| POST | `/api/chat` | JSON fallback (same RAG engine) |
| POST | `/api/reset` | Same as `/reset` |

SSE `/chat` events:

- `{"type":"meta","session_id":"..."}`
- `{"type":"token","text":"..."}` (repeated)
- `{"type":"done","answer":"...","sources":[...]}`
- `{"type":"error","message":"..."}`

## Run the backend

Windows:

```bat
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Linux / macOS:

```bash
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Or `python -m app` / `start.bat` / `./start.sh`.

Test with curl (Windows `cmd`):

```bat
curl http://127.0.0.1:8000/health

curl -N -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"demo-1\",\"message\":\"What services do you offer?\"}"

curl -X POST http://127.0.0.1:8000/reset ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"demo-1\"}"
```

On Linux/macOS use `\` instead of `^` for line breaks, and `'{"session_id":"demo-1","message":"What services do you offer?"}'`.

## Add the widget to timelyhealth.in

One script tag, no API keys. The widget injects its own CSS:

```html
<script
  src="https://YOUR-CHAT-HOST/static/chat-widget.js"
  data-api-base="https://YOUR-CHAT-HOST">
</script>
```

Optional overrides, placed before the script:

```html
<script>
  window.TH_CHAT_OVERRIDES = {
    panelWidth: 380,
    panelHeight: 500,
    welcomeMessage: "Hello! Welcome to Timely Health. How can I help you?",
    quickReplies: ["Our services", "Home diagnostics", "Book appointment", "Contact"]
  };
</script>
```

Set `CORS_ORIGINS=https://timelyhealth.in,https://www.timelyhealth.in` in `.env`.

The widget streams tokens from `POST /chat`, keeps `session_id` in `sessionStorage`, supports New chat / Esc / Enter, and lifts itself if another site button sits in the same corner.

## Deploy the backend over HTTPS

1. Run FastAPI on the server, bound privately (`APP_HOST=127.0.0.1`).
2. Put nginx or Caddy in front with TLS for `YOUR-CHAT-HOST`.
3. Proxy `/`, `/chat`, `/reset`, `/health`, `/ready`, `/sync-status`, `/api/`, and `/static/` to Uvicorn.
4. Keep Ollama (`11434`) and ChromaDB off the public internet.
5. Point `data-api-base` at the HTTPS host so the browser can reach `/chat`.

Docker:

```bash
docker compose up -d --build
```
