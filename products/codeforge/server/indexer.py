from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = os.getenv("CODEFORGE_MODEL", "all-MiniLM-L6-v2")
INDEX_DIR = os.getenv("CODEFORGE_INDEX_DIR", ".codeforge")
MAX_FILE_SIZE = int(os.getenv("CODEFORGE_MAX_FILE_SIZE", 1_048_576))

LANG_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "target", "vendor", ".codeforge",
}

# ---------------------------------------------------------------------------
# Regex patterns for extracting function/class signatures per language
# ---------------------------------------------------------------------------

EXTRACTION_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?P<kind>class|def|async\s+def)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
    ],
    "typescript": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?:export\s+)?(?P<kind>function|class|interface|type|const)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
        re.compile(
            r"^(?P<indent>[ \t]*)(?:export\s+)?(?:async\s+)?(?P<kind>function)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
    ],
    "javascript": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?:export\s+)?(?P<kind>function|class|const)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
    ],
    "go": [
        re.compile(
            r"^(?P<kind>func)\s+(?:\(.*?\)\s+)?(?P<name>\w+)",
            re.MULTILINE,
        ),
        re.compile(
            r"^(?P<kind>type)\s+(?P<name>\w+)\s+struct",
            re.MULTILINE,
        ),
    ],
    "rust": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?:pub\s+)?(?P<kind>fn|struct|enum|trait|impl)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
    ],
    "java": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?:public|private|protected)?\s*(?:static\s+)?(?P<kind>class|interface|enum)\s+(?P<name>\w+)",
            re.MULTILINE,
        ),
        re.compile(
            r"^(?P<indent>[ \t]*)(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\]]+\s+(?P<name>\w+)\s*\(",
            re.MULTILINE,
        ),
    ],
    "ruby": [
        re.compile(
            r"^(?P<indent>[ \t]*)(?P<kind>class|module|def)\s+(?P<name>[\w:.]+)",
            re.MULTILINE,
        ),
    ],
}


@dataclass
class CodeChunk:
    file_path: str
    language: str
    name: str
    kind: str  # function, class, method, etc.
    start_line: int
    end_line: int
    content: str
    signature: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "name": self.name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "signature": self.signature,
        }


@dataclass
class IndexStats:
    files_processed: int = 0
    chunks_created: int = 0
    total_lines: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    index_size_bytes: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "files_processed": self.files_processed,
            "chunks_created": self.chunks_created,
            "total_lines": self.total_lines,
            "languages": self.languages,
            "index_size_mb": round(self.index_size_bytes / (1024 * 1024), 2),
            "duration_seconds": round(self.duration_seconds, 2),
        }


def _load_gitignore_patterns(repo_root: Path) -> list[str]:
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[str] = []
    for line in gitignore.read_text(errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(path: Path, repo_root: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(repo_root)).replace("\\", "/")
    for pat in patterns:
        clean = pat.rstrip("/")
        if clean in rel or rel.startswith(clean + "/"):
            return True
    return False


class RepoIndexer:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._index: Optional[faiss.IndexFlatIP] = None
        self._chunks: list[CodeChunk] = []
        self._stats = IndexStats()
        self._index_dir = Path(INDEX_DIR)

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def _ensure_index(self) -> faiss.IndexFlatIP:
        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dimension)
        return self._index

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _collect_files(
        self,
        root: Path,
        extensions: Optional[list[str]] = None,
        exclude_dirs: Optional[set[str]] = None,
    ) -> list[Path]:
        allowed_ext = set(extensions) if extensions else set(LANG_EXTENSIONS.keys())
        skip_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS
        gitignore_patterns = _load_gitignore_patterns(root)
        files: list[Path] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in skip_dirs and not _is_ignored(Path(dirpath) / d, root, gitignore_patterns)
            ]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix in allowed_ext and fpath.stat().st_size <= MAX_FILE_SIZE:
                    if not _is_ignored(fpath, root, gitignore_patterns):
                        files.append(fpath)
        return files

    # ------------------------------------------------------------------
    # Chunking — extract functions/classes as chunks
    # ------------------------------------------------------------------

    def _extract_chunks(self, file_path: Path, root: Path) -> list[CodeChunk]:
        lang = LANG_EXTENSIONS.get(file_path.suffix)
        if not lang:
            return []

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        lines = source.splitlines(keepends=True)
        patterns = EXTRACTION_PATTERNS.get(lang, [])
        boundaries: list[tuple[int, str, str]] = []  # (line_number, kind, name)

        for pat in patterns:
            for m in pat.finditer(source):
                line_no = source[:m.start()].count("\n")
                kind = m.group("kind") if "kind" in pat.groupindex else "unknown"
                name = m.group("name") if "name" in pat.groupindex else "unknown"
                boundaries.append((line_no, kind, name))

        boundaries.sort(key=lambda b: b[0])

        if not boundaries:
            # Whole file as one chunk
            rel = str(file_path.relative_to(root))
            return [CodeChunk(
                file_path=rel,
                language=lang,
                name=file_path.stem,
                kind="module",
                start_line=1,
                end_line=len(lines),
                content=source[:4000],
                signature=f"module {file_path.name}",
            )]

        chunks: list[CodeChunk] = []
        rel = str(file_path.relative_to(root))

        for i, (line_no, kind, name) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(lines)
            content = "".join(lines[line_no:end]).rstrip()
            sig_line = lines[line_no].strip() if line_no < len(lines) else ""

            chunks.append(CodeChunk(
                file_path=rel,
                language=lang,
                name=name,
                kind=kind,
                start_line=line_no + 1,
                end_line=end,
                content=content[:4000],
                signature=sig_line,
            ))

        return chunks

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_repo(
        self,
        path: str,
        extensions: Optional[list[str]] = None,
        exclude_dirs: Optional[list[str]] = None,
    ) -> IndexStats:
        start = time.time()
        root = Path(path).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Repository path not found: {root}")

        skip = DEFAULT_EXCLUDE_DIRS | set(exclude_dirs or [])
        files = self._collect_files(root, extensions, skip)

        self._chunks = []
        lang_counts: dict[str, int] = {}
        total_lines = 0

        for fpath in files:
            file_chunks = self._extract_chunks(fpath, root)
            self._chunks.extend(file_chunks)
            lang = LANG_EXTENSIONS.get(fpath.suffix, "unknown")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            try:
                total_lines += sum(1 for _ in open(fpath, errors="replace"))
            except OSError:
                pass

        if self._chunks:
            texts = [
                f"{c.language} {c.kind} {c.name}\n{c.signature}\n{c.content[:1000]}"
                for c in self._chunks
            ]
            embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            embeddings = np.array(embeddings, dtype=np.float32)

            self._index = faiss.IndexFlatIP(embeddings.shape[1])
            self._index.add(embeddings)

            self._save_index(root)

        elapsed = time.time() - start
        self._stats = IndexStats(
            files_processed=len(files),
            chunks_created=len(self._chunks),
            total_lines=total_lines,
            languages=lang_counts,
            index_size_bytes=self._get_index_size(root),
            duration_seconds=elapsed,
        )
        return self._stats

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _index_path(self, repo_root: Path) -> Path:
        repo_hash = hashlib.sha256(str(repo_root).encode()).hexdigest()[:16]
        out = self._index_dir / repo_hash
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _save_index(self, repo_root: Path) -> None:
        out = self._index_path(repo_root)
        if self._index is not None:
            faiss.write_index(self._index, str(out / "index.faiss"))
        meta = [c.to_dict() for c in self._chunks]
        (out / "chunks.json").write_text(json.dumps(meta, indent=2))

    def load_index(self, repo_root: Path) -> bool:
        idx_dir = self._index_path(repo_root)
        faiss_path = idx_dir / "index.faiss"
        meta_path = idx_dir / "chunks.json"
        if not faiss_path.exists() or not meta_path.exists():
            return False
        self._index = faiss.read_index(str(faiss_path))
        raw = json.loads(meta_path.read_text())
        self._chunks = [
            CodeChunk(**{k: v for k, v in item.items() if k in CodeChunk.__dataclass_fields__})
            for item in raw
        ]
        return True

    def _get_index_size(self, repo_root: Path) -> int:
        idx_dir = self._index_path(repo_root)
        total = 0
        if idx_dir.exists():
            for f in idx_dir.iterdir():
                total += f.stat().st_size
        return total

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        return self._stats.to_dict()

    @property
    def chunks(self) -> list[CodeChunk]:
        return self._chunks

    @property
    def faiss_index(self) -> Optional[faiss.IndexFlatIP]:
        return self._index
