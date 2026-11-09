"""Incrementally synchronize website pages into ChromaDB."""

import argparse
import hashlib
import json
import re
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, urlunparse

import chromadb
import ollama
import requests
from bs4 import BeautifulSoup

from config import PROJECT_ROOT, settings
from app.browser import render_page_html
from app.content_filters import is_marketing_section, strip_marketing_copy
from app.rag import engine as rag

HASH_FILE = PROJECT_ROOT / "data" / "page_hashes.json"

CHUNK_SIZE = settings.website_chunk_size
CHUNK_OVERLAP = settings.website_chunk_overlap
EMBED_BATCH_SIZE = settings.website_embed_batch_size
REQUEST_TIMEOUT = settings.website_request_timeout
USER_AGENT = settings.website_user_agent

# Deep crawling uses the configured seed pages in data/website_pages.json.
DEEP_SYNC_ENABLED = settings.website_deep_sync_enabled
DEEP_SYNC_MAX_PAGES = max(1, settings.website_deep_sync_max_pages)
DEEP_SYNC_MAX_DEPTH = max(0, settings.website_deep_sync_max_depth)

# Exclude common utility, account, and non-content routes from deep crawling.
SKIPPED_PATH_PARTS = (
    "/wp-admin", "/login", "/logout", "/cart", "/checkout",
    "/account", "/my-account", "/cdn-cgi", "/search",
)
SKIPPED_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".mp4",
    ".mp3", ".css", ".js", ".xml",
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
SYNC_LOCK = threading.Lock()
LAST_SYNC = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_report": {},
    "last_failures": [],
    "last_error": None,
    "changed": False,
}


# ---------------------------------------------------------------------------
# FETCHING / PARSING
# ---------------------------------------------------------------------------

def render_with_playwright(url):
    """Render a JavaScript-heavy page when static HTML has too little content."""
    return render_page_html(url, USER_AGENT)


def _clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def parse_html(html):
    """Extract visible page content, including text inside div/span layouts.

    Prefer semantic headings/paragraphs/lists. If those miss substantial text,
    fall back to all visible text in the main content root. Duplicate lines are
    removed while preserving the page's reading order.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for selector in ("header", "nav", "footer"):
        for tag in soup.select(selector):
            tag.decompose()

    content_root = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    # First pass: semantic content with headings retained as section markers.
    lines = []
    semantic_tags = content_root.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "blockquote"],
        recursive=True,
    )
    for element in semantic_tags:
        value = _clean_text(element.get_text(" ", strip=True))
        if not value:
            continue
        if element.name in {"h1", "h2", "h3", "h4"}:
            line = f"## {value}"
        elif element.name == "li":
            line = f"- {value}"
        else:
            line = value
        if not lines or line.casefold() != lines[-1].casefold():
            lines.append(line)

    semantic_text = "\n".join(lines).strip()

    # Second pass: div/span-based layouts often contain real product copy.
    # Use it when it adds meaningful text not captured by semantic tags.
    raw_lines = []
    for raw in content_root.get_text("\n", strip=True).splitlines():
        value = _clean_text(raw)
        if value and (not raw_lines or value.casefold() != raw_lines[-1].casefold()):
            raw_lines.append(value)
    raw_text = "\n".join(raw_lines).strip()

    if len(raw_text) > len(semantic_text) * 1.15:
        # Preserve heading labels in the richer fallback where possible.
        text = raw_text
    else:
        text = semantic_text or raw_text

    return title, text, soup


def fetch_page(url):
    """
    Return (title, text, soup), or None for confirmed HTTP 404/410.

    Network errors and empty pages raise exceptions so old indexed content
    remains intact.
    """
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)

    if response.status_code in (404, 410):
        return None

    response.raise_for_status()
    title, text, soup = parse_html(response.text)

    # Try browser rendering when the static response is likely an app shell.
    main = soup.find("main") or soup.find(id=re.compile(r"main|content", re.I))
    main_text = main.get_text(" ", strip=True) if main else ""
    if len(text) < 250 or (main is not None and len(main_text) < 120):
        rendered_html = render_with_playwright(url)
        if rendered_html:
            rendered_title, rendered_text, rendered_soup = parse_html(rendered_html)
            if len(rendered_text) > len(text):
                title = rendered_title or title
                text = rendered_text
                soup = rendered_soup

    if len(text.strip()) < 80:
        raise RuntimeError(
            "Page returned too little readable text; previous index preserved."
        )

    return title or url, text, soup


def normalize_web_url(base_url, href):
    if not href:
        return None

    url, _fragment = urldefrag(urljoin(base_url, href.strip()))
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    # Ignore query strings to avoid indexing tracking/filter variants.
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        "",
        "",
    ))


def _is_crawlable(url, allowed_hosts):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()

    if host not in allowed_hosts:
        return False
    if path.endswith(SKIPPED_EXTENSIONS):
        return False
    if any(part in path for part in SKIPPED_PATH_PARTS):
        return False
    return True


def discover_deep_pages(seed_urls):
    """
    Discover same-domain pages from seed URLs.

    Deep sync is disabled by default to prevent unrelated website pages from
    polluting the chatbot's knowledge base. Enable it explicitly via env var.
    """
    seeds = list(dict.fromkeys(
        normalize_web_url(url, url) for url in seed_urls
        if normalize_web_url(url, url)
    ))
    if not DEEP_SYNC_ENABLED:
        return {f"seed_{i}": url for i, url in enumerate(seeds)}

    allowed_hosts = {
        urlparse(url).hostname.lower().removeprefix("www.")
        for url in seeds if urlparse(url).hostname
    }

    queue = deque((url, 0) for url in seeds)
    visited = set()
    discovered = {}

    while queue and len(discovered) < DEEP_SYNC_MAX_PAGES:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if not _is_crawlable(url, allowed_hosts):
            continue

        try:
            response = SESSION.get(
                url, timeout=REQUEST_TIMEOUT, allow_redirects=True
            )
            if response.status_code in (404, 410):
                continue
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            print(f"    [Deep crawl skipped {url}: {type(exc).__name__}: {exc}]")
            continue

        parsed = urlparse(url)
        path_key = parsed.path.strip("/") or "home"
        key = re.sub(r"[^a-zA-Z0-9]+", "_", path_key).strip("_")[:80] or "page"
        if key in discovered and discovered[key] != url:
            key = f"{key}_{len(discovered)}"
        discovered[key] = url

        if depth >= DEEP_SYNC_MAX_DEPTH:
            continue

        for link in soup.find_all("a", href=True):
            next_url = normalize_web_url(url, link.get("href"))
            if next_url and next_url not in visited:
                if _is_crawlable(next_url, allowed_hosts):
                    queue.append((next_url, depth + 1))

    return discovered


# ---------------------------------------------------------------------------
# SECTION-AWARE CHUNKING
# ---------------------------------------------------------------------------

HEADING_PATTERN = re.compile(r"^\s*#{1,4}\s+(.+?)\s*$")
SKIP_HEADINGS = {
    "learn more", "view", "live", "get bundle", "contact sales",
    "get started", "join now", "sign up", "buy now",
}
def _is_section_heading(line):
    text = _clean_text(line)
    if not text:
        return False
    match = HEADING_PATTERN.match(line)
    if match:
        return True
    name = text.lower().rstrip(":")
    if name in SKIP_HEADINGS:
        return False
    words = text.split()
    if text.endswith((".", "?", "!")) or len(text) > 60 or len(words) > 6:
        return False
    if text.isupper():
        return False
    if 1 <= len(words) <= 5 and text.istitle():
        return True
    return False


def _split_long_text(text, chunk_size, overlap):
    """Split an oversized section while preferring paragraph/sentence boundaries."""
    text = text.strip()
    if not text:
        return []

    pieces = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            candidates = [
                text.rfind("\n\n", start, end),
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
                text.rfind("? ", start, end),
                text.rfind("! ", start, end),
            ]
            boundary = max(candidates)
            if boundary > start + int(chunk_size * 0.55):
                end = boundary + (2 if text[boundary:boundary + 2] in {
                    ". ", "? ", "! "
                } else 1)

        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)

        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return pieces


def chunk_sections(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Produce dictionaries containing text and section_heading.

    A heading is prepended to its section's content, rather than being split
    away into a different chunk.
    """
    text = re.sub(r"\n{3,}", "\n\n", (text or "")).strip()
    if not text:
        return []

    sections = []
    current_heading = ""
    current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if _is_section_heading(line):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            heading_match = HEADING_PATTERN.match(line)
            current_heading = _clean_text(
                heading_match.group(1) if heading_match else line
            )
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    if not sections:
        sections = [("", text)]

    chunks = []
    for heading, body in sections:
        if is_marketing_section(heading, body):
            continue
        body = strip_marketing_copy(body)
        if not body:
            continue
        combined = f"{heading}\n{body}".strip() if heading and heading.lower() not in {
            "why choose us", "from systems to intelligence"
        } else body
        for piece in _split_long_text(combined, chunk_size, overlap):
            chunks.append({
                "text": piece,
                "section_heading": heading[:200] or "General",
            })

    return chunks


# Backward-compatible helper for any other code importing chunk_text().
def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    return [item["text"] for item in chunk_sections(text, chunk_size, overlap)]


# ---------------------------------------------------------------------------
# EMBEDDINGS / CHROMA
# ---------------------------------------------------------------------------

def embed_documents(texts):
    """Embed batches using the same model and Nomic prefix as test_rag.py."""
    prefix = "search_document: " if getattr(rag, "USE_NOMIC_PREFIX", False) else ""
    vectors = []

    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = [
            prefix + item for item in texts[start:start + EMBED_BATCH_SIZE]
        ]
        result = ollama.embed(model=rag.EMBED_MODEL, input=batch)
        vectors.extend(result.embeddings)

    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: expected {len(texts)}, got {len(vectors)}"
        )
    return vectors


def get_collection():
    rag.DB_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(rag.DB_PATH))
    return client.get_or_create_collection(
        name=rag.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def load_hashes():
    try:
        data = json.loads(HASH_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_hashes(hashes):
    HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = HASH_FILE.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(hashes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(HASH_FILE)


def existing_page_ids(collection, url):
    result = collection.get(
        where={"source_url": url},
        include=["metadatas"],
    )
    return result.get("ids") or []


def _page_category(url, title):
    """Create a simple, searchable category label from the page URL/title."""
    path = urlparse(url).path.strip("/").lower()
    if path:
        return path.split("/")[-1].replace("-", " ").replace("_", " ")[:100]
    return _clean_text(title)[:100] or "website"


def replace_page_records(collection, url, title, chunks, digest):
    """
    Embed and upsert the new page version before deleting old records.

    If embedding or upsert fails, the old page remains searchable.
    """
    if not chunks:
        raise RuntimeError("No text chunks were produced; old index retained.")

    texts = [item["text"] for item in chunks]
    vectors = embed_documents(texts)
    base = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    ids = [f"{base}-{digest[:10]}-{i}" for i in range(len(texts))]
    category = _page_category(url, title)
    synced_at = datetime.now().isoformat(timespec="seconds")

    metadatas = []
    for i, item in enumerate(chunks):
        metadatas.append({
            "source_url": url,
            "page_title": str(title)[:250],
            "page_category": category,
            "page_path": urlparse(url).path or "/",
            "section_heading": str(item.get("section_heading", "General"))[:200],
            "chunk_number": i,
            "chunk_type": "text",
            "content_hash": digest,
            "synced_at": synced_at,
        })

    old_ids = existing_page_ids(collection, url)

    # Upsert first: old records are not deleted if this operation fails.
    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=vectors,
        metadatas=metadatas,
    )

    new_id_set = set(ids)
    ids_to_delete = [item for item in old_ids if item not in new_id_set]
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)


def remove_page(collection, url):
    ids = existing_page_ids(collection, url)
    if ids:
        collection.delete(ids=ids)


# ---------------------------------------------------------------------------
# SYNC
# ---------------------------------------------------------------------------

def sync_page(collection, key, url, hashes, force=False):
    page = fetch_page(url)

    if page is None:
        # Only a confirmed HTTP 404/410 removes an indexed page.
        remove_page(collection, url)
        hashes.pop(url, None)
        return "removed (HTTP 404/410)"

    title, text, _soup = page
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    if not force and hashes.get(url) == digest:
        return "unchanged"

    chunks = chunk_sections(text)
    replace_page_records(collection, url, title, chunks, digest)
    hashes[url] = digest
    return f"updated ({len(chunks)} chunks)"


def sync_all(force=False):
    """Sync configured pages. Failed pages retain their previous index."""
    with SYNC_LOCK:
        LAST_SYNC["running"] = True
        LAST_SYNC["last_started"] = datetime.now().isoformat(timespec="seconds")
        LAST_SYNC["last_error"] = None
        try:
            collection = get_collection()
        except Exception as exc:
            LAST_SYNC["running"] = False
            LAST_SYNC["last_error"] = f"{type(exc).__name__}: {exc}"
            LAST_SYNC["last_finished"] = datetime.now().isoformat(timespec="seconds")
            raise
        hashes = load_hashes()
        report = {}
        changed = False
        failures = []

        # Always sync explicitly configured pages first.
        pages = dict(settings.pages)

        if DEEP_SYNC_ENABLED:
            discovered = discover_deep_pages(list(settings.pages.values()))
            for key, url in discovered.items():
                if url not in pages.values():
                    pages[key] = url

        for key, url in pages.items():
            try:
                status = sync_page(collection, key, url, hashes, force)
                report[key] = status
                if status.startswith(("updated", "removed")):
                    changed = True
            except Exception as exc:
                report[key] = f"FAILED - {type(exc).__name__}: {exc}"
                failures.append(key)

        # Persist successful page hashes even if another page failed.
        save_hashes(hashes)

        if changed:
            rag.STAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
            rag.STAMP_FILE.write_text(
                datetime.now().isoformat(timespec="seconds"),
                encoding="utf-8",
            )

        LAST_SYNC.update({
            "running": False,
            "last_finished": datetime.now().isoformat(timespec="seconds"),
            "last_report": report,
            "last_failures": failures,
            "changed": changed,
        })
        return report, failures


def print_report(report, failures):
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] Website sync report")
    print("-" * 76)
    for key, status in report.items():
        print(f"{key:24s} {status}")
    print("-" * 76)

    if failures:
        print(
            f"Sync completed with errors on {len(failures)} page(s): "
            + ", ".join(failures)
        )
    else:
        print("Sync completed successfully.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize Timely Health / Iryax website pages into ChromaDB."
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-embed every configured page.",
    )
    parser.add_argument(
        "--watch",
        type=int,
        metavar="MINUTES",
        help="Repeat sync every N minutes (terminal must remain open).",
    )
    args = parser.parse_args()

    if args.watch is not None and args.watch < 1:
        parser.error("--watch must be at least 1 minute.")

    while True:
        try:
            report, failures = sync_all(force=args.force)
            print_report(report, failures)
        except Exception as exc:
            print(f"\nSync could not start: {type(exc).__name__}: {exc}")

        if not args.watch:
            break

        # Only the first cycle honors --force.
        args.force = False
        print(
            f"\nNext sync in {args.watch} minute(s). "
            "Press Ctrl+C to stop."
        )
        try:
            time.sleep(args.watch * 60)
        except KeyboardInterrupt:
            print("\nWebsite sync stopped.")
            break


if __name__ == "__main__":
    main()
