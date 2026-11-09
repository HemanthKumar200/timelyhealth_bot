"""Discover internal Timely Health pages from sitemap.xml and links."""
import json
import re
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

from config import PROJECT_ROOT, settings

BASE_URL = settings.website_base_url
ALLOWED_HOSTS = set(settings.website_allowed_hosts)
MAX_PAGES = settings.website_deep_sync_max_pages
TIMEOUT = settings.website_request_timeout
USER_AGENT = settings.website_user_agent
OUTPUT_FILE = PROJECT_ROOT / "data" / "raw" / "discovered_urls.json"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def normalize_url(raw_url):
    if not raw_url:
        return None
    url = urldefrag(urljoin(BASE_URL, raw_url.strip()))[0]
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(),
                           path=path, params="", fragment="").geturl()


def should_skip(url):
    parsed = urlparse(url)
    return parsed.path.lower().endswith((
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip",
        ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".mp3",
    ))


def sitemap_urls(sitemap_url):
    try:
        response = SESSION.get(sitemap_url, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")
        found = []
        for sitemap in soup.find_all("sitemap"):
            loc = sitemap.find("loc")
            if loc:
                found.extend(sitemap_urls(loc.get_text(strip=True)))
        for loc in soup.find_all("loc"):
            normalized = normalize_url(loc.get_text(strip=True))
            if normalized and not should_skip(normalized):
                found.append(normalized)
        return list(dict.fromkeys(found))
    except requests.RequestException:
        return []


def discover_pages():
    parsed = urlparse(BASE_URL)
    root = f"{parsed.scheme}://{parsed.netloc}"
    discovered = sitemap_urls(f"{root}/sitemap.xml")
    queue_items = [normalize_url(BASE_URL)]

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            if response and response.status < 400:
                for href in page.locator("a").evaluate_all("elements => elements.map(a => a.href)"):
                    normalized = normalize_url(href)
                    if normalized and not should_skip(normalized):
                        discovered.append(normalized)
                        queue_items.append(normalized)
            browser.close()
    except Exception:
        pass

    queue = deque(dict.fromkeys(queue_items))
    visited = set()

    while queue and len(visited) < MAX_PAGES:
        url = queue.popleft()
        if not url or url in visited or should_skip(url):
            continue
        visited.add(url)
        try:
            response = SESSION.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                continue
            soup = BeautifulSoup(response.text, "lxml")
        except requests.RequestException:
            continue
        discovered.append(url)
        for anchor in soup.find_all("a", href=True):
            normalized = normalize_url(anchor["href"])
            if normalized and not should_skip(normalized) and normalized not in visited:
                queue.append(normalized)

    urls = list(dict.fromkeys(item for item in discovered if item))
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(urls, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    return urls


if __name__ == "__main__":
    urls = discover_pages()
    print(f"Discovered {len(urls)} unique internal pages")
    print(*urls, sep="\n")
