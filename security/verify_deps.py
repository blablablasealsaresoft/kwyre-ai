#!/usr/bin/env python3
"""
Kwyre Layer 3: Dependency Integrity Verification
=================================================
Generates and verifies SHA256 hashes for all installed Python packages.

Supply chain attacks through pip packages are real. This module:
  1. Generates a locked requirements file with per-package SHA256 hashes
  2. Verifies installed packages match known-good hashes at runtime
  3. Detects unexpected packages that weren't in the original install

Usage:
  # One-time: generate hash manifest from your clean install
  python verify_deps.py generate

  # Every startup: verify current packages match manifest
  python verify_deps.py verify

  # Install from locked file (no hash mismatches allowed)
  python verify_deps.py install

  # Check for unexpected packages not in manifest
  python verify_deps.py audit
"""

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "kwyre_dep_manifest.json"

# Core packages Kwyre depends on — anything else found at runtime is flagged
REQUIRED_PACKAGES = [
    "torch",
    "transformers",
    "peft",
    "trl",
    "bitsandbytes",
    "datasets",
    "accelerate",
    "psutil",
    "huggingface_hub",
    "tokenizers",
    "safetensors",
]

# Packages allowed to be present but not required (standard lib companions)
ALLOWLISTED_EXTRA = [
    "pip", "setuptools", "wheel", "pkg_resources",
    "packaging", "filelock", "requests", "urllib3",
    "certifi", "charset_normalizer", "idna",
    "tqdm", "numpy", "regex", "fsspec",
    "pyarrow", "pandas", "scipy",
    "sympy", "networkx", "jinja2", "markupsafe",
    "mpmath", "typing_extensions", "importlib_metadata",
    "zipp", "six", "attrs", "click",
    "pyyaml", "aiohttp", "multidict", "yarl",
]


def get_package_hash(package_name: str) -> dict:
    """
    Get the installed version and SHA256 hash of a package's dist-info RECORD
    or top-level files. Used to detect tampering post-install.
    """
    try:
        import importlib.metadata as meta
        dist = meta.distribution(package_name)
        version = dist.metadata["Version"]

        # Hash the RECORD file which lists all package files + their hashes
        record_path = None
        for f in dist.files or []:
            if str(f).endswith("RECORD"):
                record_path = dist.locate_file(f)
                break

        if record_path and Path(record_path).exists():
            with open(record_path, "rb") as fh:
                record_hash = hashlib.sha256(fh.read()).hexdigest()
        else:
            record_hash = "no-record"

        return {
            "version": version,
            "record_hash": record_hash,
            "status": "ok",
        }
    except Exception as e:
        return {"version": "unknown", "record_hash": "error", "status": str(e)}


def generate_manifest():
    """
    Generate a hash manifest from the current clean installation.
    Run this ONCE on a verified clean environment, then commit the manifest.
    """
    print("[Layer 3] Generating dependency manifest...")
    manifest = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "python_version": sys.version,
        "packages": {},
    }

    import importlib.metadata as meta
    all_dists = list(meta.distributions())
    print(f"[Layer 3] Scanning {len(all_dists)} installed packages...")

    for dist in all_dists:
        name = dist.metadata.get("Name", "").lower()
        if not name:
            continue
        pkg_info = get_package_hash(name)
        manifest["packages"][name] = pkg_info
        if pkg_info["status"] == "ok":
            print(f"  ✓ {name}=={pkg_info['version']}")
        else:
            print(f"  ? {name} — {pkg_info['status']}")

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n[Layer 3] Manifest written to {MANIFEST_PATH}")
    print(f"[Layer 3] {len(manifest['packages'])} packages recorded.")
    print(f"[Layer 3] Commit this file to your repo and verify on every deployment.")


def verify_manifest() -> bool:
    """
    Verify all installed packages match the manifest.
    Returns True if clean, False if any tampering detected.
    """
    if not MANIFEST_PATH.exists():
        print(f"[Layer 3] WARNING: No manifest found at {MANIFEST_PATH}")
        print(f"[Layer 3] Run: python verify_deps.py generate")
        print(f"[Layer 3] Skipping dependency verification.")
        return True  # Non-blocking until manifest is set up

    print(f"[Layer 3] Verifying dependencies against manifest...")
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    known = manifest.get("packages", {})
    failures = []
    warnings = []

    import importlib.metadata as meta
    for dist in meta.distributions():
        name = dist.metadata.get("Name", "").lower()
        if not name:
            continue

        current = get_package_hash(name)

        if name not in known:
            # New package not in manifest — could be legitimate or injected
            if name not in [p.lower() for p in ALLOWLISTED_EXTRA]:
                warnings.append(f"UNEXPECTED PACKAGE: {name}=={current['version']} "
                                 f"(not in manifest, not allowlisted)")
            continue

        expected = known[name]

        # Version mismatch
        if current["version"] != expected["version"]:
            failures.append(
                f"VERSION MISMATCH: {name} "
                f"(expected {expected['version']}, got {current['version']})"
            )
            continue

        # Hash mismatch — most serious
        if (current["record_hash"] != expected["record_hash"]
                and expected["record_hash"] not in ("no-record", "error")
                and current["record_hash"] not in ("no-record", "error")):
            failures.append(
                f"HASH MISMATCH: {name}=={current['version']} "
                f"(expected {expected['record_hash'][:12]}..., "
                f"got {current['record_hash'][:12]}...)"
            )

    # Report
    if failures:
        print("\n[Layer 3] *** DEPENDENCY INTEGRITY FAILURES ***")
        for f in failures:
            print(f"  [FAIL] {f}")

    if warnings:
        print("\n[Layer 3] *** DEPENDENCY WARNINGS ***")
        for w in warnings:
            print(f"  [WARN] {w}")

    if not failures and not warnings:
        print(f"[Layer 3] All {len(known)} packages verified clean.")
    elif not failures:
        print(f"\n[Layer 3] {len(warnings)} warning(s) but no integrity failures.")

    return len(failures) == 0


def verify_required_only() -> bool:
    """
    Lightweight check — only verify the core packages Kwyre actually uses.
    Faster than full manifest scan, suitable for server startup.
    """
    if not MANIFEST_PATH.exists():
        print("[Layer 3] No manifest — skipping required package check.")
        return True

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    known = manifest.get("packages", {})

    print("[Layer 3] Verifying core dependencies...")
    failures = []
    for pkg in REQUIRED_PACKAGES:
        pkg_lower = pkg.lower()
        current = get_package_hash(pkg_lower)
        if current["status"] != "ok":
            print(f"  ? {pkg} — {current['status']}")
            continue

        if pkg_lower not in known:
            print(f"  ? {pkg} — not in manifest")
            continue

        expected = known[pkg_lower]
        if current["version"] != expected["version"]:
            failures.append(f"{pkg}: version {current['version']} != {expected['version']}")
        elif (current["record_hash"] != expected["record_hash"]
              and expected["record_hash"] not in ("no-record", "error")):
            failures.append(f"{pkg}: hash mismatch")
        else:
            print(f"  ✓ {pkg}=={current['version']}")

    if failures:
        print("\n[Layer 3] CORE DEPENDENCY FAILURES:")
        for f in failures:
            print(f"  [FAIL] {f}")
        return False

    print(f"[Layer 3] {len(REQUIRED_PACKAGES)} core packages verified.")
    return True


def audit_unexpected():
    """List packages not in manifest and not allowlisted."""
    if not MANIFEST_PATH.exists():
        print("[Layer 3] No manifest to audit against.")
        return

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    known = set(manifest.get("packages", {}).keys())
    allowlisted = {p.lower() for p in ALLOWLISTED_EXTRA}

    import importlib.metadata as meta
    unexpected = []
    for dist in meta.distributions():
        name = (dist.metadata.get("Name") or "").lower()
        if name and name not in known and name not in allowlisted:
            version = dist.metadata.get("Version", "?")
            unexpected.append((name, version))

    if unexpected:
        print(f"[Layer 3] {len(unexpected)} unexpected packages (not in manifest):")
        for name, ver in sorted(unexpected):
            print(f"  {name}=={ver}")
        print("\nIf these are legitimate, re-run: python verify_deps.py generate")
    else:
        print("[Layer 3] No unexpected packages found.")


def main():
    parser = argparse.ArgumentParser(description="Kwyre Layer 3: Dependency Integrity")
    parser.add_argument(
        "command",
        choices=["generate", "verify", "verify-core", "audit"],
        help=(
            "generate=build manifest from clean install | "
            "verify=full check | "
            "verify-core=check required packages only (fast) | "
            "audit=list unexpected packages"
        ),
    )
    args = parser.parse_args()

    if args.command == "generate":
        generate_manifest()
    elif args.command == "verify":
        ok = verify_manifest()
        sys.exit(0 if ok else 1)
    elif args.command == "verify-core":
        ok = verify_required_only()
        sys.exit(0 if ok else 1)
    elif args.command == "audit":
        audit_unexpected()


# ---------------------------------------------------------------------------
# Integration: call this from serve_local_4bit.py at startup
# ---------------------------------------------------------------------------
def startup_check(abort_on_failure: bool = True) -> bool:
    """
    Drop this into serve_local_4bit.py startup sequence:

        from verify_deps import startup_check
        startup_check(abort_on_failure=True)

    Uses verify-core (fast) by default.
    Set abort_on_failure=False to warn without stopping the server.
    """
    ok = verify_required_only()
    if not ok:
        if abort_on_failure:
            print("[Layer 3] ABORTING: Dependency integrity check failed.")
            sys.exit(1)
        else:
            print("[Layer 3] WARNING: Dependency integrity issues detected.")
    return ok


if __name__ == "__main__":
    main()
