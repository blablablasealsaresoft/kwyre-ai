from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from .indexer import CodeChunk


@dataclass
class SearchResult:
    file_path: str
    language: str
    name: str
    kind: str
    start_line: int
    end_line: int
    score: float
    preview: str

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "language": self.language,
            "name": self.name,
            "kind": self.kind,
            "lines": [self.start_line, self.end_line],
            "score": round(self.score, 4),
            "preview": self.preview,
        }


class SemanticSearch:
    def __init__(
        self,
        model: SentenceTransformer,
        index: faiss.IndexFlatIP,
        chunks: list[CodeChunk],
    ):
        self._model = model
        self._index = index
        self._chunks = chunks

    @property
    def total_chunks(self) -> int:
        return len(self._chunks)

    def search(self, query: str, k: int = 10) -> list[SearchResult]:
        if not self._chunks or self._index is None or self._index.ntotal == 0:
            return []

        k = min(k, self._index.ntotal)
        query_vec = self._model.encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype=np.float32)
        scores, indices = self._index.search(query_vec, k)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            preview_lines = chunk.content.splitlines()[:15]
            results.append(SearchResult(
                file_path=chunk.file_path,
                language=chunk.language,
                name=chunk.name,
                kind=chunk.kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=float(score),
                preview="\n".join(preview_lines),
            ))
        return results

    def search_by_name(self, name: str) -> list[SearchResult]:
        """Exact-match search by function/class name (no embeddings needed)."""
        results: list[SearchResult] = []
        query_lower = name.lower()
        for chunk in self._chunks:
            if query_lower in chunk.name.lower():
                preview_lines = chunk.content.splitlines()[:15]
                results.append(SearchResult(
                    file_path=chunk.file_path,
                    language=chunk.language,
                    name=chunk.name,
                    kind=chunk.kind,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=1.0 if chunk.name.lower() == query_lower else 0.8,
                    preview="\n".join(preview_lines),
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results
