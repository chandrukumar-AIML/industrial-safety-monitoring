"""
rag/ingest/ingest_pdfs.py

Ingests OSHA PDFs and safety SOP text files into ChromaDB.

# FIXED: Input validation + sanitization for all public methods
# FIXED: Config validation at module load
# IMPROVED: Secure file handling with path validation
# IMPROVED: Error handling with graceful fallbacks

Drop OSHA PDFs into:  rag/data/osha_pdfs/
Drop SOP text into:   rag/data/sops/

Run: python -m rag.ingest.ingest_pdfs
"""

from __future__ import annotations

import os
import pathlib
from typing import List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from loguru import logger

from rag.vector_store import add_documents, COL_REGULATIONS, COL_SOPS

# ── Config: Load from env with validation ─────────────────────
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
if not 100 <= CHUNK_SIZE <= 2000:
    logger.warning("RAG_CHUNK_SIZE invalid — using 800")
    CHUNK_SIZE = 800

CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
if not 0 <= CHUNK_OVERLAP <= 500:
    logger.warning("RAG_CHUNK_OVERLAP invalid — using 150")
    CHUNK_OVERLAP = 150

TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
PDF_DIR = DATA_DIR / "osha_pdfs"
SOP_DIR = DATA_DIR / "sops"

# Security: restrict ingest directories
ALLOWED_INGEST_DIRS = [os.path.abspath(d.strip()) for d in os.getenv("ALLOWED_INGEST_DIRS", "./rag/data").split(",") if d.strip()]

# ── Helper: Validate file path ───────────────────────────────
def _validate_file_path(path: pathlib.Path, name: str) -> pathlib.Path:
    """Validate that file path is within allowed directories."""
    resolved = path.resolve()
    if not any(str(resolved).startswith(d) for d in ALLOWED_INGEST_DIRS):
        raise ValueError(f"{name} not in allowed directories: {resolved}")
    return resolved

def _load_pdfs(pdf_dir: pathlib.Path) -> List[Document]:
    """Load and chunk all PDFs in the given directory."""
    # Validate directory
    pdf_dir = _validate_file_path(pdf_dir, "PDF directory")
    
    docs = []
    pdfs = list(pdf_dir.glob("*.pdf"))
    
    if not pdfs:
        logger.warning("No PDFs found in {}", pdf_dir)
        return []
    
    for pdf_path in pdfs:
        logger.info("Loading PDF: {}", pdf_path.name)
        try:
            loader = PyPDFLoader(str(pdf_path))
            pages = loader.load()
            chunks = TEXT_SPLITTER.split_documents(pages)
            
            # Tag each chunk with source metadata
            for chunk in chunks:
                chunk.metadata["source"] = "osha_pdf"
                chunk.metadata["filename"] = pdf_path.name
                chunk.metadata["doc_type"] = "regulation"
            
            docs.extend(chunks)
            logger.info("  {} → {} chunks", pdf_path.name, len(chunks))
        except Exception as exc:
            logger.error("Failed to load {}: {}", pdf_path.name, exc)
            continue
    
    return docs


def _load_sops(sop_dir: pathlib.Path) -> List[Document]:
    """Load and chunk all .txt SOP files."""
    # Validate directory
    sop_dir = _validate_file_path(sop_dir, "SOP directory")
    
    docs = []
    txts = list(sop_dir.glob("*.txt"))
    
    if not txts:
        logger.warning("No SOP files found in {}", sop_dir)
        return []
    
    for txt_path in txts:
        logger.info("Loading SOP: {}", txt_path.name)
        try:
            loader = TextLoader(str(txt_path), encoding="utf-8")
            pages = loader.load()
            chunks = TEXT_SPLITTER.split_documents(pages)
            
            for chunk in chunks:
                chunk.metadata["source"] = "safety_sop"
                chunk.metadata["filename"] = txt_path.name
                chunk.metadata["doc_type"] = "sop"
            
            docs.extend(chunks)
            logger.info("  {} → {} chunks", txt_path.name, len(chunks))
        except Exception as exc:
            logger.error("Failed to load {}: {}", txt_path.name, exc)
            continue
    
    return docs


def ingest_all() -> dict:
    """
    Ingest all PDFs and SOPs. Returns counts per collection.
    
    # IMPROVED: Error handling with graceful fallbacks
    """
    # Ensure directories exist
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    SOP_DIR.mkdir(parents=True, exist_ok=True)
    
    pdf_docs = _load_pdfs(PDF_DIR)
    sop_docs = _load_sops(SOP_DIR)
    
    pdf_count = add_documents(COL_REGULATIONS, pdf_docs) if pdf_docs else 0
    sop_count = add_documents(COL_SOPS, sop_docs) if sop_docs else 0
    
    return {
        "regulations_ingested": pdf_count,
        "sops_ingested": sop_count,
    }


if __name__ == "__main__":
    result = ingest_all()
    print(f"Ingestion complete: {result}")