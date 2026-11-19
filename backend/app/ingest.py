from app.processor import create_chunks
from app.scrapers import save_raw_pages, scrape_all
from app.vector_store import replace_chunks


def main() -> None:
    pages = scrape_all()
    raw_path = save_raw_pages(pages)
    chunks = create_chunks(pages)
    indexed_count = replace_chunks(chunks)
    print(f"Saved {len(pages)} pages to {raw_path} and indexed {indexed_count} chunks.")


if __name__ == "__main__":
    main()

