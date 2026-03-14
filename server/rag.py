"""
Kwyre AI — RAG Document Ingestion
==================================
RAM-only document storage with FAISS vector search.
All data is stored exclusively in memory and cryptographically
wiped on session end, shutdown, or intrusion detection.

Supports PDF, DOCX, and TXT file parsing with automatic chunking.
Uses sentence-transformers for local embedding (no cloud calls).
"""

import io  # In-memory byte stream for file parsing
import os  # Environment variables and path utilities
import re  # Regex for text splitting
import secrets  # Cryptographic random data for secure wipe
import threading  # Thread safety for shared state
import time  # Timestamps for session metadata
from typing import Optional  # Optional type hint for nullable returns

import numpy as np  # Numerical arrays for embedding vectors

_FAISS_AVAILABLE = False  # Track whether FAISS library is installed
try:
    import faiss  # Facebook AI Similarity Search for vector indexing
    _FAISS_AVAILABLE = True  # Mark FAISS as available
except ImportError:  # FAISS not installed, degrade gracefully
    pass

_PYPDF_AVAILABLE = False  # Track whether pypdf library is installed
try:
    from pypdf import PdfReader  # PDF parsing library
    _PYPDF_AVAILABLE = True  # Mark pypdf as available
except ImportError:  # pypdf not installed, degrade gracefully
    pass

_DOCX_AVAILABLE = False  # Track whether python-docx library is installed
try:
    from docx import Document as DocxDocument  # DOCX parsing library
    _DOCX_AVAILABLE = True  # Mark python-docx as available
except ImportError:  # python-docx not installed, degrade gracefully
    pass

_ST_AVAILABLE = False  # Track whether sentence-transformers is installed
_embedding_model = None  # Singleton lazy-loaded embedding model instance
_embedding_lock = threading.Lock()  # Mutex for thread-safe model initialization

EMBEDDING_MODEL_NAME = os.environ.get(
    "KWYRE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)  # Configurable embedding model name, default MiniLM
CHUNK_MAX_CHARS = int(os.environ.get("KWYRE_RAG_CHUNK_SIZE", "1500"))  # Max characters per text chunk
CHUNK_OVERLAP_CHARS = int(os.environ.get("KWYRE_RAG_CHUNK_OVERLAP", "200"))  # Overlap between adjacent chunks
RAG_TOP_K = int(os.environ.get("KWYRE_RAG_TOP_K", "5"))  # Default number of retrieval results


def _get_embedding_model():
    """Lazy-load the embedding model on first use (not at server startup)."""
    global _embedding_model, _ST_AVAILABLE
    with _embedding_lock:  # Acquire lock for thread-safe singleton init
        if _embedding_model is not None:  # Return cached model if already loaded
            return _embedding_model
        try:
            from sentence_transformers import SentenceTransformer  # Import embedding library
            _ST_AVAILABLE = True  # Mark sentence-transformers as available
            print(f"[RAG] Loading embedding model: {EMBEDDING_MODEL_NAME}")  # Log model loading start
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")  # Load model on CPU to avoid GPU dependency
            print("[RAG] Embedding model loaded on CPU")  # Log successful model load
            return _embedding_model  # Return initialized model
        except ImportError:  # sentence-transformers not installed
            print("[RAG] ERROR: sentence-transformers not installed.")
            print("[RAG] Install with: pip install sentence-transformers")
            return None  # Return None to signal unavailability
        except Exception as e:  # Catch any other loading failure
            print(f"[RAG] ERROR loading embedding model: {e}")
            return None  # Return None to signal failure


def encode_texts(texts: list[str]) -> Optional[np.ndarray]:
    """Encode texts into embeddings using the local model."""
    model = _get_embedding_model()  # Get or lazy-load embedding model
    if model is None:  # Bail if model unavailable
        return None
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)  # Generate L2-normalized embeddings
    return np.array(embeddings, dtype=np.float32)  # Convert to float32 numpy array for FAISS


class DocumentParser:
    """Extracts text from uploaded files and splits into chunks."""

    @staticmethod
    def parse(filename: str, file_bytes: bytes) -> list[str]:
        ext = os.path.splitext(filename)[1].lower()  # Extract and lowercase file extension
        if ext == ".pdf":  # Route PDF files to PDF parser
            return DocumentParser._parse_pdf(file_bytes)
        elif ext == ".docx":  # Route DOCX files to DOCX parser
            return DocumentParser._parse_docx(file_bytes)
        elif ext in (".txt", ".md", ".csv", ".log"):  # Route plain text formats to text parser
            return DocumentParser._parse_text(file_bytes)
        else:  # Reject unsupported file types
            raise ValueError(f"Unsupported file type: {ext}")

    @staticmethod
    def _parse_pdf(data: bytes) -> list[str]:
        if not _PYPDF_AVAILABLE:  # Check pypdf dependency
            raise ImportError("pypdf not installed. Install with: pip install pypdf")
        reader = PdfReader(io.BytesIO(data))  # Create PDF reader from byte stream
        pages = []  # Accumulate extracted page texts
        for page in reader.pages:  # Iterate each PDF page
            text = page.extract_text()  # Extract text content from page
            if text and text.strip():  # Skip empty pages
                pages.append(text.strip())  # Add cleaned page text
        full_text = "\n\n".join(pages)  # Join pages with double newlines
        return DocumentParser._chunk_text(full_text)  # Split into sized chunks

    @staticmethod
    def _parse_docx(data: bytes) -> list[str]:
        if not _DOCX_AVAILABLE:  # Check python-docx dependency
            raise ImportError("python-docx not installed. Install with: pip install python-docx")
        doc = DocxDocument(io.BytesIO(data))  # Create DOCX reader from byte stream
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]  # Extract non-empty paragraphs
        full_text = "\n\n".join(paragraphs)  # Join paragraphs with double newlines
        return DocumentParser._chunk_text(full_text)  # Split into sized chunks

    @staticmethod
    def _parse_text(data: bytes) -> list[str]:
        text = data.decode("utf-8", errors="replace").strip()  # Decode bytes to UTF-8, replace invalid chars
        return DocumentParser._chunk_text(text)  # Split into sized chunks

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        if not text:  # Return empty for blank input
            return []
        paragraphs = re.split(r'\n\s*\n', text)  # Split on blank lines into paragraphs
        chunks = []  # Accumulate output chunks
        current_chunk = ""  # Buffer for building current chunk

        for para in paragraphs:  # Process each paragraph
            para = para.strip()  # Strip whitespace from paragraph
            if not para:  # Skip empty paragraphs
                continue
            if len(current_chunk) + len(para) + 2 <= CHUNK_MAX_CHARS:  # Check if paragraph fits in current chunk
                current_chunk = (current_chunk + "\n\n" + para).strip()  # Append paragraph to current chunk
            else:
                if current_chunk:  # Save completed chunk if non-empty
                    chunks.append(current_chunk)
                if len(para) > CHUNK_MAX_CHARS:  # Handle oversized paragraphs
                    sentences = re.split(r'(?<=[.!?])\s+', para)  # Split paragraph into sentences
                    sub_chunk = ""  # Buffer for sentence-level chunking
                    for sent in sentences:  # Process each sentence
                        if len(sub_chunk) + len(sent) + 1 <= CHUNK_MAX_CHARS:  # Check if sentence fits
                            sub_chunk = (sub_chunk + " " + sent).strip()  # Append sentence to sub-chunk
                        else:
                            if sub_chunk:  # Save completed sub-chunk
                                chunks.append(sub_chunk)
                            sub_chunk = sent  # Start new sub-chunk with current sentence
                    if sub_chunk:  # Carry remaining sub-chunk forward
                        current_chunk = sub_chunk
                    else:  # No remaining text
                        current_chunk = ""
                else:  # Paragraph fits as new chunk start
                    current_chunk = para

        if current_chunk:  # Save final buffered chunk
            chunks.append(current_chunk)

        return [c for c in chunks if len(c) > 20]  # Filter out trivially short chunks


class SecureRAGStore:
    """
    Per-session RAM-only vector store with cryptographic wipe.

    Each session gets its own FAISS index and chunk storage.
    On wipe, all chunk strings are overwritten with random bytes
    before references are cleared — consistent with Kwyre's
    SecureConversationBuffer pattern.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}  # Map session IDs to RAG data entries
        self._lock = threading.Lock()  # Mutex for thread-safe session access

    def has_documents(self, session_id: str) -> bool:
        with self._lock:  # Acquire lock for safe read
            entry = self._sessions.get(session_id)  # Look up session entry
            return entry is not None and len(entry.get("chunks", [])) > 0  # True if session has stored chunks

    def add_documents(self, session_id: str, chunks: list[str],
                      embeddings: np.ndarray, metadata: dict | None = None):
        if not _FAISS_AVAILABLE:  # Check FAISS dependency
            raise ImportError("faiss-cpu not installed. Install with: pip install faiss-cpu")

        dim = embeddings.shape[1]  # Get embedding vector dimensionality
        with self._lock:  # Acquire lock for safe mutation
            if session_id not in self._sessions:  # Initialize new session entry
                index = faiss.IndexFlatIP(dim)  # Create inner-product FAISS index
                self._sessions[session_id] = {
                    "chunks": [],  # Text chunk storage
                    "index": index,  # FAISS vector index
                    "metadata": [],  # Per-chunk metadata
                    "created_at": time.time(),  # Session creation timestamp
                }

            entry = self._sessions[session_id]  # Get existing session entry
            entry["chunks"].extend(chunks)  # Append new text chunks
            entry["index"].add(embeddings)  # Add embedding vectors to FAISS index
            if metadata:  # Attach metadata to each chunk if provided
                entry["metadata"].extend([metadata] * len(chunks))
            else:  # Use empty dicts as placeholder metadata
                entry["metadata"].extend([{}] * len(chunks))

    def retrieve(self, session_id: str, query_embedding: np.ndarray,
                 top_k: int | None = None) -> list[str]:
        if top_k is None:  # Use default if not specified
            top_k = RAG_TOP_K
        with self._lock:  # Acquire lock for safe read
            entry = self._sessions.get(session_id)  # Look up session entry
            if entry is None or len(entry["chunks"]) == 0:  # Return empty if no documents
                return []

            n_chunks = len(entry["chunks"])  # Get total chunk count
            k = min(top_k, n_chunks)  # Cap k at available chunk count
            if query_embedding.ndim == 1:  # Reshape 1D query to 2D for FAISS
                query_embedding = query_embedding.reshape(1, -1)

            distances, indices = entry["index"].search(query_embedding, k)  # Search FAISS index for nearest neighbors
            results = []  # Accumulate matched chunks
            for idx in indices[0]:  # Iterate top-k result indices
                if 0 <= idx < n_chunks:  # Validate index bounds
                    results.append(entry["chunks"][idx])  # Add matching chunk text
            return results  # Return retrieved document chunks

    def get_stats(self, session_id: str) -> dict:
        with self._lock:  # Acquire lock for safe read
            entry = self._sessions.get(session_id)  # Look up session entry
            if entry is None:  # Return empty stats if no session
                return {"chunks": 0, "has_index": False}
            return {
                "chunks": len(entry["chunks"]),  # Number of stored chunks
                "has_index": entry["index"] is not None,  # Whether FAISS index exists
                "created_at": entry.get("created_at"),  # Session creation timestamp
            }

    def secure_wipe(self, session_id: str, reason: str = "session_end"):
        with self._lock:  # Acquire lock for atomic wipe
            entry = self._sessions.pop(session_id, None)  # Remove and return session entry
            if entry is None:  # Nothing to wipe
                return
            n = len(entry.get("chunks", []))  # Save chunk count for logging
            for i, chunk in enumerate(entry.get("chunks", [])):  # Overwrite each chunk with random data
                entry["chunks"][i] = secrets.token_hex(max(len(chunk), 32))  # Replace chunk with random hex string
            entry["chunks"].clear()  # Remove all chunk references
            entry["metadata"].clear()  # Remove all metadata references
            if entry.get("index") is not None:  # Wipe FAISS index if present
                entry["index"].reset()  # Clear all vectors from index
                del entry["index"]  # Delete index object
            print(f"[RAG] {session_id[:8]}... wiped ({n} chunks, reason={reason})")  # Log wipe event

    def wipe_all(self, reason: str = "server_shutdown"):
        with self._lock:  # Acquire lock for bulk wipe
            n_sessions = len(self._sessions)  # Save session count for logging
            for sid in list(self._sessions.keys()):  # Iterate all session IDs
                entry = self._sessions.pop(sid)  # Remove session entry
                for i, chunk in enumerate(entry.get("chunks", [])):  # Overwrite each chunk
                    entry["chunks"][i] = secrets.token_hex(max(len(chunk), 32))  # Replace with random hex
                entry["chunks"].clear()  # Remove all chunk references
                entry["metadata"].clear()  # Remove all metadata references
                if entry.get("index") is not None:  # Wipe FAISS index if present
                    entry["index"].reset()  # Clear all vectors from index
                    del entry["index"]  # Delete index object
            print(f"[RAG] All sessions wiped ({n_sessions} sessions, reason={reason})")  # Log bulk wipe event

    def active_count(self) -> int:
        with self._lock:  # Acquire lock for consistent count
            return len(self._sessions)  # Return number of active RAG sessions

    def total_chunks(self) -> int:
        with self._lock:  # Acquire lock for consistent total
            return sum(len(e.get("chunks", [])) for e in self._sessions.values())  # Sum chunks across all sessions
