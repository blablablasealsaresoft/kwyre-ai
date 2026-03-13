"""Literature engine: semantic search and synthesis over scientific documents."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass
class DocumentMeta:
    doc_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    source: str = ""
    extra: dict = field(default_factory=dict)


class EmbeddingIndex:
    """FAISS-backed semantic index with sentence-transformer embeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(self.dim)
        self._texts: list[str] = []
        self._metadata: list[DocumentMeta] = []

    @property
    def size(self) -> int:
        return self.index.ntotal

    def _make_id(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add_documents(
        self,
        texts: list[str],
        metadata: list[dict] | None = None,
    ) -> list[str]:
        """Embed and index a batch of documents. Returns assigned doc IDs."""
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        vectors = np.array(embeddings, dtype=np.float32)
        self.index.add(vectors)

        ids = []
        for i, text in enumerate(texts):
            doc_id = self._make_id(text)
            meta = metadata[i] if metadata else {}
            doc_meta = DocumentMeta(
                doc_id=doc_id,
                title=meta.get("title", f"Document {self.size - len(texts) + i + 1}"),
                authors=meta.get("authors", []),
                year=meta.get("year"),
                abstract=meta.get("abstract", text[:500]),
                source=meta.get("source", ""),
                extra=meta.get("extra", {}),
            )
            self._texts.append(text)
            self._metadata.append(doc_meta)
            ids.append(doc_id)

        return ids

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return the top-k most similar documents to the query."""
        if self.size == 0:
            return []

        k = min(k, self.size)
        q_vec = self.model.encode([query], normalize_embeddings=True)
        q_vec = np.array(q_vec, dtype=np.float32)

        scores, indices = self.index.search(q_vec, k)

        results = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx == -1:
                continue
            meta = self._metadata[idx]
            results.append({
                "rank": rank + 1,
                "score": float(score),
                "doc_id": meta.doc_id,
                "title": meta.title,
                "authors": meta.authors,
                "year": meta.year,
                "abstract": meta.abstract,
                "source": meta.source,
                "snippet": self._texts[idx][:300],
            })

        return results

    def get_document(self, doc_id: str) -> dict | None:
        for i, meta in enumerate(self._metadata):
            if meta.doc_id == doc_id:
                return {
                    "doc_id": meta.doc_id,
                    "title": meta.title,
                    "authors": meta.authors,
                    "year": meta.year,
                    "abstract": meta.abstract,
                    "source": meta.source,
                    "text": self._texts[i],
                }
        return None

    def synthesize(self, doc_ids: list[str]) -> dict:
        """Combine multiple documents into a structured synthesis."""
        docs = []
        for did in doc_ids:
            doc = self.get_document(did)
            if doc:
                docs.append(doc)

        if not docs:
            return {"error": "No matching documents found", "documents": []}

        all_text = " ".join(d["text"] for d in docs)
        sentences = [s.strip() for s in all_text.split(".") if len(s.strip()) > 20]

        themes = _extract_themes(sentences)
        consensus = _find_consensus(docs)
        gaps = _identify_gaps(docs)

        return {
            "document_count": len(docs),
            "documents": [
                {"doc_id": d["doc_id"], "title": d["title"], "authors": d["authors"]}
                for d in docs
            ],
            "themes": themes,
            "consensus_points": consensus,
            "research_gaps": gaps,
            "date_range": _date_range(docs),
            "generated_at": time.time(),
        }


def _extract_themes(sentences: list[str], max_themes: int = 5) -> list[dict]:
    """Cluster sentences into broad themes using keyword frequency."""
    from collections import Counter

    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must", "and", "or",
        "but", "if", "of", "in", "to", "for", "with", "on", "at", "by", "from",
        "not", "no", "this", "that", "it", "its", "as", "we", "our", "their",
        "which", "what", "when", "where", "who", "how", "than", "more", "also",
    }
    word_freq: Counter = Counter()
    for sent in sentences:
        words = [w.lower().strip(".,;:!?()[]") for w in sent.split()]
        words = [w for w in words if len(w) > 3 and w not in stopwords]
        word_freq.update(words)

    top_words = [w for w, _ in word_freq.most_common(max_themes * 3)]
    themes = []
    used = set()
    for word in top_words:
        if word in used or len(themes) >= max_themes:
            break
        related = [s for s in sentences if word in s.lower()]
        if related:
            themes.append({
                "keyword": word,
                "frequency": word_freq[word],
                "representative_sentence": related[0],
                "mention_count": len(related),
            })
            used.add(word)

    return themes


def _find_consensus(docs: list[dict]) -> list[str]:
    """Identify points that appear across multiple documents."""
    if len(docs) < 2:
        return ["Insufficient documents for consensus analysis (need >= 2)."]

    from collections import Counter

    phrase_counter: Counter = Counter()
    for doc in docs:
        seen = set()
        words = doc["text"].lower().split()
        for i in range(len(words) - 2):
            trigram = " ".join(words[i : i + 3])
            if trigram not in seen:
                phrase_counter[trigram] += 1
                seen.add(trigram)

    shared = [phrase for phrase, count in phrase_counter.most_common(50) if count >= 2]
    if not shared:
        return ["No strong consensus points detected across the corpus."]

    return [f"Shared concept: '{p}' (appears in multiple documents)" for p in shared[:5]]


def _identify_gaps(docs: list[dict]) -> list[str]:
    """Heuristic gap analysis based on hedging language."""
    gap_markers = [
        "further research", "remains unclear", "not well understood",
        "future work", "limitations", "however", "insufficient data",
        "more studies", "open question", "warrants investigation",
    ]
    gaps = []
    for doc in docs:
        text_lower = doc["text"].lower()
        for marker in gap_markers:
            if marker in text_lower:
                idx = text_lower.index(marker)
                start = max(0, idx - 60)
                end = min(len(doc["text"]), idx + len(marker) + 100)
                snippet = doc["text"][start:end].strip()
                gaps.append(f"[{doc['title']}]: ...{snippet}...")
                break

    return gaps or ["No explicit research gaps detected in the provided documents."]


def _date_range(docs: list[dict]) -> dict:
    years = [d["year"] for d in docs if d.get("year")]
    if not years:
        return {"earliest": None, "latest": None}
    return {"earliest": min(years), "latest": max(years)}
