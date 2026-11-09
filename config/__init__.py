import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_csv(name, default=""):
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def env_path(name, default):
    value = Path(os.getenv(name, str(default)))
    if not value.is_absolute():
        value = PROJECT_ROOT / value
    return value.resolve()


def _hosts_from_urls(*urls):
    hosts = set()
    for url in urls:
        host = urlparse(url or "").hostname
        if not host:
            continue
        host = host.lower()
        hosts.add(host)
        if host.startswith("www."):
            hosts.add(host[4:])
        else:
            hosts.add(f"www.{host}")
    return hosts


def load_website_pages():
    pages_file = env_path(
        "WEBSITE_PAGES_FILE",
        PROJECT_ROOT / "data" / "website_pages.json",
    )
    data = {}
    if pages_file.exists():
        data = json.loads(pages_file.read_text(encoding="utf-8"))

    pages = {
        str(key): str(url).strip()
        for key, url in (data.get("pages") or {}).items()
        if str(url).strip()
    }
    base_url = (
        os.getenv("WEBSITE_BASE_URL", "").strip()
        or str(data.get("base_url") or "").strip()
    )
    extra_hosts = env_csv("WEBSITE_ALLOWED_HOSTS") or tuple(
        str(host).strip() for host in (data.get("allowed_hosts") or []) if str(host).strip()
    )
    product_keys = env_csv("WEBSITE_PRODUCT_KEYS") or tuple(
        str(key).strip() for key in (data.get("product_keys") or []) if str(key).strip()
    )
    if not product_keys:
        product_keys = tuple(
            key for key, url in pages.items()
            if "iryax.com" in ((urlparse(url).hostname or "").lower())
        )
    allowed_hosts = {
        host.lower() for host in extra_hosts
    } | _hosts_from_urls(base_url, *pages.values())
    return {
        "file": pages_file,
        "base_url": base_url,
        "allowed_hosts": tuple(sorted(allowed_hosts)),
        "pages": pages,
        "product_keys": product_keys,
    }


_website = load_website_pages()


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("APP_ENV", "local")
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = env_int("APP_PORT", 8000)
    cors_origins: tuple = env_csv(
        "CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    )
    llm_model: str = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b").strip()
    embedding_model: str = os.getenv(
        "OLLAMA_EMBED_MODEL",
        "nomic-embed-text",
    )
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    chroma_path: Path = env_path(
        "CHROMA_DB_PATH",
        PROJECT_ROOT / "data" / "chroma_db",
    )
    collection_name: str = os.getenv("CHROMA_COLLECTION", "timely_health")
    max_request_chars: int = env_int("MAX_REQUEST_CHARS", 1000)
    rate_limit_per_minute: int = env_int("RATE_LIMIT_PER_MINUTE", 30)
    admin_token: str = os.getenv("ADMIN_SYNC_TOKEN", "")
    num_ctx: int = env_int("OLLAMA_NUM_CTX", 4096)
    num_predict_short: int = env_int("OLLAMA_NUM_PREDICT_SHORT", 110)
    num_predict_detailed: int = env_int("OLLAMA_NUM_PREDICT_DETAILED", 450)
    website_sync_enabled: bool = env_bool("WEBSITE_SYNC_ENABLED", True)
    website_sync_minutes: int = env_int("WEBSITE_SYNC_MINUTES", 5)
    website_deep_sync_enabled: bool = env_bool("WEBSITE_DEEP_SYNC_ENABLED", True)
    website_deep_sync_max_pages: int = env_int("WEBSITE_DEEP_SYNC_MAX_PAGES", 250)
    website_deep_sync_max_depth: int = env_int("WEBSITE_DEEP_SYNC_MAX_DEPTH", 3)
    website_pages_file: Path = _website["file"]
    website_base_url: str = _website["base_url"]
    website_allowed_hosts: tuple = _website["allowed_hosts"]
    pages: dict = field(default_factory=lambda: dict(_website["pages"]))
    product_keys: tuple = _website["product_keys"]
    website_user_agent: str = os.getenv(
        "WEBSITE_USER_AGENT",
        "TimelyHealthRAGBot/1.0",
    )
    website_request_timeout: int = env_int("WEBSITE_REQUEST_TIMEOUT", 20)
    website_request_delay: float = float(os.getenv("WEBSITE_REQUEST_DELAY", "0.5"))
    website_chunk_size: int = env_int("WEBSITE_CHUNK_SIZE", 850)
    website_chunk_overlap: int = env_int("WEBSITE_CHUNK_OVERLAP", 120)
    website_embed_batch_size: int = env_int("WEBSITE_EMBED_BATCH_SIZE", 16)
    rag_top_k: int = env_int("RAG_TOP_K", 6)
    rag_max_turns: int = env_int("RAG_MAX_TURNS", 3)
    rag_max_context_chars: int = env_int("RAG_MAX_CONTEXT_CHARS", 5000)
    rag_max_distance: float = env_float("RAG_MAX_DISTANCE", 0.68)
    debug: bool = env_bool("RAG_DEBUG", False)


def load_settings():
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    except ImportError:
        pass
    loaded = Settings()
    os.environ.setdefault("OLLAMA_HOST", loaded.ollama_host)
    return loaded


settings = load_settings()
