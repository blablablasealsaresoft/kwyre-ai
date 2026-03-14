#!/usr/bin/env python3
"""
Data preparation pipeline for Kwyre domain-specific fine-tuning.
Extracts text from documents, applies templates, outputs Alpaca/OpenHermes JSONL.
Uses only: json, pathlib, re, argparse, hashlib (no ML dependencies).
"""

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Add parent for templates
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finetune.templates import DOMAIN_TEMPLATES, Template, get_templates_for_domain  # noqa: E402


# ---------------------------------------------------------------------------
# TEXT EXTRACTION (stdlib only)
# ---------------------------------------------------------------------------

def extract_txt(path: Path) -> str:
    """Extract text from a .txt file."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def extract_docx(path: Path) -> str:
    """Extract text from .docx using zipfile + xml.etree (stdlib only)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()
        parts = []
        for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if t.text:
                parts.append(t.text)
            if t.tail:
                parts.append(t.tail)
        return " ".join(parts).replace("\n", " ").strip()
    except Exception:
        return ""


def extract_pdf(path: Path) -> str:
    """Extract text from PDF using pdftotext (poppler) if available. Returns empty if not."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=path.read_bytes(),
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


EXTRACTORS = {
    ".txt": extract_txt,
    ".docx": extract_docx,
    ".pdf": extract_pdf,
}


def extract_text(path: Path) -> str:
    """Extract text from a document. Returns empty string if unsupported or failed."""
    ext = path.suffix.lower()
    if ext not in EXTRACTORS:
        return ""
    return EXTRACTORS[ext](path)


# ---------------------------------------------------------------------------
# CHUNKING
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_chunk_chars: int = 4000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks. Preserve paragraph boundaries when possible."""
    text = text.strip()
    if not text or len(text) <= max_chunk_chars:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chunk_chars
        if end < len(text):
            # Try to break at paragraph or sentence
            break_at = text.rfind("\n\n", start, end + 1)
            if break_at == -1:
                break_at = text.rfind("\n", start, end + 1)
            if break_at == -1:
                break_at = text.rfind(". ", start, end + 1)
            if break_at != -1 and break_at > start:
                end = break_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if overlap > 0 else end
    return chunks


# ---------------------------------------------------------------------------
# PROMPT GENERATION
# ---------------------------------------------------------------------------

def apply_template(template: Template, content: str, domain: str) -> dict | None:
    """Apply a template to content. Returns OpenHermes-format dict or None if content empty."""
    content = content.strip()
    if not content or len(content) < 50:
        return None

    instruction = template.instruction_template.replace("{document}", content).replace("{content}", content)
    response = template.expected_format

    return {
        "conversations": [
            {"from": "human", "value": instruction},
            {"from": "gpt", "value": response},
        ],
        "domain": domain,
        "difficulty": template.difficulty,
    }


def content_hash(obj: dict) -> str:
    """Stable hash for deduplication."""
    key = json.dumps(obj.get("conversations", []), sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def collect_documents(input_dir: Path) -> list[tuple[Path, str]]:
    """Collect (path, domain) for all supported documents. Domain from parent folder name."""
    supported = {".txt", ".docx", ".pdf"}
    results = []
    for path in input_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in supported:
            # Infer domain from parent folder: legal/, financial/, forensic/
            rel = path.relative_to(input_dir)
            parts = rel.parts
            domain = "legal"  # default
            for d in ("legal", "financial", "forensic"):
                if d in parts:
                    domain = d
                    break
            results.append((path, domain))
    return results


def run_pipeline(
    input_dir: Path,
    output_path: Path,
    domains: list[str],
    max_chunk_chars: int = 4000,
    min_content_len: int = 100,
    dedupe: bool = True,
) -> int:
    """Run the full pipeline. Returns number of records written."""
    if domains:
        templates_by_domain = {d: get_templates_for_domain(d) for d in domains}
    else:
        templates_by_domain = {d: get_templates_for_domain(d) for d in DOMAIN_TEMPLATES}

    seen_hashes: set[str] = set()
    records: list[dict] = []
    docs = collect_documents(input_dir)

    if not docs:
        print("No supported documents found. Use .txt, .docx, or .pdf (pdftotext required for PDF).")
        return 0

    for path, inferred_domain in docs:
        if domains and inferred_domain not in domains:
            continue
        domain = inferred_domain if inferred_domain in templates_by_domain else "legal"
        templates = templates_by_domain.get(domain, templates_by_domain.get("legal", []))

        text = extract_text(path)
        if not text or len(text) < min_content_len:
            continue

        chunks = chunk_text(text, max_chunk_chars=max_chunk_chars)
        for chunk in chunks:
            for template in templates:
                rec = apply_template(template, chunk, domain)
                if rec is None:
                    continue
                if dedupe:
                    h = content_hash(rec)
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                records.append(rec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return len(records)


def main():
    ap = argparse.ArgumentParser(description="Prepare fine-tuning data from raw documents")
    ap.add_argument("input_dir", type=Path, help="Directory containing PDF, TXT, DOCX files")
    ap.add_argument("-o", "--output", type=Path, default=Path("finetune_data.jsonl"), help="Output JSONL path")
    ap.add_argument("--domains", nargs="+", choices=["legal", "financial", "forensic"], default=[],
                    help="Restrict to these domains (default: all)")
    ap.add_argument("--max-chunk", type=int, default=4000, help="Max characters per chunk")
    ap.add_argument("--min-content", type=int, default=100, help="Min content length to process")
    ap.add_argument("--no-dedupe", action="store_true", help="Disable deduplication")
    args = ap.parse_args()

    if not args.input_dir.is_dir():
        print(f"Error: {args.input_dir} is not a directory")
        sys.exit(1)

    n = run_pipeline(
        args.input_dir,
        args.output,
        domains=args.domains,
        max_chunk_chars=args.max_chunk,
        min_content_len=args.min_content,
        dedupe=not args.no_dedupe,
    )
    print(f"Wrote {n} records to {args.output}")


if __name__ == "__main__":
    main()
