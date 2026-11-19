from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import FRONTEND_ORIGINS
from app.models import ChatRequest, ChatResponse
from app.rag import answer_question
from app.vector_store import get_collection

app = FastAPI(title="DarGlobal & Wasalt Property Assistant")
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "DarGlobal & Wasalt Property Assistant API", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "indexed_documents": get_collection().count()}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    answer, sources = answer_question(request.message, request.history)
    return ChatResponse(answer=answer, sources=sources)
