from __future__ import annotations

import sys
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from products._shared.ai_engine import AIEngine

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

ai = AIEngine(
    default_system=(
        "You are CodeForge AI, an expert software architect and code reviewer. "
        "Provide precise, actionable code analysis with specific line references, "
        "security implications, performance considerations, and refactoring suggestions. "
        "Use proper technical terminology for the detected language."
    )
)


def _get_search_engine() -> SemanticSearch:
    global _search_engine
    if indexer.faiss_index is None:
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


class AIReviewRequest(BaseModel):
    diff: str
    focus: str = ""


class AIRefactorRequest(BaseModel):
    code: str
    language: str = "python"
    goal: str = ""


class AIExplainRequest(BaseModel):
    code: str
    language: str = ""
    detail_level: str = "detailed"


class AIGenerateDocsRequest(BaseModel):
    code: str
    language: str = "python"
    style: str = "google"


class AIChatRequest(BaseModel):
    question: str
    code_context: str = ""
    language: str = ""


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


# ---- AI-Powered Endpoints ----


@app.post("/v1/ai/review")
async def ai_review(req: AIReviewRequest):
    if not req.diff.strip():
        raise HTTPException(status_code=400, detail="Diff text is empty")

    focus_clause = f"\nFocus specifically on: {req.focus}" if req.focus else ""
    prompt = (
        f"Perform a deep code review of the following diff. Identify:\n"
        f"1. Security vulnerabilities (injection, auth issues, data exposure)\n"
        f"2. Performance problems (N+1 queries, unnecessary allocations, blocking calls)\n"
        f"3. Logic errors and edge cases\n"
        f"4. Code style and maintainability issues\n"
        f"5. Testing gaps\n"
        f"{focus_clause}\n\n"
        f"For each finding, provide: severity (critical/warning/info), category, "
        f"file and line reference, description, and a concrete fix.\n\n"
        f"Respond in JSON format with a top-level key \"findings\" containing an array of objects, "
        f"each with keys: severity, category, location, description, suggestion.\n"
        f"Also include a \"summary\" key with a brief overall assessment.\n\n"
        f"```diff\n{req.diff}\n```"
    )

    resp = await ai.complete(prompt, temperature=0.3)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "ai_review": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/refactor")
async def ai_refactor(req: AIRefactorRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code snippet is empty")

    goal_clause = f"\nRefactoring goal: {req.goal}" if req.goal else ""
    prompt = (
        f"Analyze the following {req.language} code and provide refactoring suggestions.\n"
        f"{goal_clause}\n\n"
        f"For each suggestion provide:\n"
        f"1. What to change and why\n"
        f"2. The refactored code snippet\n"
        f"3. Impact on readability, performance, and maintainability\n\n"
        f"```{req.language}\n{req.code}\n```"
    )

    resp = await ai.complete(prompt, temperature=0.4)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "refactoring": resp.text,
        "language": req.language,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/explain")
async def ai_explain(req: AIExplainRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code snippet is empty")

    lang_hint = f" ({req.language})" if req.language else ""
    prompt = (
        f"Explain the following code{lang_hint} at a {req.detail_level} level.\n\n"
        f"Cover:\n"
        f"- What the code does (high-level purpose)\n"
        f"- How it works (step-by-step logic)\n"
        f"- Key patterns and design decisions used\n"
        f"- Any potential issues or edge cases\n"
        f"- Dependencies and side effects\n\n"
        f"```{req.language}\n{req.code}\n```"
    )

    resp = await ai.complete(prompt, temperature=0.5)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "explanation": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/generate-docs")
async def ai_generate_docs(req: AIGenerateDocsRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code is empty")

    prompt = (
        f"Generate comprehensive documentation for the following {req.language} code "
        f"using {req.style} docstring style.\n\n"
        f"For each function/class/method, generate:\n"
        f"- A clear summary line\n"
        f"- Parameter descriptions with types\n"
        f"- Return value description\n"
        f"- Usage examples where helpful\n"
        f"- Any raised exceptions\n\n"
        f"Return the fully documented version of the code.\n\n"
        f"```{req.language}\n{req.code}\n```"
    )

    resp = await ai.complete(prompt, temperature=0.3)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "documented_code": resp.text,
        "style": req.style,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/chat")
async def ai_chat(req: AIChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question is empty")

    context_block = ""
    if req.code_context.strip():
        lang = req.language or "text"
        context_block = f"\n\nCode context:\n```{lang}\n{req.code_context}\n```"

    prompt = f"{req.question}{context_block}"

    resp = await ai.complete(prompt, temperature=0.6)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "answer": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }
