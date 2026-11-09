"""Drop generic marketing slogan cards from index and retrieval."""
from __future__ import annotations

import re

MARKETING_HEADINGS = {
    "enterprise security",
    "scalable solutions",
    "dedicated support",
    "ai-driven insights",
    "automated workflows",
    "predictive decisions",
    "why choose us",
    "from systems to intelligence",
}

MARKETING_BLURBS = (
    "bank-level encryption and compliance standards",
    "grow your business with our flexible platform",
    "24/7 expert support for all your needs",
    "turn raw data into actionable intelligence instantly.",
    "self-optimizing systems that run your business on autopilot.",
    "anticipate market trends and operations before they happen.",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _flexible_pattern(phrase: str) -> str:
    return r"\s+".join(re.escape(part) for part in phrase.split())


def marketing_hit_count(text: str) -> int:
    text_n = _norm(text)
    return sum(1 for heading in MARKETING_HEADINGS if heading in text_n)


def is_marketing_section(heading: str = "", text: str = "") -> bool:
    heading_n = _norm(heading)
    remaining = strip_marketing_copy(text)
    remaining_n = _norm(remaining)
    if heading_n in MARKETING_HEADINGS and len(remaining_n) < 80:
        return True
    text_n = _norm(text)
    if not text_n:
        return False
    if text_n in MARKETING_HEADINGS:
        return True
    if len(remaining_n) >= 80:
        return False
    if marketing_hit_count(text) >= 3:
        return True
    for title in MARKETING_HEADINGS:
        if text_n == title or text_n.startswith(f"{title} "):
            if len(text_n.split()) <= 24:
                return True
    return False


def strip_marketing_copy(text: str) -> str:
    cleaned = text or ""
    for heading in MARKETING_HEADINGS:
        cleaned = re.sub(_flexible_pattern(heading), " ", cleaned, flags=re.I)
    for blurb in MARKETING_BLURBS:
        cleaned = re.sub(_flexible_pattern(blurb), " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?i)\bthe future\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" •-\n\t ")


JUNK_HEADINGS = {
    "frequently asked questions",
    "faq",
    "hired",
    "book demo",
    "start for free",
    "initial qualification",
    "first interview",
    "what our members say",
    "what our community says",
    "the future",
}

DEMO_UI_RE = re.compile(
    r"(?i)(\b\d+\s+days ago\b|linkedin|\bdrag and drop candidates\b|"
    r"\b(senior developer|agency)\b.{0,20}\b\d+\s+days ago|"
    r"^\s*(initial qualification|first interview)\b)",
)


def clean_page_text(text: str) -> str:
    cleaned = (text or "").replace("Iyrax", "Iryax").replace("iyrax", "iryax")
    cleaned = re.sub(r"(?i)\breimagined\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\bfeature\s+\d+\b", " ", cleaned)
    cleaned = re.sub(
        r"(?i)\b(learn more|view live|get bundle|contact sales|"
        r"book demo|start for free|view)\b",
        " ",
        cleaned,
    )
    kept = []
    for raw in re.split(r"[\n.]+", cleaned):
        line = raw.strip(" •-\t")
        if not line:
            continue
        if line.endswith("?") and len(line.split()) >= 4:
            continue
        if DEMO_UI_RE.search(line):
            continue
        kept.append(line)
    return re.sub(r"\s+", " ", ". ".join(kept)).strip(" .")


def is_junk_section(heading: str = "", text: str = "") -> bool:
    heading_n = _norm(heading)
    text_n = _norm(text)
    if not text_n:
        return True
    remaining = clean_page_text(text)
    if any(junk in heading_n for junk in JUNK_HEADINGS) and len(remaining.split()) < 18:
        return True
    questions = len(re.findall(r"\?", text or ""))
    words = max(1, len(text_n.split()))
    if questions >= 3 and questions >= words / 8:
        return True
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", text_n) and re.search(r"\bvolunteers?\b", text_n):
        return True
    return False


_STAT_BODY = re.compile(r"^[\d,.+%/\s]+$")
_CTA_LINE = re.compile(
    r"(?i)\b(book a doctor|chat with us|get bundle|contact sales|"
    r"organize a camp|get started)\b"
)


def is_catalog_card(heading: str = "", text: str = "") -> bool:
    """True for offering cards (title + real description), not stats or CTAs."""
    heading_n = _norm(heading).lstrip("✦ ").strip()
    words_h = [w for w in heading_n.split() if w]
    if not (1 <= len(words_h) <= 6):
        return False
    if heading_n in MARKETING_HEADINGS or heading_n in JUNK_HEADINGS:
        return False
    if re.search(r"^(all|complete)\b", heading_n) and re.search(
        r"\b(products?|bundle|solutions?)\b", heading_n
    ):
        return False
    if heading_n.startswith("✦") or "?" in heading_n:
        return False
    if re.search(r"\b(get started|questions? about|ready to)\b", heading_n):
        return False
    if re.match(r"^feature\s+\d+$", heading_n):
        return False
    if heading_n in {"paid", "live", "hired"}:
        return False
    if "," in heading_n:
        return False
    body = _norm(text)
    if heading_n and body.startswith(heading_n):
        body = body[len(heading_n):].strip()
    body = _norm(strip_marketing_copy(body))
    if not body or _STAT_BODY.match(body.replace(" ", "")):
        return False
    if re.match(r'^["“\'‘]', body) or re.search(r"\b(i've|i have|our rwa|our employee)\b", body):
        return False
    if _CTA_LINE.search(body) and len(body.split()) < 18:
        return False
    if len(body.split()) < 6:
        return False
    if re.search(r"we.?ve got you covered|that comes to you|all designed for", body):
        return False
    return True


def sanitize_record(doc, meta):
    heading = ""
    if isinstance(meta, dict):
        heading = str(meta.get("section_heading") or "")
        if isinstance(meta.get("page_title"), str):
            meta = dict(meta)
            meta["page_title"] = str(meta["page_title"]).replace("Iyrax", "Iryax")
    if is_marketing_section(heading, doc) or is_junk_section(heading, doc):
        return None
    cleaned = clean_page_text(strip_marketing_copy(str(doc or "")))
    if not cleaned or len(cleaned.split()) < 4:
        return None
    return cleaned, meta
