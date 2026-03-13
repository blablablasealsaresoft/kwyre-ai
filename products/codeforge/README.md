# CodeForge

**AI That Understands Your Codebase**

*By Mint Rail LLC*

CodeForge indexes your repository into a semantic vector store, then gives you instant code search, automated review, refactoring hints, test stubs, and documentation generation — all running locally on your machine.

---

## Features

### Repo Indexing
Walks your repository (respecting `.gitignore`), extracts function and class signatures via AST-like parsing, generates embeddings with `sentence-transformers`, and stores everything in a FAISS vector index. Incremental re-indexing on file changes.

### Semantic Code Search
Query your codebase in natural language. "Where do we handle authentication?" returns ranked code chunks with file paths, line numbers, and similarity scores.

### Automated Code Review
Pass a diff and get back actionable issues:
- **Hardcoded secrets** — API keys, passwords, tokens in string literals
- **SQL injection** — raw string interpolation in queries
- **Unused imports** — dead imports in Python files
- **Complexity** — functions with nesting depth > 4
- **Missing error handling** — bare `except`, empty `catch` blocks
- **TODO/FIXME tracking** — counts and locations
- **File size warnings** — files exceeding 500 lines

### Refactoring Suggestions
Identifies long functions, duplicated blocks, and deeply nested logic, then suggests extraction targets.

### Test Generation Stubs
Given a function signature, generates a test skeleton with setup, assertion placeholders, and edge-case comments.

### Documentation Generation
Generates docstrings and module-level documentation from function signatures and body analysis.

---

## Supported Languages

| Language   | Indexing | Review | Search |
|------------|----------|--------|--------|
| Python     | Yes      | Yes    | Yes    |
| TypeScript | Yes      | Yes    | Yes    |
| JavaScript | Yes      | Yes    | Yes    |
| Go         | Yes      | Yes    | Yes    |
| Rust       | Yes      | Partial| Yes    |
| Java       | Yes      | Partial| Yes    |
| Ruby       | Yes      | Partial| Yes    |

---

## Privacy

**Your code never leaves your machine.** CodeForge runs entirely locally — embeddings are generated on-device, the FAISS index lives on disk, and no data is sent to external services.

---

## Quickstart

### Prerequisites
- Python 3.10+
- 4 GB RAM minimum (8 GB recommended for large repos)

### Install

```bash
cd products/codeforge
pip install -r requirements.txt
```

### Run the server

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

### Index a repository

```bash
curl -X POST http://localhost:8000/v1/index/repo \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/your/repo"}'
```

### Search your code

```bash
curl -X POST http://localhost:8000/v1/search/code \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication middleware", "k": 5}'
```

### Review a diff

```bash
curl -X POST http://localhost:8000/v1/review/diff \
  -H "Content-Type: application/json" \
  -d '{"diff": "$(git diff HEAD~1)"}'
```

---

## API Reference

### `GET /health`
Returns server status and index statistics.

```json
{
  "status": "ok",
  "indexed_files": 342,
  "total_chunks": 1847,
  "index_size_mb": 12.4
}
```

### `POST /v1/index/repo`
Index a repository for search and analysis.

**Request:**
```json
{
  "path": "/absolute/path/to/repo",
  "extensions": [".py", ".ts", ".go"],
  "exclude_dirs": ["node_modules", "venv", ".git"]
}
```

**Response:**
```json
{
  "status": "indexed",
  "files_processed": 142,
  "chunks_created": 876,
  "duration_seconds": 23.4
}
```

### `POST /v1/search/code`
Semantic search across indexed code.

**Request:**
```json
{
  "query": "database connection pooling",
  "k": 10
}
```

**Response:**
```json
{
  "results": [
    {
      "file": "src/db/pool.py",
      "lines": [12, 45],
      "score": 0.92,
      "preview": "class ConnectionPool:\n    def __init__(self, max_size=10)..."
    }
  ]
}
```

### `POST /v1/review/diff`
Analyze a diff for issues.

**Request:**
```json
{
  "diff": "diff --git a/app.py..."
}
```

**Response:**
```json
{
  "issues": [
    {
      "severity": "high",
      "category": "security",
      "message": "Possible hardcoded API key detected",
      "line": 42,
      "suggestion": "Move to environment variable"
    }
  ],
  "summary": {
    "high": 1,
    "medium": 3,
    "low": 2
  }
}
```

### `POST /v1/architecture/analyze`
Analyze repository structure and dependencies.

**Request:**
```json
{
  "path": "/absolute/path/to/repo"
}
```

### `POST /v1/docs/generate`
Generate documentation for a file.

**Request:**
```json
{
  "file_path": "/absolute/path/to/file.py"
}
```

---

## Architecture

```
products/codeforge/
  server/
    app.py          # FastAPI application and route handlers
    indexer.py       # Repository indexing, AST extraction, FAISS storage
    reviewer.py      # Code review engine with pattern-based checks
    search.py        # Semantic search over FAISS index
  site/
    index.html       # Landing page
  requirements.txt   # Python dependencies
  wrangler.toml      # Cloudflare Pages deployment config
  README.md
```

---

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEFORGE_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model name |
| `CODEFORGE_INDEX_DIR` | `.codeforge/` | Where FAISS indexes are stored |
| `CODEFORGE_MAX_FILE_SIZE` | `1048576` | Max file size in bytes to index (1 MB) |
| `CODEFORGE_HOST` | `0.0.0.0` | Server bind address |
| `CODEFORGE_PORT` | `8000` | Server port |

---

## License

Proprietary — Mint Rail LLC. All rights reserved.
