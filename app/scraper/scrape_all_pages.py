"""Scrape discovered pages, chunk them, and upsert them into ChromaDB."""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

import chromadb
import ollama
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import PROJECT_ROOT, settings
from app.browser import render_page_html
from app.content_filters import is_marketing_section, strip_marketing_copy
from app.scraper.discover_pages import BASE_URL, discover_pages

RAW_FILE = PROJECT_ROOT / "data" / "raw" / "all_pages_content.json"
REPORT_FILE = PROJECT_ROOT / "data" / "raw" / "complete_scraping_report.json"
USER_AGENT = settings.website_user_agent
TIMEOUT = settings.website_request_timeout
DELAY_SECONDS = settings.website_request_delay

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("scraper")

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})
retries = Retry(total=3, connect=3, read=3, backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def extract_page(html, url):
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = clean_text(title_tag.get_text(" ", strip=True)) if title_tag else ""
    if not title:
        heading = soup.find("h1")
        title = clean_text(heading.get_text(" ", strip=True)) if heading else "Untitled Page"

    for tag in soup(["script", "style", "noscript", "svg", "iframe",
                     "header", "nav", "footer", "aside", "form"]):
        tag.decompose()
    for selector in (".cookie-banner", ".cookie-consent", "#cookie-banner",
                     ".newsletter", ".popup", ".modal"):
        for tag in soup.select(selector):
            tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.find("body") or soup
    sections = []
    section_heading = ""
    blocks = []
    for element in root.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = clean_text(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name in {"h1", "h2", "h3", "h4"}:
            section_heading = text
            blocks.append(f"\n{text}\n")
            continue
        sections.append({
            "section_heading": section_heading,
            "text": text,
        })
        blocks.append(text)

    content = clean_text("\n".join(blocks))
    return title, content, sections


def chunk_text(text, sections=None, chunk_size=None, overlap=None):
    chunk_size = settings.website_chunk_size if chunk_size is None else chunk_size
    overlap = settings.website_chunk_overlap if overlap is None else overlap
    if sections:
        chunks = []
        current_heading = ""
        buffer = []
        for section in sections:
            heading = section["section_heading"]
            if is_marketing_section(heading, section.get("text", "")):
                continue
            if heading != current_heading:
                if buffer:
                    chunks.extend(split_buffer(" ".join(buffer), current_heading,
                                               chunk_size, overlap))
                    buffer = []
                current_heading = heading
            buffer.append(strip_marketing_copy(section["text"]))
        if buffer:
            chunks.extend(split_buffer(" ".join(buffer), current_heading,
                                       chunk_size, overlap))
        return chunks
    return split_buffer(text, "", chunk_size, overlap)


def split_buffer(text, heading, chunk_size, overlap):
    text = clean_text(text)
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("? ", start, end),
                           text.rfind("! ", start, end), text.rfind("\n", start, end))
            if boundary > start + 350:
                end = boundary + 1
        piece = clean_text(text[start:end])
        if piece:
            chunks.append({
                "text": piece,
                "section_heading": heading or "Page Introduction",
            })
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def fetch_page(url):
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    if response.status_code == 204:
        return None
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        return None
    html = response.text
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    static_text = clean_text(soup.get_text(" ", strip=True))
    if len(static_text) >= 80:
        return html

    rendered_html = render_page_html(url, USER_AGENT, timeout_ms=60000)
    if rendered_html:
        return rendered_html
    return html


def embed_batches(texts, batch_size=None):
    from app.rag.engine import USE_NOMIC_PREFIX
    batch_size = settings.website_embed_batch_size if batch_size is None else batch_size
    prefix = "search_document: " if USE_NOMIC_PREFIX else ""
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = [prefix + item for item in texts[start:start + batch_size]]
        result = ollama.embed(model=settings.embedding_model, input=batch)
        vectors.extend(result.embeddings)
    return vectors


def index_page(collection, page, chunks):
    url = page["url"]
    digest = page["content_hash"]
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    existing = collection.get(where={"source_url": url}, include=["metadatas"])
    existing_ids = existing.get("ids", [])
    existing_hashes = {
        metadata.get("content_hash")
        for metadata in existing.get("metadatas", [])
        if metadata
    }
    if existing_ids and existing_hashes == {digest}:
        return len(existing_ids), "unchanged"

    documents = [chunk["text"] for chunk in chunks]
    vectors = embed_batches(documents)
    ids = [f"{url_hash}-{index}" for index in range(len(chunks))]
    metadatas = [{
        "source_url": url,
        "page_title": page["title"],
        "section_heading": chunk["section_heading"],
        "chunk_index": index,
        "content_hash": digest,
        "scraped_at": page["scraped_at"],
    } for index, chunk in enumerate(chunks)]

    collection.upsert(ids=ids, documents=documents, embeddings=vectors,
                      metadatas=metadatas)
    stale_ids = [item for item in existing_ids if item not in set(ids)]
    if stale_ids:
        collection.delete(ids=stale_ids)
    return len(ids), "updated"


def scrape_all_pages():
    pages = discover_pages()
    if not pages:
        LOGGER.error("No pages discovered; output files will record an empty run")
    scraped_pages = []
    failures = []

    for index, url in enumerate(pages, start=1):
        LOGGER.info("Scraping %s/%s %s", index, len(pages), url)
        try:
            html = fetch_page(url)
            if html is None:
                failures.append({"url": url, "error": "Non-HTML or empty response"})
                continue
            title, content, sections = extract_page(html, url)
            if len(content) < 80:
                failures.append({"url": url, "error": "Very short or empty page"})
                continue
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            scraped_pages.append({
                "url": url,
                "title": title,
                "clean_text": content,
                "content": content,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": digest,
                "sections": sections,
            })
        except Exception as exc:
            LOGGER.exception("Failed to scrape %s", url)
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(DELAY_SECONDS)

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_text(json.dumps(scraped_pages, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    chroma_client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = chroma_client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    scraped_urls = {page["url"] for page in scraped_pages}
    stale_collection = collection.get(include=["metadatas"])
    stale_ids = []
    for record_id, metadata in zip(
        stale_collection.get("ids", []),
        stale_collection.get("metadatas", []) or [],
    ):
        source_url = metadata.get("source_url") if metadata else None
        if source_url not in scraped_urls:
            stale_ids.append(record_id)
    if stale_ids:
        collection.delete(ids=stale_ids)
        LOGGER.info("Removed %s stale Chroma record(s)", len(stale_ids))
    index_results = []
    expected_chunks = 0
    for page in scraped_pages:
        chunks = chunk_text(page["clean_text"], page["sections"])
        expected_chunks += len(chunks)
        chunk_count, status = index_page(collection, page, chunks)
        index_results.append({"url": page["url"], "chunks": chunk_count, "status": status})

    REPORT_FILE.write_text(json.dumps({
        "website": BASE_URL,
        "scraping_date": datetime.now(timezone.utc).isoformat(),
        "pages_found": len(pages),
        "pages_scraped": len(scraped_pages),
        "pages_failed": len(failures),
        "failed_details": failures,
        "expected_chunks": expected_chunks,
        "index_results": index_results,
        "output_file": str(RAW_FILE),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    LOGGER.info("Scraped %s pages; failed %s; indexed %s expected chunks",
                len(scraped_pages), len(failures), expected_chunks)
    return scraped_pages, failures, expected_chunks


if __name__ == "__main__":
    scrape_all_pages()
