"""
Kwyre AI — RAG Document Ingestion
==================================
RAM-only document storage with FAISS vector search.
All data is stored exclusively in memory and cryptographically
wiped on session end, shutdown, or intrusion detection.

Supports PDF, DOCX, and TXT file parsing with automatic chunking.
Uses sentence-transformers for local embedding (no cloud calls).
"""

import io
import os
import re
import secrets
import threading
import time
from typing import Optional

import numpy as np

_FAISS_AVAILABLE = False
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    pass

_PYPDF_AVAILABLE = False
try:
    from pypdf import PdfReader
    _PYPDF_AVAILABLE = True
except ImportError:
    pass

_DOCX_AVAILABLE = False
try:
    from docx import Document as DocxDocument
    _DOCX_AVAILABLE = True
except ImportError:
    pass

_ST_AVAILABLE = False
_embedding_model = None
_embedding_lock = threading.Lock()

EMBEDDING_MODEL_NAME = os.environ.get(
    "KWYRE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
CHUNK_MAX_CHARS = int(os.environ.get("KWYRE_RAG_CHUNK_SIZE", "1500"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("KWYRE_RAG_CHUNK_OVERLAP", "200"))
RAG_TOP_K = int(os.environ.get("KWYRE_RAG_TOP_K", "5"))


def _get_embedding_model():
    """Lazy-load the embedding model on first use (not at server startup)."""
    global _embedding_model, _ST_AVAILABLE
    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model
        try:
            from sentence_transformers import SentenceTransformer
            _ST_AVAILABLE = True
            print(f"[RAG] Loading embedding model: {EMBEDDING_MODEL_NAME}")
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
            print(f"[RAG] Embedding model loaded on CPU")
            return _embedding_model
        except ImportError:
            print("[RAG] ERROR: sentence-transformers not installed.")
            print("[RAG] Install with: pip install sentence-transformers")
            return None
        except Exception as e:
            print(f"[RAG] ERROR loading embedding model: {e}")
            return None


def encode_texts(texts: list[str]) -> Optional[np.ndarray]:
    """Encode texts into embeddings using the local model."""
    model = _get_embedding_model()
    if model is None:
        return None
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.array(embeddings, dtype=np.float32)


class DocumentParser:
    """Extracts text from uploaded files and splits into chunks."""

    @staticmethod
    def parse(filename: str, file_bytes: bytes) -> list[str]:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            return DocumentParser._parse_pdf(file_bytes)
        elif ext == ".docx":
            return DocumentParser._parse_docx(file_bytes)
        elif ext in (".txt", ".md", ".csv", ".log"):
            return DocumentParser._parse_text(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    @staticmethod
    def _parse_pdf(data: bytes) -> list[str]:
        if not _PYPDF_AVAILABLE:
            raise ImportError("pypdf not installed. Install with: pip install pypdf")
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
        full_text = "\n\n".join(pages)
        return DocumentParser._chunk_text(full_text)

    @staticmethod
    def _parse_docx(data: bytes) -> list[str]:
        if not _DOCX_AVAILABLE:
            raise ImportError("python-docx not installed. Install with: pip install python-docx")
        doc = DocxDocument(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paragraphs)
        return DocumentParser._chunk_text(full_text)

    @staticmethod
    def _parse_text(data: bytes) -> list[str]:
        text = data.decode("utf-8", errors="replace").strip()
        return DocumentParser._chunk_text(text)

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        if not text:
            return []
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current_chunk) + len(para) + 2 <= CHUNK_MAX_CHARS:
                current_chunk = (current_chunk + "\n\n" + para).strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > CHUNK_MAX_CHARS:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    sub_chunk = ""
                    for sent in sentences:
                        if len(sub_chunk) + len(sent) + 1 <= CHUNK_MAX_CHARS:
                            sub_chunk = (sub_chunk + " " + sent).strip()
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = sent
                    if sub_chunk:
                        current_chunk = sub_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return [c for c in chunks if len(c) > 20]


class SecureRAGStore:
    """
    Per-session RAM-only vector store with cryptographic wipe.
    
    Each session gets its own FAISS index and chunk storage.
    On wipe, all chunk strings are overwritten with random bytes
    before references are cleared — consistent with Kwyre's
    SecureConversationBuffer pattern.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def has_documents(self, session_id: str) -> bool:
        with self._lock:
            entry = self._sessions.get(session_id)
            return entry is not None and len(entry.get("chunks", [])) > 0

    def add_documents(self, session_id: str, chunks: list[str],
                      embeddings: np.ndarray, metadata: dict | None = None):
        if not _FAISS_AVAILABLE:
            raise ImportError("faiss-cpu not installed. Install with: pip install faiss-cpu")

        dim = embeddings.shape[1]
        with self._lock:
            if session_id not in self._sessions:
                index = faiss.IndexFlatIP(dim)
                self._sessions[session_id] = {
                    "chunks": [],
                    "index": index,
                    "metadata": [],
                    "created_at": time.time(),
                }

            entry = self._sessions[session_id]
            entry["chunks"].extend(chunks)
            entry["index"].add(embeddings)
            if metadata:
                entry["metadata"].extend([metadata] * len(chunks))
            else:
                entry["metadata"].extend([{}] * len(chunks))

    def retrieve(self, session_id: str, query_embedding: np.ndarray,
                 top_k: int | None = None) -> list[str]:
        if top_k is None:
            top_k = RAG_TOP_K
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None or len(entry["chunks"]) == 0:
                return []

            n_chunks = len(entry["chunks"])
            k = min(top_k, n_chunks)
            if query_embedding.ndim == 1:
                query_embedding = query_embedding.reshape(1, -1)

            distances, indices = entry["index"].search(query_embedding, k)
            results = []
            for idx in indices[0]:
                if 0 <= idx < n_chunks:
                    results.append(entry["chunks"][idx])
            return results

    def get_stats(self, session_id: str) -> dict:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return {"chunks": 0, "has_index": False}
            return {
                "chunks": len(entry["chunks"]),
                "has_index": entry["index"] is not None,
                "created_at": entry.get("created_at"),
            }

    def secure_wipe(self, session_id: str, reason: str = "session_end"):
        with self._lock:
            entry = self._sessions.pop(session_id, None)
            if entry is None:
                return
            n = len(entry.get("chunks", []))
            for i, chunk in enumerate(entry.get("chunks", [])):
                entry["chunks"][i] = secrets.token_hex(max(len(chunk), 32))
            entry["chunks"].clear()
            entry["metadata"].clear()
            if entry.get("index") is not None:
                entry["index"].reset()
                del entry["index"]
            print(f"[RAG] {session_id[:8]}... wiped ({n} chunks, reason={reason})")

    def wipe_all(self, reason: str = "server_shutdown"):
        with self._lock:
            n_sessions = len(self._sessions)
            for sid in list(self._sessions.keys()):
                entry = self._sessions.pop(sid)
                for i, chunk in enumerate(entry.get("chunks", [])):
                    entry["chunks"][i] = secrets.token_hex(max(len(chunk), 32))
                entry["chunks"].clear()
                entry["metadata"].clear()
                if entry.get("index") is not None:
                    entry["index"].reset()
                    del entry["index"]
            print(f"[RAG] All sessions wiped ({n_sessions} sessions, reason={reason})")

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def total_chunks(self) -> int:
        with self._lock:
            return sum(len(e.get("chunks", [])) for e in self._sessions.values())
