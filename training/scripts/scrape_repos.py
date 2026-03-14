#!/usr/bin/env python3
"""
KWYRE — GitHub Repo Scraper for Training Context Enrichment

Clones specified GitHub repositories and extracts README content,
API listings, and code documentation as supplementary context for
domain-specific training trace generation.

Output: ~/.kwyre/training-data/repo-context/*.json

Usage:
    python3 scrape_repos.py
"""

import json
import os
import shutil
import subprocess
import re
from pathlib import Path

KWYRE_HOME = os.path.expanduser("~/.kwyre")
CONTEXT_DIR = Path(KWYRE_HOME) / "training-data" / "repo-context"
CLONE_DIR = Path(KWYRE_HOME) / "training-data" / "repo-clones"
CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
CLONE_DIR.mkdir(parents=True, exist_ok=True)

REPOS = {
    "awesome-osint": {
        "url": "https://github.com/blablablasealsaresoft/Awesome-OSINT-For-Everything.git",
        "target_domain": "defense_intelligence",
        "extract": ["README.md", "**/*.md"],
        "description": "OSINT tools, techniques, and methodologies for intelligence gathering",
    },
    "public-apis": {
        "url": "https://github.com/blablablasealsaresoft/public-apis.git",
        "target_domain": "software_engineering",
        "extract": ["README.md", "**/*.md"],
        "description": "Public API directory with categories, auth types, and endpoints",
    },
    "face-recognition": {
        "url": "https://github.com/blablablasealsaresoft/face_recognition.git",
        "target_domain": "relationship_matching",
        "extract": ["README.md", "**/*.md", "**/*.py"],
        "description": "Face recognition library for profile matching and biometric analysis",
    },
}


def clone_repo(name: str, url: str) -> Path:
    """Clone or update a git repository."""
    repo_dir = CLONE_DIR / name
    if repo_dir.exists():
        print(f"  [{name}] Updating existing clone...")
        try:
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=repo_dir, capture_output=True, timeout=60
            )
        except Exception:
            pass
    else:
        print(f"  [{name}] Cloning {url}...")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(repo_dir)],
                capture_output=True, timeout=120, check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"  [{name}] Clone failed: {e.stderr.decode()[:200] if e.stderr else 'unknown error'}")
            return repo_dir
    return repo_dir


def extract_content(repo_dir: Path, patterns: list[str], max_file_size: int = 50_000) -> list[dict]:
    """Extract text content from files matching glob patterns."""
    files = []
    for pattern in patterns:
        for filepath in repo_dir.glob(pattern):
            if not filepath.is_file():
                continue
            if filepath.stat().st_size > max_file_size:
                continue
            if any(skip in str(filepath) for skip in [".git", "__pycache__", "node_modules", ".egg"]):
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                if len(content.strip()) < 50:
                    continue
                files.append({
                    "path": str(filepath.relative_to(repo_dir)),
                    "size": len(content),
                    "content": content[:20_000],
                })
            except Exception:
                continue
    return files


def build_context_summary(name: str, description: str, files: list[dict]) -> str:
    """Build a condensed context summary from extracted files."""
    summary_parts = [f"# {name}\n{description}\n"]

    for f in files[:20]:
        header = f"\n## {f['path']}\n"
        content = f["content"]
        content = re.sub(r"\n{3,}", "\n\n", content)
        if len(content) > 5000:
            content = content[:5000] + "\n... (truncated)"
        summary_parts.append(header + content)

    return "\n".join(summary_parts)


def main():
    print(f"\n{'='*60}")
    print("  KWYRE — GitHub Repo Scraper")
    print(f"  Repos: {len(REPOS)}")
    print(f"  Output: {CONTEXT_DIR}")
    print(f"{'='*60}\n")

    for name, config in REPOS.items():
        print(f"\n[{name}]")
        repo_dir = clone_repo(name, config["url"])

        if not repo_dir.exists():
            print(f"  [{name}] Skipping — clone directory not found")
            continue

        files = extract_content(repo_dir, config["extract"])
        print(f"  [{name}] Extracted {len(files)} files")

        summary = build_context_summary(name, config["description"], files)
        print(f"  [{name}] Context summary: {len(summary):,} chars")

        output = {
            "repo": name,
            "url": config["url"],
            "target_domain": config["target_domain"],
            "description": config["description"],
            "files_extracted": len(files),
            "context_summary": summary,
            "file_list": [{"path": f["path"], "size": f["size"]} for f in files],
        }

        out_path = CONTEXT_DIR / f"{name}.json"
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"  [{name}] Saved to {out_path}")

    print(f"\n{'='*60}")
    print("  SCRAPING COMPLETE")
    print(f"  Context files: {CONTEXT_DIR}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
