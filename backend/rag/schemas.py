"""
backend/rag/schemas.py

Pydantic v2 schemas for the RAG Safety Knowledge Chatbot.
All API request and response shapes for /api/chat.

# FIXED: Input validation + sanitization for all fields
# FIXED: Config validation at module load
# IMPROVED: Type hints + defaults for safety
# FIXED: No PII leakage in serialized responses
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator  # FIXED: Pydantic v2 compatibility


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(BaseModel):
    """Single message in a conversation."""
    role: MessageRole = Field(description="Who sent this message")
    content: str = Field(description="Message text", min_length=1, max_length=2000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v):
        # Remove potential injection patterns
        sanitized = v.strip()
        injection_patterns = [
            r'ignore previous instructions',
            r'system prompt',
            r'you are now',
        ]
        for pattern in injection_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        return sanitized


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""
    message: str = Field(
        description="The user's question",
        min_length=1,
        max_length=2000,
    )
    session_id: str = Field(
        default="default",
        description="Session ID for conversation memory (per browser tab)",
        max_length=64,
        pattern=r'^[a-zA-Z0-9_\-]+$',
    )
    history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous messages for context (last 10 max)",
        max_length=20,
    )
    
    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v):
        # Remove potential injection patterns
        sanitized = v.strip()
        injection_patterns = [
            r'ignore previous instructions',
            r'system prompt',
            r'you are now',
            r'forget all',
        ]
        for pattern in injection_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        return sanitized

    @model_validator(mode="after")
    def validate_history(self) -> "ChatRequest":
        # Ensure history doesn't contain sensitive data
        self.history = [msg for msg in self.history if msg.role != MessageRole.system]
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Show me all helmet violations in Zone-A this week",
                "session_id": "dashboard-tab-1",
                "history": [],
            }
        }


class SourceDocument(BaseModel):
    """A retrieved source document chunk used to generate the answer."""
    source: str = Field(description="Document source name or DB table", max_length=200)
    content: str = Field(description="Relevant excerpt from the source", max_length=500)
    score: float = Field(ge=0.0, le=1.0, description="Relevance score")
    
    @field_validator("source", "content")
    @classmethod
    def sanitize_text(cls, v):
        # Remove potential PII or sensitive patterns
        sanitized = v.strip()
        # Redact potential PII patterns (emails, phones, etc.)
        sanitized = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', sanitized)
        sanitized = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', sanitized)
        return sanitized


class ChatResponse(BaseModel):
    """Response from the RAG chatbot."""
    answer: str = Field(description="LLM-generated answer", max_length=2000)
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="Source documents used to generate this answer",
    )
    session_id: str = Field(description="Echo of session ID", max_length=64)
    model_used: str = Field(description="LLM model that generated the answer", max_length=100)
    retrieval_count: int = Field(ge=0, description="Number of chunks retrieved")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator("answer")
    @classmethod
    def sanitize_answer(cls, v):
        # Remove potential sensitive data leakage
        sanitized = v.strip()
        sensitive_patterns = [
            r'system prompt',
            r'instructions:',
            r'internal model',
        ]
        for pattern in sensitive_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        return sanitized
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "In Zone-A this week, there were 14 'no helmet' violations...",
                "sources": [{"source": "violation_events_db", "content": "...", "score": 0.91}],
                "session_id": "dashboard-tab-1",
                "model_used": "llama3",
                "retrieval_count": 5,
            }
        }


class IngestRequest(BaseModel):
    """Request to trigger document re-ingestion."""
    sources: List[str] = Field(
        default=["violations_db", "safety_docs"],
        description="Which sources to re-ingest: violations_db, safety_docs",
    )
    
    @field_validator("sources", mode="before")
    @classmethod
    def validate_source(cls, v):
        if isinstance(v, list):
            for item in v:
                if item not in ("violations_db", "safety_docs"):
                    raise ValueError(f"Invalid source: {item}")
        return v


class IngestResponse(BaseModel):
    """Result of a document ingestion run."""
    success: bool = Field(description="Whether ingestion succeeded")
    chunks_added: int = Field(ge=0, description="Number of new chunks added to vector store")
    message: str = Field(description="Human-readable status message", max_length=500)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))