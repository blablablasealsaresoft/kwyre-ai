#!/usr/bin/env python3
"""
Kwyre Release Code Signing
===========================
Ed25519-signed release manifests for tamper-proof distribution.

Generates a SHA256 manifest of all build artifacts, signs it with the same
Ed25519 private key used for license signing, and verifies releases offline.

Usage:
  # Sign a build directory
  python codesign.py sign --dir build/kwyre-dist --version 1.0.0 --platform windows

  # Verify a signed release
  python codesign.py verify --manifest build/kwyre-dist/MANIFEST.sig.json

  # SHA256 hash a single file
  python codesign.py hash --file path/to/file
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key, load_der_public_key
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

KEYS_DIR = Path(__file__).parent / ".keys"

EMBEDDED_PUBLIC_KEY = ""  # Set after running: python license.py keygen

SKIP_PATTERNS = [
    "MANIFEST.json",
    "MANIFEST.sig",
    "MANIFEST.sig.json",
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
    ".pyc",
]


def _load_private_key():
    key_path = KEYS_DIR / "kwyre_signing.key"
    if not key_path.exists():
        print(f"[CodeSign] Private key not found at {key_path}")
        print(f"[CodeSign] Run: python security/license.py keygen")
        sys.exit(1)
    with open(key_path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _load_public_key(pubkey_b64: str = ""):
    if pubkey_b64:
        raw = base64.b64decode(pubkey_b64)
        return load_der_public_key(raw)

    key_path = KEYS_DIR / "kwyre_signing.pub"
    if key_path.exists():
        with open(key_path, "rb") as f:
            return load_pem_public_key(f.read())

    if EMBEDDED_PUBLIC_KEY:
        return _load_public_key(EMBEDDED_PUBLIC_KEY)

    return None


def _should_skip(rel_path: str) -> bool:
    for pattern in SKIP_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def generate_manifest(dist_dir: str, version: str, plat: str) -> dict:
    """Generate a SHA256 manifest for all files in the distribution directory."""
    dist_path = Path(dist_dir).resolve()
    if not dist_path.is_dir():
        print(f"[CodeSign] Directory not found: {dist_dir}")
        sys.exit(1)

    files = {}
    for root, dirs, filenames in os.walk(dist_path):
        dirs[:] = [d for d in dirs if not _should_skip(d)]
        for fname in sorted(filenames):
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, dist_path).replace("\\", "/")
            if _should_skip(rel):
                continue
            file_hash = sha256_file(full)
            file_size = os.path.getsize(full)
            files[rel] = {"sha256": file_hash, "size": file_size}

    manifest = {
        "version": version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": plat,
        "files": files,
    }

    return manifest


def sign_manifest(manifest: dict) -> str:
    """Sign the manifest JSON and return the base64-encoded Ed25519 signature."""
    if not HAS_CRYPTO:
        print("[CodeSign] Install cryptography: pip install cryptography")
        sys.exit(1)

    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    priv = _load_private_key()
    signature = priv.sign(manifest_bytes)
    return base64.b64encode(signature).decode()


def sign_release(dist_dir: str, version: str, plat: str) -> Path:
    """Generate manifest, sign it, and write all output files."""
    dist_path = Path(dist_dir).resolve()

    print(f"\n[CodeSign] Signing release v{version} ({plat})")
    print(f"[CodeSign] Directory: {dist_path}")

    manifest = generate_manifest(dist_dir, version, plat)
    file_count = len(manifest["files"])
    print(f"[CodeSign] Hashed {file_count} files")

    signature_b64 = sign_manifest(manifest)

    manifest_path = dist_path / "MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[CodeSign] Wrote {manifest_path}")

    sig_path = dist_path / "MANIFEST.sig"
    with open(sig_path, "w", encoding="utf-8") as f:
        f.write(signature_b64)
    print(f"[CodeSign] Wrote {sig_path}")

    combined = {
        "manifest": manifest,
        "signature": signature_b64,
    }
    combined_path = dist_path / "MANIFEST.sig.json"
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)
    print(f"[CodeSign] Wrote {combined_path}")

    print(f"\n[CodeSign] Release signed successfully.")
    return combined_path


def verify_release(manifest_path: str, pubkey_b64: str = "") -> bool:
    """
    Verify a signed release manifest.

    Loads the combined manifest+signature file, verifies the Ed25519
    signature, then checks every file hash against the manifest.

    Returns True if valid. Raises ValueError with details if not.
    """
    if not HAS_CRYPTO:
        raise ValueError("cryptography library not installed")

    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.exists():
        raise ValueError(f"Manifest not found: {manifest_path}")

    with open(manifest_file, "r", encoding="utf-8") as f:
        combined = json.load(f)

    if "manifest" in combined and "signature" in combined:
        manifest = combined["manifest"]
        signature_b64 = combined["signature"]
    else:
        raise ValueError("Invalid manifest format — expected 'manifest' and 'signature' keys")

    pub = _load_public_key(pubkey_b64)
    if pub is None:
        raise ValueError("No public key available for verification")

    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    signature = base64.b64decode(signature_b64)

    try:
        pub.verify(signature, manifest_bytes)
    except InvalidSignature:
        raise ValueError("Invalid manifest signature — release is forged or corrupted")

    print(f"[CodeSign] Signature verified (v{manifest.get('version', '?')}, {manifest.get('platform', '?')})")

    dist_dir = manifest_file.parent
    files = manifest.get("files", {})
    failures = []

    for rel_path, expected in files.items():
        full_path = dist_dir / rel_path
        if not full_path.exists():
            failures.append(f"MISSING: {rel_path}")
            continue

        actual_hash = sha256_file(str(full_path))
        if actual_hash != expected["sha256"]:
            failures.append(
                f"HASH MISMATCH: {rel_path} "
                f"(expected {expected['sha256'][:16]}..., got {actual_hash[:16]}...)"
            )

        actual_size = os.path.getsize(full_path)
        if actual_size != expected["size"]:
            failures.append(
                f"SIZE MISMATCH: {rel_path} "
                f"(expected {expected['size']}, got {actual_size})"
            )

    if failures:
        detail = "\n".join(f"  {f}" for f in failures)
        raise ValueError(f"Release verification failed:\n{detail}")

    print(f"[CodeSign] All {len(files)} files verified.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Kwyre Release Code Signing")
    sub = parser.add_subparsers(dest="command")

    sign_p = sub.add_parser("sign", help="Sign a release directory")
    sign_p.add_argument("--dir", required=True, help="Distribution directory to sign")
    sign_p.add_argument("--version", required=True, help="Release version string")
    sign_p.add_argument("--platform", required=True, help="Target platform (windows/linux/macos)")

    verify_p = sub.add_parser("verify", help="Verify a signed release")
    verify_p.add_argument("--manifest", required=True, help="Path to MANIFEST.sig.json")

    hash_p = sub.add_parser("hash", help="SHA256 hash a single file")
    hash_p.add_argument("--file", required=True, help="File to hash")

    args = parser.parse_args()

    if args.command == "sign":
        sign_release(args.dir, args.version, args.platform)
    elif args.command == "verify":
        try:
            verify_release(args.manifest)
            print("[CodeSign] VALID")
        except ValueError as e:
            print(f"[CodeSign] INVALID: {e}")
            sys.exit(1)
    elif args.command == "hash":
        if not os.path.isfile(args.file):
            print(f"[CodeSign] File not found: {args.file}")
            sys.exit(1)
        h = sha256_file(args.file)
        size = os.path.getsize(args.file)
        print(f"{h}  {args.file}  ({size} bytes)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
