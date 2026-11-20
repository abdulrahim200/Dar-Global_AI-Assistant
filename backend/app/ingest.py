from app.processor import create_chunks
from app.scrapers import scrape_all
from app.vector_store import EMBEDDING_MODEL, index_new_or_changed_chunks


def main() -> None:
    pages, processed_count, changed_count = scrape_all()
    chunks = create_chunks(pages, EMBEDDING_MODEL)
    indexed_count, unchanged_pages = index_new_or_changed_chunks(chunks)
    print(
        f"Processed {processed_count} URLs; {changed_count} pages changed; "
        f"indexed {indexed_count} chunks; {unchanged_pages} pages were unchanged."
    )


if __name__ == "__main__":
    main()

