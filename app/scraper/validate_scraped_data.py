"""Validate scraped pages, Chroma chunks, metadata, and sample retrieval."""
import json

import chromadb
import ollama

from config import PROJECT_ROOT, settings
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "all_pages_content.json"
DISCOVERY_FILE = PROJECT_ROOT / "data" / "raw" / "discovered_urls.json"
REPORT_FILE = PROJECT_ROOT / "data" / "raw" / "validation_report.json"

TEST_QUERIES = [
    "what services do you offer",
    "home diagnostics",
    "how can I book a health checkup",
    "Timely Health membership",
    "contact Timely Health",
    "privacy policy",
    "doctor consultation",
    "medical camp",
    "recruitment",
    "attendance product",
]


def validate_pipeline(expected_chunks=None):
    pages = json.loads(RAW_FILE.read_text(encoding="utf-8")) if RAW_FILE.exists() else []
    discovered = json.loads(DISCOVERY_FILE.read_text(encoding="utf-8")) if DISCOVERY_FILE.exists() else []

    duplicate_urls = len(pages) - len({page["url"] for page in pages})
    empty_or_short = [
        page["url"] for page in pages
        if len((page.get("clean_text") or page.get("content") or "").strip()) < 80
    ]
    missing_metadata = []
    duplicate_chunk_documents = []

    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(name=settings.collection_name)
    indexed = collection.get(include=["documents", "metadatas"])
    ids = indexed.get("ids", [])
    documents = indexed.get("documents", []) or []
    metadatas = indexed.get("metadatas", []) or []

    seen_documents = set()
    for record_id, document, metadata in zip(ids, documents, metadatas):
        key = document.strip().lower()
        if key in seen_documents:
            duplicate_chunk_documents.append(key[:100])
        seen_documents.add(key)
        for field in ("source_url", "page_title", "section_heading",
                      "chunk_index", "content_hash", "scraped_at"):
            if not metadata or field not in metadata or metadata[field] in (None, ""):
                missing_metadata.append({"id": record_id, "field": field})
                break

    issues = []
    if duplicate_urls:
        issues.append(f"{duplicate_urls} duplicate page URL(s)")
    if empty_or_short:
        issues.append(f"{len(empty_or_short)} empty or very short page(s)")
    if duplicate_chunk_documents:
        issues.append(f"{len(duplicate_chunk_documents)} duplicate chunk(s)")
    if missing_metadata:
        issues.append(f"{len(missing_metadata)} chunk(s) missing metadata")
    if expected_chunks is not None and len(ids) != expected_chunks:
        issues.append(
            f"Chroma chunk count mismatch: found {len(ids)}, expected {expected_chunks}"
        )

    retrieval_results = []
    for query in TEST_QUERIES:
        embedded = ollama.embed(model=settings.embedding_model, input=query).embeddings[0]
        matches = collection.query(query_embeddings=[embedded], n_results=3,
                                   include=["documents", "metadatas", "distances"])
        rows = []
        for rank, (document, metadata, distance) in enumerate(zip(
            matches["documents"][0],
            matches["metadatas"][0],
            matches["distances"][0],
        ), start=1):
            rows.append({
                "rank": rank,
                "distance": round(float(distance), 6),
                "source_url": metadata.get("source_url"),
                "page_title": metadata.get("page_title"),
                "section_heading": metadata.get("section_heading"),
                "text_preview": document[:220],
            })
        retrieval_results.append({"query": query, "results": rows})
        print(f"\nQuery: {query}")
        for row in rows:
            print(row["rank"], row["distance"], row["source_url"], row["text_preview"])

    report = {
        "pages_found": len(discovered),
        "pages_scraped": len(pages),
        "empty_or_short_pages": empty_or_short,
        "duplicate_page_urls": duplicate_urls,
        "duplicate_chunks": len(duplicate_chunk_documents),
        "duplicate_chunk_examples": duplicate_chunk_documents[:10],
        "missing_metadata": missing_metadata,
        "chroma_chunk_count": len(ids),
        "expected_chunk_count": expected_chunks,
        "issues": issues,
        "test_queries": retrieval_results,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    print("\nVALIDATION SUMMARY")
    print("Pages found:", len(discovered))
    print("Pages scraped:", len(pages))
    print("Chroma chunks:", len(ids))
    print("Expected chunks:", expected_chunks)
    print("Issues:", len(issues))
    print("Report:", REPORT_FILE)
    return report


if __name__ == "__main__":
    validate_pipeline()
