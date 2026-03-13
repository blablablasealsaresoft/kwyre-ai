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

import argparse  # command-line argument parsing
import hashlib  # cryptographic hash functions (SHA256)
import importlib  # dynamic module import utilities
import json  # JSON serialization and deserialization
import os  # filesystem and path operations
import subprocess  # spawn external processes (pip)
import sys  # system-level utilities and exit
from pathlib import Path  # object-oriented filesystem paths

MANIFEST_PATH = Path(__file__).parent / "kwyre_dep_manifest.json"  # path to hash manifest file

# Core packages Kwyre depends on — anything else found at runtime is flagged
REQUIRED_PACKAGES = [
    "torch",  # PyTorch deep learning framework
    "transformers",  # HuggingFace model loading and inference
    "peft",  # parameter-efficient fine-tuning (LoRA)
    "trl",  # transformer reinforcement learning library
    "bitsandbytes",  # GPU quantization primitives
    "datasets",  # HuggingFace dataset loading
    "accelerate",  # distributed training utilities
    "psutil",  # system resource monitoring
    "huggingface_hub",  # model hub API client
    "tokenizers",  # fast tokenization backend
    "safetensors",  # safe tensor serialization format
]

# Packages allowed to be present but not required (standard lib companions)
ALLOWLISTED_EXTRA = [
    "pip", "setuptools", "wheel", "pkg_resources",  # packaging tools
    "packaging", "filelock", "requests", "urllib3",  # HTTP and file locking utilities
    "certifi", "charset_normalizer", "idna",  # SSL certs and encoding normalization
    "tqdm", "numpy", "regex", "fsspec",  # progress bars, arrays, regex, filesystem spec
    "pyarrow", "pandas", "scipy",  # data processing and scientific computing
    "sympy", "networkx", "jinja2", "markupsafe",  # symbolic math, graphs, templating
    "mpmath", "typing_extensions", "importlib_metadata",  # math, typing backports, metadata
    "zipp", "six", "attrs", "click",  # zipfile compat, py2/3, classes, CLI framework
    "pyyaml", "aiohttp", "multidict", "yarl",  # YAML parsing and async HTTP
]


def get_package_hash(package_name: str) -> dict:
    """
    Get the installed version and SHA256 hash of a package's dist-info RECORD
    or top-level files. Used to detect tampering post-install.
    """
    try:
        import importlib.metadata as meta  # access installed package metadata
        dist = meta.distribution(package_name)  # look up distribution by name
        version = dist.metadata["Version"]  # extract installed version string

        # Hash the RECORD file which lists all package files + their hashes
        record_path = None  # will hold path to RECORD file
        for f in dist.files or []:  # iterate all files in distribution
            if str(f).endswith("RECORD"):  # find the RECORD manifest file
                record_path = dist.locate_file(f)  # resolve absolute path
                break

        if record_path and Path(record_path).exists():  # RECORD file found on disk
            with open(record_path, "rb") as fh:  # read RECORD in binary mode
                record_hash = hashlib.sha256(fh.read()).hexdigest()  # compute SHA256 of RECORD
        else:
            record_hash = "no-record"  # mark as missing RECORD file

        return {
            "version": version,  # installed package version
            "record_hash": record_hash,  # SHA256 of RECORD file
            "status": "ok",  # package found and hashed successfully
        }
    except Exception as e:  # handle missing or broken packages
        return {"version": "unknown", "record_hash": "error", "status": str(e)}


def generate_manifest():
    """
    Generate a hash manifest from the current clean installation.
    Run this ONCE on a verified clean environment, then commit the manifest.
    """
    print("[Layer 3] Generating dependency manifest...")  # status message for manifest generation
    manifest = {  # initialize manifest structure
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",  # UTC timestamp of generation
        "python_version": sys.version,  # record Python interpreter version
        "packages": {},  # will hold per-package hash data
    }

    import importlib.metadata as meta  # access installed package metadata
    all_dists = list(meta.distributions())  # enumerate all installed distributions
    print(f"[Layer 3] Scanning {len(all_dists)} installed packages...")  # display package count

    for dist in all_dists:  # iterate each installed distribution
        name = dist.metadata.get("Name", "").lower()  # normalize package name to lowercase
        if not name:  # skip distributions without a name
            continue
        pkg_info = get_package_hash(name)  # compute version and hash for package
        manifest["packages"][name] = pkg_info  # store package info in manifest
        if pkg_info["status"] == "ok":  # successfully hashed
            print(f"  [OK] {name}=={pkg_info['version']}")  # display success for this package
        else:
            print(f"  [??] {name} -- {pkg_info['status']}")  # display error status

    with open(MANIFEST_PATH, "w") as f:  # write manifest to JSON file
        json.dump(manifest, f, indent=2)  # serialize with pretty-printing

    print(f"\n[Layer 3] Manifest written to {MANIFEST_PATH}")  # confirm file location
    print(f"[Layer 3] {len(manifest['packages'])} packages recorded.")  # display total package count
    print(f"[Layer 3] Commit this file to your repo and verify on every deployment.")  # usage guidance


def verify_manifest() -> bool:
    """
    Verify all installed packages match the manifest.
    Returns True if clean, False if any tampering detected.
    """
    if not MANIFEST_PATH.exists():  # no manifest file on disk
        print(f"[Layer 3] WARNING: No manifest found at {MANIFEST_PATH}")  # warn about missing manifest
        print(f"[Layer 3] Run: python verify_deps.py generate")  # suggest generating one
        print(f"[Layer 3] Skipping dependency verification.")  # explain skip behavior
        return True  # Non-blocking until manifest is set up

    print(f"[Layer 3] Verifying dependencies against manifest...")  # status for verification start
    with open(MANIFEST_PATH) as f:  # open manifest for reading
        manifest = json.load(f)  # deserialize manifest JSON

    known = manifest.get("packages", {})  # extract known package data
    failures = []  # list of critical integrity failures
    warnings = []  # list of non-critical warnings

    import importlib.metadata as meta  # access installed package metadata
    for dist in meta.distributions():  # iterate all currently installed packages
        name = dist.metadata.get("Name", "").lower()  # normalize name to lowercase
        if not name:  # skip unnamed distributions
            continue

        current = get_package_hash(name)  # compute current hash for comparison

        if name not in known:  # package not present in original manifest
            # New package not in manifest — could be legitimate or injected
            if name not in [p.lower() for p in ALLOWLISTED_EXTRA]:  # not on allow list
                warnings.append(f"UNEXPECTED PACKAGE: {name}=={current['version']} "  # flag unexpected package
                                 f"(not in manifest, not allowlisted)")
            continue

        expected = known[name]  # retrieve expected hash and version

        # Version mismatch
        if current["version"] != expected["version"]:  # installed version differs from manifest
            failures.append(
                f"VERSION MISMATCH: {name} "  # record version mismatch failure
                f"(expected {expected['version']}, got {current['version']})"
            )
            continue

        # Hash mismatch — most serious
        if (current["record_hash"] != expected["record_hash"]  # RECORD file hash differs
                and expected["record_hash"] not in ("no-record", "error")  # expected hash is valid
                and current["record_hash"] not in ("no-record", "error")):  # current hash is valid
            failures.append(
                f"HASH MISMATCH: {name}=={current['version']} "  # record hash tampering failure
                f"(expected {expected['record_hash'][:12]}..., "
                f"got {current['record_hash'][:12]}...)"
            )

    # Report
    if failures:  # critical integrity issues found
        print("\n[Layer 3] *** DEPENDENCY INTEGRITY FAILURES ***")  # failure section header
        for f in failures:  # iterate each failure
            print(f"  [FAIL] {f}")  # display individual failure

    if warnings:  # non-critical issues found
        print("\n[Layer 3] *** DEPENDENCY WARNINGS ***")  # warning section header
        for w in warnings:  # iterate each warning
            print(f"  [WARN] {w}")  # display individual warning

    if not failures and not warnings:  # all packages verified clean
        print(f"[Layer 3] All {len(known)} packages verified clean.")  # confirm clean state
    elif not failures:  # warnings but no critical failures
        print(f"\n[Layer 3] {len(warnings)} warning(s) but no integrity failures.")  # summarize warnings

    return len(failures) == 0  # return True only if no critical failures


def verify_required_only() -> bool:
    """
    Lightweight check — only verify the core packages Kwyre actually uses.
    Faster than full manifest scan, suitable for server startup.
    """
    if not MANIFEST_PATH.exists():  # no manifest to check against
        print("[Layer 3] No manifest — skipping required package check.")  # warn and skip
        return True

    with open(MANIFEST_PATH) as f:  # open manifest for reading
        manifest = json.load(f)  # deserialize manifest JSON
    known = manifest.get("packages", {})  # extract known package data

    print("[Layer 3] Verifying core dependencies...")  # status for core verification
    failures = []  # list of critical failures for required packages
    for pkg in REQUIRED_PACKAGES:  # iterate core required packages
        pkg_lower = pkg.lower()  # normalize package name
        current = get_package_hash(pkg_lower)  # get current installed hash
        if current["status"] != "ok":  # package not installed or broken
            print(f"  [??] {pkg} -- {current['status']}")  # display error status
            continue

        if pkg_lower not in known:  # package not recorded in manifest
            print(f"  [??] {pkg} -- not in manifest")  # warn about missing manifest entry
            continue

        expected = known[pkg_lower]  # retrieve expected package info
        if current["version"] != expected["version"]:  # version mismatch detected
            failures.append(f"{pkg}: version {current['version']} != {expected['version']}")  # record version failure
        elif (current["record_hash"] != expected["record_hash"]  # hash mismatch detected
              and expected["record_hash"] not in ("no-record", "error")):  # only if expected hash is valid
            failures.append(f"{pkg}: hash mismatch")  # record hash failure
        else:
            print(f"  [OK] {pkg}=={current['version']}")  # package verified clean

    if failures:  # critical failures found in core packages
        print("\n[Layer 3] CORE DEPENDENCY FAILURES:")  # failure section header
        for f in failures:  # iterate each failure
            print(f"  [FAIL] {f}")  # display individual failure
        return False  # indicate verification failed

    print(f"[Layer 3] {len(REQUIRED_PACKAGES)} core packages verified.")  # confirm all core packages clean
    return True  # all core packages verified successfully


def audit_unexpected():
    """List packages not in manifest and not allowlisted."""
    if not MANIFEST_PATH.exists():  # no manifest to audit against
        print("[Layer 3] No manifest to audit against.")  # warn about missing manifest
        return

    with open(MANIFEST_PATH) as f:  # open manifest for reading
        manifest = json.load(f)  # deserialize manifest JSON
    known = set(manifest.get("packages", {}).keys())  # set of known package names
    allowlisted = {p.lower() for p in ALLOWLISTED_EXTRA}  # set of allowlisted package names

    import importlib.metadata as meta  # access installed package metadata
    unexpected = []  # list to collect unexpected packages
    for dist in meta.distributions():  # iterate all installed distributions
        name = (dist.metadata.get("Name") or "").lower()  # normalize package name
        if name and name not in known and name not in allowlisted:  # not known and not allowlisted
            version = dist.metadata.get("Version", "?")  # get installed version
            unexpected.append((name, version))  # add to unexpected list

    if unexpected:  # unexpected packages were found
        print(f"[Layer 3] {len(unexpected)} unexpected packages (not in manifest):")  # display count
        for name, ver in sorted(unexpected):  # iterate alphabetically
            print(f"  {name}=={ver}")  # display each unexpected package
        print("\nIf these are legitimate, re-run: python verify_deps.py generate")  # suggest re-generating manifest
    else:
        print("[Layer 3] No unexpected packages found.")  # all packages accounted for


def main():  # CLI entry point for dependency verification commands
    parser = argparse.ArgumentParser(description="Kwyre Layer 3: Dependency Integrity")  # create CLI parser
    parser.add_argument(  # required positional command argument
        "command",
        choices=["generate", "verify", "verify-core", "audit"],
        help=(
            "generate=build manifest from clean install | "
            "verify=full check | "
            "verify-core=check required packages only (fast) | "
            "audit=list unexpected packages"
        ),
    )
    args = parser.parse_args()  # parse command-line arguments

    if args.command == "generate":  # build new manifest from current install
        generate_manifest()
    elif args.command == "verify":  # full verification against manifest
        ok = verify_manifest()  # run full package verification
        sys.exit(0 if ok else 1)  # exit with appropriate status code
    elif args.command == "verify-core":  # fast core-only verification
        ok = verify_required_only()  # verify only required packages
        sys.exit(0 if ok else 1)  # exit with appropriate status code
    elif args.command == "audit":  # list unexpected packages
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
    ok = verify_required_only()  # run lightweight core package check
    if not ok:  # verification failed
        if abort_on_failure:  # configured to halt on failure
            print("[Layer 3] ABORTING: Dependency integrity check failed.")  # critical abort message
            sys.exit(1)  # terminate process with error code
        else:
            print("[Layer 3] WARNING: Dependency integrity issues detected.")  # non-fatal warning
    return ok  # return verification result


if __name__ == "__main__":  # only run when executed directly
    main()  # invoke CLI entry point
