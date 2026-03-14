#!/usr/bin/env python3
"""Generate manifest JSON with SHA256 hashes from adapter directories."""
import argparse
import hashlib
import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path


def zip_and_hash(adapter_dir: Path) -> str:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in adapter_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(adapter_dir))
    buf.seek(0)
    return hashlib.sha256(buf.read()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter-dir", default=os.path.expanduser("~/.kwyre/adapters"))
    p.add_argument("--manifest", help="Existing manifest JSON to update")
    args = p.parse_args()

    base = Path(args.adapter_dir)
    manifest = {}
    if args.manifest:
        with open(args.manifest) as f:
            manifest = json.load(f)

    for d in sorted(base.iterdir()) if base.exists() else []:
        if not d.is_dir() or d.name.startswith("."):
            continue
        domain = d.name.replace("-", "_")
        try:
            h = zip_and_hash(d)
        except Exception as e:
            print(f"# skip {d.name}: {e}", file=sys.stderr)
            continue
        if domain not in manifest:
            manifest[domain] = {}
        manifest[domain]["sha256"] = h
        slug = domain.replace("_", "-")
        url = f"https://cdn.kwyre.com/adapters/{slug}-4b-v1.0.0.zip"
        manifest[domain]["url"] = url

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
