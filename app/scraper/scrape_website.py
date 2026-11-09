"""One-command website discovery, scraping, indexing, and validation."""
from app.scraper.scrape_all_pages import scrape_all_pages
from app.scraper.validate_scraped_data import validate_pipeline


def run_pipeline():
    pages, failures, expected_chunks = scrape_all_pages()
    validation = validate_pipeline(expected_chunks=expected_chunks)
    print("\nPipeline completed")
    print(f"Scraped pages: {len(pages)} | Failed pages: {len(failures)}")
    print(f"Validation issues: {len(validation['issues'])}")
    return validation


if __name__ == "__main__":
    run_pipeline()
