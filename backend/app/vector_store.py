from functools import lru_cache

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import CHROMA_DIR
from app.processor import DocumentChunk

COLLECTION_NAME = "property_documents"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache
def get_collection():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def index_chunks(chunks: list[DocumentChunk]) -> int:
    if not chunks:
        return 0
    collection = get_collection()
    model = get_embedding_model()
    embeddings = model.encode([chunk.text for chunk in chunks], normalize_embeddings=True).tolist()
    collection.upsert(
        ids=[chunk.id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
        embeddings=embeddings,
    )
    return len(chunks)


def index_new_or_changed_chunks(chunks: list[DocumentChunk]) -> tuple[int, int]:
    """Upsert only documents whose page content or embedding model changed."""
    collection = get_collection()
    chunks_by_url: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        chunks_by_url.setdefault(chunk.metadata["source_url"], []).append(chunk)

    to_index: list[DocumentChunk] = []
    unchanged_pages = 0
    for source_url, page_chunks in chunks_by_url.items():
        existing = collection.get(where={"source_url": source_url}, include=["metadatas"])
        existing_metadata = existing.get("metadatas", [])
        incoming_hash = page_chunks[0].metadata["content_hash"]
        is_unchanged = bool(existing_metadata) and all(
            metadata.get("content_hash") == incoming_hash
            and metadata.get("embedding_model") == EMBEDDING_MODEL
            for metadata in existing_metadata
        )
        if is_unchanged:
            unchanged_pages += 1
            continue
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
        to_index.extend(page_chunks)
    return index_chunks(to_index), unchanged_pages


def search(question: str, limit: int = 5) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    embedding = get_embedding_model().encode(question, normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=[embedding], n_results=limit, include=["documents", "metadatas", "distances"])
    return [
        {"text": text, "metadata": metadata, "distance": distance}
        for text, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    ]

