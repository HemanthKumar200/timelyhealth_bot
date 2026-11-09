"""Render JavaScript pages with a project-local Playwright Chromium."""
from __future__ import annotations

import os
from pathlib import Path

BROWSERS_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "timelyhealth-playwright"
if os.name != "nt":
    BROWSERS_DIR = Path.home() / ".cache" / "timelyhealth-playwright"


def use_project_browsers() -> Path:
    BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)
    return BROWSERS_DIR


def render_page_html(url: str, user_agent: str, timeout_ms: int = 45000) -> str | None:
    """Return rendered HTML, or None if Chromium is missing / the page fails."""
    use_project_browsers()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"    [Playwright is not installed; cannot render {url}]")
        return None

    wants_prices = any(part in (url or "").lower() for part in ("membership", "pricing", "plan"))
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=user_agent)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_function(
                    "document.body && (document.body.innerText || '').trim().length > 80",
                    timeout=15000,
                )
            except Exception:
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    page.wait_for_timeout(1500)
            try:
                page.evaluate(
                    "window.scrollTo(0, Math.max(document.body.scrollHeight, 800))"
                )
            except Exception:
                pass
            price_timeout = 12000 if wants_prices else 2500
            try:
                page.wait_for_function(
                    r"() => /₹\s*\d|Rs\.?\s*\d|\d+\s*\/mo/i.test(document.body.innerText || '')",
                    timeout=price_timeout,
                )
            except Exception:
                page.wait_for_timeout(3500 if wants_prices else 800)
            return page.content()
    except Exception as exc:
        print(f"    [Playwright fallback failed for {url}: {exc}]")
        return None
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
