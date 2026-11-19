from __future__ import annotations

import requests

from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from app.models import ChatMessage, Source
from app.vector_store import search

SYSTEM_PROMPT = """You are a real estate assistant for DarGlobal and Wasalt. Answer only using the provided context. Do not invent property prices, locations, amenities, project details, or availability. If context is insufficient, say the information is not available in the collected data. Be helpful and concise, and distinguish the two sources when relevant. Use plain text only: do not use Markdown headings, bold markers, bullets, or tables."""


def unique_sources(results: list[dict]) -> list[Source]:
    sources: list[Source] = []
    seen_urls: set[str] = set()
    for result in results:
        metadata = result["metadata"]
        url = metadata["source_url"]
        if url not in seen_urls:
            sources.append(Source(title=metadata.get("title", "Source page"), source=metadata["source"], url=url))
            seen_urls.add(url)
    return sources


def answer_question(message: str, history: list[ChatMessage]) -> tuple[str, list[Source]]:
    results = [result for result in search(message) if result["distance"] <= 0.85]
    if not results:
        return "I couldn't find relevant information in the collected DarGlobal and Wasalt data. Try a different question after running ingestion.", []

    sources = unique_sources(results)
    if not OPENROUTER_API_KEY:
        return "Relevant information was found, but the server is missing OPENROUTER_API_KEY. Add it to enable generated answers.", sources

    context = "\n\n".join(f"[{item['metadata']['source']}] {item['text']}" for item in results)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": f"Context:\n{context}"}]
    messages.extend({"role": item.role, "content": item.content} for item in history)
    messages.append({"role": "user", "content": message})
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_MODEL, "messages": messages, "temperature": 0.2},
            timeout=45,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"], sources
    except requests.Timeout:
        return "The language model took too long to respond. Please try again.", sources
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 429:
            return "The language model is rate-limited. Please wait a moment and try again.", sources
        return "The language model could not be reached. Please try again later.", sources
    except (KeyError, ValueError, requests.RequestException):
        return "The language model returned an unexpected response. Please try again.", sources

