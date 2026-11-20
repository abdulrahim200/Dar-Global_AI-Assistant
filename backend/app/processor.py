from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.scrapers import ScrapedPage

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


@dataclass
class DocumentChunk:
    id: str
    text: str
    metadata: dict[str, str]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_text(text: str) -> list[str]:
    text = clean_text(text)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def create_chunks(pages: list[ScrapedPage], embedding_model: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    seen_text: set[str] = set()
    for page in pages:
        for index, chunk_text in enumerate(split_text(page.text)):
            normalized = clean_text(chunk_text).lower()
            if normalized in seen_text:
                continue
            seen_text.add(normalized)
            chunk_id = hashlib.sha256(f"{page.source_url}:{index}:{normalized}".encode()).hexdigest()
            metadata = {
                "source": page.source,
                "source_url": page.source_url,
                "title": page.title,
                "document_type": page.document_type,
                "content_hash": page.content_hash,
                "embedding_model": embedding_model,
            }
            if page.project_name:
                metadata["project_name"] = page.project_name
            if page.location:
                metadata["location"] = page.location
            chunks.append(DocumentChunk(id=chunk_id, text=chunk_text, metadata=metadata))
    return chunks

