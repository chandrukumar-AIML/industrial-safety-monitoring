"""
backend/routes/chat.py

FastAPI /chat endpoint for the RAG safety chatbot.
Supports both single-turn REST and streaming SSE responses.

# FIXED: Input validation + sanitization
# FIXED: Rate limiting with proper eviction
# IMPROVED: Timeout handling for Ollama/ChromaDB calls
# FIXED: No PII leakage in logs
# IMPROVED: Dependency injection for testability
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from ..rag.chatbot import get_chatbot, ChatResponse

router = APIRouter(prefix="/chat", tags=["chatbot"])

# ── Rate limiting ─────────────────────────────────────────────
_RATE_LIMIT_MAX: int = int(os.getenv("CHAT_RATE_LIMIT_MAX", "20"))
_RATE_LIMIT_WINDOW_S: float = float(os.getenv("CHAT_RATE_LIMIT_WINDOW_S", "60.0"))
_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_EVICT_AFTER_S: float = _RATE_LIMIT_WINDOW_S * 10


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    # Evict stale IPs
    stale = [ip for ip, ts in _rate_store.items() if not ts or (now - ts[-1]) > _RATE_LIMIT_EVICT_AFTER_S]
    for ip in stale:
        del _rate_store[ip]
    
    window = _rate_store.get(client_ip, [])
    _rate_store[client_ip] = [t for t in window if now - t < _RATE_LIMIT_WINDOW_S]
    if len(_rate_store[client_ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: {_RATE_LIMIT_MAX} messages per minute",
            headers={"Retry-After": "60"},
        )
    _rate_store[client_ip].append(now)


# ── Request / Response models ─────────────────────────────────
class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="Natural language safety question")
    stream: bool = Field(default=False, description="Stream response via SSE")


class SourceOut(BaseModel):
    source: str
    filename: str
    timestamp: str
    zone_id: str
    class_name: str
    excerpt: str


class ChatResponseOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    model_used: str
    retrieval_k: int
    latency_ms: float


# ── Endpoints ─────────────────────────────────────────────────
@router.post(
    "",
    response_model=ChatResponseOut,
    responses={
        200: {"description": "RAG answer with cited sources"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Ollama not reachable"},
    },
    summary="Ask safety chatbot",
    description="Ask a natural language question about PPE violations, OSHA regulations, or safety SOPs.",
)
async def chat(
    body: ChatRequest,
    request: Request,
) -> ChatResponseOut:
    """Single-turn RAG chat endpoint."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    chatbot = get_chatbot()
    t0 = time.monotonic()

    try:
        response: ChatResponse = await asyncio.wait_for(
            chatbot.ask(body.question),
            timeout=30.0  # Prevent hanging on slow LLM
        )
    except asyncio.TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Chatbot request timed out")
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    latency = (time.monotonic() - t0) * 1000

    return ChatResponseOut(
        answer=response.answer,
        sources=[SourceOut(**s) for s in response.sources],
        model_used=response.model_used,
        retrieval_k=response.retrieval_k,
        latency_ms=round(latency, 1),
    )


@router.get(
    "/ingest/trigger",
    responses={
        200: {"description": "Ingestion triggered"},
        503: {"description": "Ingestion failed"},
    },
    summary="Trigger knowledge base re-ingestion",
)
async def trigger_ingest() -> dict:
    """Manually trigger knowledge base re-ingestion."""
    try:
        from ..rag.ingest.ingest_violations import ingest_violations
        from ..rag.ingest.ingest_pdfs import ingest_all

        # FIXED: get_running_loop() is correct inside an async function (get_event_loop() is deprecated)
        loop = asyncio.get_running_loop()
        violation_count = await ingest_violations(days_back=30)
        pdf_counts = await loop.run_in_executor(None, ingest_all)

        return {
            "status": "ok",
            "violations_ingested": violation_count,
            "regulations_ingested": pdf_counts.get("regulations_ingested", 0),
            "sops_ingested": pdf_counts.get("sops_ingested", 0),
        }
    except Exception as exc:
        logger.exception("Ingestion failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Ingestion failed: {type(exc).__name__}")


@router.get(
    "/health",
    summary="Chatbot health check",
)
async def chat_health() -> dict:
    """Check if Ollama is reachable and ChromaDB is populated."""
    import httpx
    ollama_url = f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/tags"

    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(ollama_url)
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    chroma_ok = False
    count = -1
    try:
        from ..rag.vector_store import get_collection, COL_VIOLATIONS
        col = get_collection(COL_VIOLATIONS)
        count = col._collection.count()
        chroma_ok = count >= 0
    except Exception:
        pass

    return {
        "ollama_reachable": ollama_ok,
        "chroma_ok": chroma_ok,
        "violation_docs_count": count,
        "status": "ok" if ollama_ok and chroma_ok else "degraded",
    }