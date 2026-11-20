# DarGlobal & Wasalt AI Property Assistant

A small RAG application that answers property questions using public pages collected from DarGlobal and Wasalt. The backend scrapes, cleans, chunks, embeds, and stores content locally; the React frontend provides a chat interface.

## Run locally

1. Copy `.env.example` to `.env` and add an OpenRouter API key.
2. Start the app: `docker compose up --build`.
3. In another terminal, collect and index public website content:
   `docker compose exec backend python -m app.ingest`
4. Open `http://localhost:5173`.

The scraper checks `robots.txt`, reads advertised XML sitemaps, follows same-domain public links, uses a delay between requests, and skips a source when access is disallowed. DarGlobal's official property site is `darglobal.co.uk`; `darglobal.com` currently serves unrelated content. Its project catalogue is JavaScript-rendered, so the scraper uses Playwright only for DarGlobal pages when the normal server HTML is empty.

Ingestion is resumable. Raw pages, hashes, HTTP cache validators, and the pending crawl queue are stored under `backend/data/raw`. Each run processes at most `CRAWL_PAGE_LIMIT` URLs (50 by default), so it can be safely repeated until the pending queue is empty. Existing pages return `304 Not Modified` where supported; ChromaDB embeds only new or changed pages and keeps vectors for unchanged pages.

## Architecture

`scrapers -> JSON -> processor -> Sentence Transformers -> ChromaDB -> FastAPI -> React`

The backend uses a multilingual Sentence Transformers model because the Wasalt pages contain Arabic content and users may ask questions in English or Arabic. It also uses the CPU-only PyTorch wheel because embeddings do not require a GPU. This keeps the Docker image practical for a small cloud deployment.

The chat endpoint only calls the LLM when relevant retrieved context exists. Responses include links to the original public pages.

## Deployment

The included `render.yaml` creates a Docker-based API, a static React site, and a persistent disk mounted at `/app/data` for ChromaDB. In Render, create a **New Blueprint Instance** from this repository and provide `OPENROUTER_API_KEY` when prompted. The Render service names determine the API and frontend URLs in the Blueprint; if you rename either service, update the matching URL values before deployment.

After both services are live, open the API's Render Shell and run:

```bash
python -m app.ingest
```

This fills the persistent disk with the current permitted website data. The frontend's Render URL is the public URL to share with recruiters.

