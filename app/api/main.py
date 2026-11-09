from __future__ import annotations

import json
import logging
import threading
import time
import traceback
from collections import defaultdict, deque
from typing import Dict
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from config import PROJECT_ROOT, settings
from app.hardware import detect_hardware_profile
from app.rag.engine import ChatSession, get_collection
from app.rag.widget_chat import iter_respond

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("timelyhealth.api")

docs_url = "/docs" if settings.debug else None
app = FastAPI(
    title="Timely Health Chatbot API",
    version="1.0.0",
    description="FastAPI interface for the Timely Health / Iryax RAG chatbot.",
    docs_url=docs_url,
    redoc_url=docs_url,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

STATIC_DIR = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

MAX_BODY_BYTES = 2048
SESSION_TTL_SECONDS = 30 * 60

_sessions: Dict[str, ChatSession] = {}
_session_locks: Dict[str, threading.Lock] = {}
_session_seen: Dict[str, float] = {}
_sessions_lock = threading.Lock()
_rate_hits: dict[str, deque] = defaultdict(deque)
_sync_thread_started = False


def _clip(value, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _parse_chat_payload(payload: dict) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Invalid JSON.")
    question = _clip(payload.get("question") or payload.get("message"), 500)
    session_id = _clip(payload.get("session_id"), 128) or None
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    return question, session_id


def _chat_payload(session_id: str, result: dict) -> dict:
    return {
        "session_id": session_id,
        "answer": str(result.get("answer", "")),
        "sources": list(result.get("sources", []) or []),
        "mode": str(result.get("mode", "UNKNOWN")),
    }


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _prune_sessions() -> None:
    now = time.time()
    expired = [
        sid for sid, seen in _session_seen.items()
        if now - seen > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_locks.pop(sid, None)
        _session_seen.pop(sid, None)


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in {"/health", "/ready"}:
        return await call_next(request)

    content_length = request.headers.get("content-length")
    if request.method == "POST" and content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse({"detail": "Request body too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid content length."}, status_code=400)

    now = time.time()
    bucket = _rate_hits[_client_ip(request)]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_per_minute:
        return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
    bucket.append(now)
    return await call_next(request)


def _sync_loop():
    from app.sync.website import LAST_SYNC, sync_all

    while True:
        try:
            sync_all()
        except Exception as exc:
            LAST_SYNC["running"] = False
            LAST_SYNC["last_error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        time.sleep(max(1, settings.website_sync_minutes) * 60)


@app.on_event("startup")
def initialize_app():
    global _sync_thread_started
    get_collection()
    if settings.website_sync_enabled and not _sync_thread_started:
        thread = threading.Thread(target=_sync_loop, name="website-sync", daemon=True)
        thread.start()
        _sync_thread_started = True


def _get_session(session_id: str | None) -> tuple[str, ChatSession, threading.Lock]:
    sid = session_id or str(uuid4())
    with _sessions_lock:
        _prune_sessions()
        if sid not in _sessions:
            _sessions[sid] = ChatSession()
            _session_locks[sid] = threading.Lock()
        _session_seen[sid] = time.time()
        return sid, _sessions[sid], _session_locks[sid]


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    try:
        count = get_collection().count()
        status = "ok"
        error = None
    except Exception as exc:
        count = 0
        status = "degraded"
        error = str(exc)
    payload = {
        "status": status,
        "service": "Timely Health Chatbot API",
        "environment": settings.environment,
        "chroma_chunk_count": count,
    }
    if error:
        payload["error"] = error
    return payload


@app.get("/ready")
def ready():
    checks = {"chroma": False, "ollama": False}
    errors = {}
    try:
        checks["chroma"] = get_collection().count() >= 0
    except Exception as exc:
        errors["chroma"] = str(exc)
    try:
        import ollama
        models = {item.model for item in ollama.list().models}
        checks["ollama"] = any(
            settings.llm_model in model or settings.embedding_model in model
            for model in models
        ) or bool(models)
        if not checks["ollama"]:
            errors["ollama"] = "Ollama is reachable but required models were not listed."
    except Exception as exc:
        errors["ollama"] = str(exc)
    ready_ok = all(checks.values())
    return {
        "status": "ok" if ready_ok else "not_ready",
        "checks": checks,
        "errors": errors,
        "hardware": detect_hardware_profile().__dict__,
    }


@app.get("/sync-status")
def sync_status():
    from app.sync.website import LAST_SYNC
    return {
        "enabled": settings.website_sync_enabled,
        "interval_minutes": settings.website_sync_minutes,
        **LAST_SYNC,
    }


@app.post("/api/sync")
def trigger_sync(
    force: bool = False,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not settings.admin_token:
        raise HTTPException(status_code=404, detail="Admin sync is not enabled.")
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    from app.sync.website import print_report, sync_all
    try:
        report, failures = sync_all(force=force)
        print_report(report, failures)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "failures": failures, "report": report}


@app.post("/chat")
async def chat_stream(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large.")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid JSON.")

    question, asked_session = _parse_chat_payload(payload if isinstance(payload, dict) else {})
    session_id, session, session_lock = _get_session(asked_session)
    LOGGER.info("chat start session=%s ip=%s q=%r", session_id, _client_ip(request), question[:80])
    wants_json = "application/json" in (request.headers.get("accept") or "").lower() and "text/event-stream" not in (request.headers.get("accept") or "").lower()
    if wants_json:
        def _respond():
            with session_lock:
                pieces = []
                result = {"answer": "", "sources": [], "mode": "UNKNOWN"}
                for event in iter_respond(session, question):
                    if event.get("type") == "token":
                        pieces.append(event.get("text") or "")
                    elif event.get("type") == "replace":
                        pieces = [event.get("text") or ""]
                    elif event.get("type") == "done":
                        result = event
                    elif event.get("type") == "error":
                        raise RuntimeError(event.get("message") or "Chat failed.")
                if not result.get("answer"):
                    result["answer"] = "".join(pieces)
                return result
        try:
            result = await run_in_threadpool(_respond)
        except Exception:
            traceback.print_exc()
            raise HTTPException(status_code=503, detail="The chatbot could not process this request.")
        return JSONResponse(_chat_payload(session_id, result))

    def event_stream():
        yield f"data: {json.dumps({'type': 'meta', 'session_id': session_id})}\n\n"
        try:
            with session_lock:
                for event in iter_respond(session, question):
                    event["session_id"] = session_id
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': 'The chatbot could not process this request.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat")
async def chat_json(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large.")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid JSON.")
    question, asked_session = _parse_chat_payload(payload if isinstance(payload, dict) else {})
    session_id, session, session_lock = _get_session(asked_session)

    def _respond():
        with session_lock:
            pieces = []
            result = {"answer": "", "sources": [], "mode": "UNKNOWN"}
            for event in iter_respond(session, question):
                if event.get("type") == "token":
                    pieces.append(event.get("text") or "")
                elif event.get("type") == "replace":
                    pieces = [event.get("text") or ""]
                elif event.get("type") == "done":
                    result = event
            if not result.get("answer"):
                result["answer"] = "".join(pieces)
            return result

    try:
        result = await run_in_threadpool(_respond)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail="The chatbot could not process this request. Check Ollama, ChromaDB, and the server logs.",
        ) from exc

    return _chat_payload(session_id, result)


@app.post("/reset")
@app.post("/api/reset")
async def reset_chat(request: Request):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid JSON.")
    session_id = _clip((payload or {}).get("session_id") if isinstance(payload, dict) else "", 128)
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required.")
    with _sessions_lock:
        session = _sessions.get(session_id)
        lock = _session_locks.get(session_id)

    if session is None or lock is None:
        return {"status": "ok", "message": "No active session found."}

    def _reset():
        with lock:
            session.reset()

    await run_in_threadpool(_reset)
    return {"status": "ok", "message": "Conversation memory cleared."}
