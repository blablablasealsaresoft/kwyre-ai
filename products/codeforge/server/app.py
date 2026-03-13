from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .indexer import LANG_EXTENSIONS, RepoIndexer
from .reviewer import CodeReviewer
from .search import SemanticSearch

app = FastAPI(
    title="CodeForge",
    description="AI That Understands Your Codebase — by Mint Rail LLC",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

indexer = RepoIndexer()
reviewer = CodeReviewer()
_search_engine: Optional[SemanticSearch] = None


def _get_search_engine() -> SemanticSearch:
    global _search_engine
    if _search_engine is None or indexer.faiss_index is None:
        raise HTTPException(
            status_code=400,
            detail="No repository indexed yet. Call /v1/index/repo first.",
        )
    if _search_engine is None:
        _search_engine = SemanticSearch(indexer.model, indexer.faiss_index, indexer.chunks)
    return _search_engine


# ---- Request / Response models ----

class IndexRequest(BaseModel):
    path: str
    extensions: Optional[list[str]] = None
    exclude_dirs: Optional[list[str]] = None


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=10, ge=1, le=100)


class ReviewRequest(BaseModel):
    diff: str


class ArchitectureRequest(BaseModel):
    path: str


class DocsRequest(BaseModel):
    file_path: str


# ---- Endpoints ----

@app.get("/health")
async def health():
    stats = indexer.get_stats()
    return {
        "status": "ok",
        "indexed_files": stats.get("files_processed", 0),
        "total_chunks": stats.get("chunks_created", 0),
        "index_size_mb": stats.get("index_size_mb", 0),
    }


@app.post("/v1/index/repo")
async def index_repo(req: IndexRequest):
    repo_path = Path(req.path).resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {req.path}")

    global _search_engine
    try:
        stats = indexer.index_repo(
            str(repo_path),
            extensions=req.extensions,
            exclude_dirs=req.exclude_dirs,
        )
        _search_engine = SemanticSearch(indexer.model, indexer.faiss_index, indexer.chunks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "indexed",
        "files_processed": stats.files_processed,
        "chunks_created": stats.chunks_created,
        "languages": stats.languages,
        "duration_seconds": round(stats.duration_seconds, 2),
    }


@app.post("/v1/search/code")
async def search_code(req: SearchRequest):
    engine = _get_search_engine()
    results = engine.search(req.query, k=req.k)
    return {
        "query": req.query,
        "total_results": len(results),
        "results": [r.to_dict() for r in results],
    }


@app.post("/v1/review/diff")
async def review_diff(req: ReviewRequest):
    if not req.diff.strip():
        raise HTTPException(status_code=400, detail="Diff text is empty")
    return reviewer.analyze_diff(req.diff)


@app.post("/v1/architecture/analyze")
async def analyze_architecture(req: ArchitectureRequest):
    repo_path = Path(req.path).resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {req.path}")

    structure: dict = {"directories": {}, "file_counts": {}, "total_files": 0, "languages": {}}

    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
        ]
        rel_dir = str(Path(dirpath).relative_to(repo_path))
        if rel_dir == ".":
            rel_dir = "/"

        file_list: list[str] = []
        for f in filenames:
            ext = Path(f).suffix
            lang = LANG_EXTENSIONS.get(ext, "other")
            structure["languages"][lang] = structure["languages"].get(lang, 0) + 1
            structure["file_counts"][ext] = structure["file_counts"].get(ext, 0) + 1
            structure["total_files"] += 1
            file_list.append(f)

        if file_list:
            structure["directories"][rel_dir] = {
                "file_count": len(file_list),
                "files": file_list[:50],  # cap listing
            }

    top_dirs = sorted(
        structure["directories"].items(),
        key=lambda x: x[1]["file_count"],
        reverse=True,
    )[:20]

    return {
        "repo": str(repo_path),
        "total_files": structure["total_files"],
        "languages": structure["languages"],
        "extension_counts": structure["file_counts"],
        "top_directories": {k: v for k, v in top_dirs},
    }


@app.post("/v1/docs/generate")
async def generate_docs(req: DocsRequest):
    fpath = Path(req.file_path).resolve()
    if not fpath.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")

    try:
        source = fpath.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    lang = LANG_EXTENSIONS.get(fpath.suffix, "unknown")
    lines = source.splitlines()
    doc_entries: list[dict] = []

    # Extract signatures and generate doc stubs
    from .indexer import EXTRACTION_PATTERNS
    patterns = EXTRACTION_PATTERNS.get(lang, [])

    for pat in patterns:
        for m in pat.finditer(source):
            line_no = source[:m.start()].count("\n")
            kind = m.group("kind") if "kind" in pat.groupindex else "symbol"
            name = m.group("name") if "name" in pat.groupindex else "unknown"
            sig_line = lines[line_no].strip() if line_no < len(lines) else ""

            # Grab the body (up to next match or 30 lines)
            body_end = min(line_no + 30, len(lines))
            body = "\n".join(lines[line_no:body_end])

            params = re.findall(r"(\w+)\s*[:,]", sig_line)
            param_docs = "\n".join(f"    {p}: Description needed." for p in params if p not in {kind, name})

            docstring = f'"""{name}: TODO — describe purpose.\n\n'
            if param_docs:
                docstring += f"Args:\n{param_docs}\n\n"
            docstring += 'Returns:\n    TODO — describe return value.\n"""'

            doc_entries.append({
                "name": name,
                "kind": kind,
                "line": line_no + 1,
                "signature": sig_line,
                "generated_doc": docstring,
            })

    return {
        "file": str(fpath),
        "language": lang,
        "entries": doc_entries,
        "total": len(doc_entries),
    }
