"""
backend/rag/retriever.py

Semantic retrieval layer for the RAG Safety Knowledge Chatbot.

# FIXED: Input validation + sanitization for all public methods
# FIXED: Config validation at module load
# IMPROVED: Metadata filter validation + sanitization
# IMPROVED: Dependency injection for testability
# FIXED: No PII leakage in logs
# IMPROVED: Error handling with graceful fallbacks

Responsibilities:
  - Embed the user's question using the same HuggingFace model
  - Query ChromaDB for top-K most similar chunks
  - Apply metadata filters (zone, date range, source type)
  - Return ranked SourceDocument objects with relevance scores

Design: Uses ChromaDB's cosine similarity. No reranker needed at
this scale (< 100K chunks). Add cross-encoder reranker if corpus
exceeds 1M chunks.
"""

from __future__ import annotations

import os
import re
from typing import List, Optional, Dict, Any, Protocol, runtime_checkable

from loguru import logger
from pydantic import BaseModel, Field, field_validator  # FIXED: Pydantic v2 compatibility

from .schemas import SourceDocument
from .ingestor import SafetyDocumentIngestor, CHROMA_COLLECTION

# ── Config: Load from env with validation ─────────────────────
def _validate_int_range(name: str, value: str, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(value)
        if not min_val <= val <= max_val:
            raise ValueError(f"{name} must be {min_val}-{max_val}, got {val}")
        return val
    except ValueError:
        logger.warning("{} invalid: {} — using default {}", name, value, default)
        return default

def _validate_float_range(name: str, value: str, default: float, min_val: float, max_val: float) -> float:
    try:
        val = float(value)
        if not min_val <= val <= max_val:
            raise ValueError(f"{name} must be {min_val}-{max_val}, got {val}")
        return val
    except ValueError:
        logger.warning("{} invalid: {} — using default {}", name, value, default)
        return default

TOP_K_RETRIEVAL = _validate_int_range("RAG_TOP_K", os.getenv("RAG_TOP_K", "6"), 6, 1, 20)
MIN_SCORE = _validate_float_range("RAG_MIN_SCORE", os.getenv("RAG_MIN_SCORE", "0.3"), 0.3, 0.0, 1.0)

# ── Protocol for dependency injection ─────────────────────────
@runtime_checkable
class EmbeddingProtocol(Protocol):
    """Protocol for embedding model — enables mocking in tests."""
    def embed_query(self, text: str) -> List[float]: ...

@runtime_checkable
class ChromaCollectionProtocol(Protocol):
    """Protocol for Chroma collection — enables mocking in tests."""
    def query(self, **kwargs) -> Dict[str, Any]: ...
    def count(self) -> int: ...

# ── Pydantic models for structured validation ─────────────────
class RetrieverConfig(BaseModel):
    """Validated configuration for retriever."""
    top_k: int = Field(default=TOP_K_RETRIEVAL, ge=1, le=20)
    min_score: float = Field(default=MIN_SCORE, ge=0, le=1)
    
    @field_validator("top_k")
    @classmethod
    def warn_on_large_top_k(cls, v):
        if v > 10:
            logger.warning("Large top_k={} may increase latency", v)
        return v

class SafetyRetriever:
    """
    Retrieves relevant context chunks from ChromaDB for a given query.
    
    # FIXED: Input validation + sanitization
    # IMPROVED: Metadata filter validation + sanitization
    # IMPROVED: Dependency injection for testability
    
    Usage:
        retriever = SafetyRetriever(ingestor)
        docs = retriever.retrieve("helmet violations in zone A last week")
    """

    def __init__(
        self,
        ingestor: SafetyDocumentIngestor,
        config: Optional[RetrieverConfig] = None,
    ):
        self._config = config or RetrieverConfig()
        self._collection: ChromaCollectionProtocol = ingestor.collection
        self._embeddings: EmbeddingProtocol = ingestor.embeddings

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        zone_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> List[SourceDocument]:
        """
        Retrieve top-K relevant document chunks for the query.
        
        # FIXED: Input validation + sanitization
        # IMPROVED: Metadata filter validation
        
        Args:
            query: User's natural language question
            top_k: Max chunks to retrieve (overrides config)
            zone_filter: Optional zone_id to filter by (e.g. "zone-A")
            source_filter: Optional source type ("violations_db" | "safety_document")
            date_filter: Optional ISO date string to filter by (e.g. "2024-01-15")
            
        Returns:
            List of SourceDocument ordered by relevance (highest first)
        """
        # Sanitize and validate query
        if not query or not query.strip():
            return []
        sanitized_query = query.strip()
        if len(sanitized_query) > 2000:
            logger.warning("Query too long: {} chars — truncating", len(sanitized_query))
            sanitized_query = sanitized_query[:2000]
        
        # Validate filters
        if zone_filter and not re.match(r'^[a-zA-Z0-9_\-]+$', zone_filter):
            logger.warning("Invalid zone_filter: {} — ignoring", zone_filter)
            zone_filter = None
        if source_filter and source_filter not in ("violations_db", "safety_document"):
            logger.warning("Invalid source_filter: {} — ignoring", source_filter)
            source_filter = None
        if date_filter and not re.match(r'^\d{4}-\d{2}-\d{2}$', date_filter):
            logger.warning("Invalid date_filter: {} — ignoring", date_filter)
            date_filter = None
        
        # Use config top_k if not overridden
        k = top_k if top_k is not None else self._config.top_k
        k = min(k, self._collection.count() or 1)  # Don't request more than available
        
        # Build ChromaDB where filter
        where_clause = self._build_where_clause(zone_filter, source_filter, date_filter)
        
        # Embed the query
        try:
            query_embedding = self._embeddings.embed_query(sanitized_query)
        except Exception as exc:
            logger.error("Embedding failed: {} — returning empty", exc)
            return []
        
        # Query ChromaDB
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_clause:
            kwargs["where"] = where_clause
        
        try:
            results = self._collection.query(**kwargs)
        except Exception as exc:
            logger.error("ChromaDB query failed: {} — returning empty", exc)
            return []
        
        # Parse results
        docs: List[SourceDocument] = []
        if not results.get("ids") or not results["ids"][0]:
            return docs
        
        for doc_text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity score
            score = max(0.0, 1.0 - distance)
            if score < self._config.min_score:
                continue
            
            # Build source label
            source_label = metadata.get("source", "unknown")
            if metadata.get("doc_type") == "violation_summary":
                source_label = f"Violation DB ({metadata.get('date', '?')} · {metadata.get('zone', '?')})"
            
            # Truncate content for API response
            content = doc_text[:400] + ("..." if len(doc_text) > 400 else "")
            
            docs.append(SourceDocument(
                source=source_label,
                content=content,
                score=round(score, 4),
            ))
        
        # Sort by score descending
        docs.sort(key=lambda d: d.score, reverse=True)
        
        logger.debug("Retrieved {} chunks for query: {!r}", len(docs), sanitized_query[:60])
        return docs

    def format_context(self, docs: List[SourceDocument]) -> str:
        """
        Format retrieved documents into a single context string for the LLM prompt.
        
        Each chunk is labelled with its source so the LLM can attribute answers.
        """
        if not docs:
            return "No relevant context found in the safety knowledge base."
        
        parts = []
        for i, doc in enumerate(docs, 1):
            parts.append(
                f"[Source {i}: {doc.source} | Relevance: {doc.score:.0%}]\n"
                f"{doc.content}"
            )
        return "\n\n---\n\n".join(parts)

    # ── Private helpers ────────────────────────────────────────

    def _build_where_clause(
        self,
        zone_filter: Optional[str],
        source_filter: Optional[str],
        date_filter: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Build ChromaDB metadata where clause."""
        conditions = []
        
        if zone_filter:
            conditions.append({"zone": {"$eq": zone_filter}})
        if source_filter:
            conditions.append({"source": {"$eq": source_filter}})
        if date_filter:
            conditions.append({"date": {"$eq": date_filter}})
        
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def get_diagnostics(self) -> dict:
        """Return retriever status for health checks."""
        return {
            "config": {
                "top_k": self._config.top_k,
                "min_score": self._config.min_score,
            },
            "collection_count": self._collection.count(),
        }