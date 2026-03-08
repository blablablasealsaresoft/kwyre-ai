#!/usr/bin/env python3
"""
Kwyre License Key System
========================
Ed25519-signed license keys that work fully offline.

Architecture:
  - Private key: kept by Apollo CyberSentinel (used to SIGN keys)
  - Public key: embedded in the server (used to VERIFY keys)
  - License key: base64-encoded JSON payload + Ed25519 signature

The server never needs to contact any external server to validate a license.
This is critical for air-gapped deployments.

Usage:
  # One-time: generate signing keypair
  python license.py keygen

  # Issue a license
  python license.py issue --tier professional --machines 3 --customer "anon-hash-123"

  # Validate a license key
  python license.py validate --key "KWYRE-..."

  # Validate from file
  python license.py validate --file ./kwyre.license
"""

import argparse
import base64
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

KEYS_DIR = Path(__file__).parent / ".keys"

TIERS = {
    "personal":     {"machines": 1,  "label": "Personal"},
    "professional": {"machines": 3,  "label": "Professional"},
    "airgapped":    {"machines": 5,  "label": "Air-Gapped Kit"},
    "unlimited":    {"machines": 999, "label": "Unlimited (Internal)"},
}

# Embedded public key for license verification (set after keygen)
# This is safe to embed in source — it can only VERIFY, not create licenses.
EMBEDDED_PUBLIC_KEY = ""  # Set after running: python license.py keygen


def _load_private_key():
    key_path = KEYS_DIR / "kwyre_signing.key"
    if not key_path.exists():
        print(f"[License] Private key not found at {key_path}")
        print(f"[License] Run: python license.py keygen")
        sys.exit(1)
    with open(key_path, "rb") as f:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        return load_pem_private_key(f.read(), password=None)


def _load_public_key(pubkey_b64: str = ""):
    if pubkey_b64:
        raw = base64.b64decode(pubkey_b64)
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        return load_der_public_key(raw)

    key_path = KEYS_DIR / "kwyre_signing.pub"
    if key_path.exists():
        with open(key_path, "rb") as f:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            return load_pem_public_key(f.read())

    if EMBEDDED_PUBLIC_KEY:
        return _load_public_key(EMBEDDED_PUBLIC_KEY)

    return None


def keygen():
    """Generate Ed25519 signing keypair."""
    if not HAS_CRYPTO:
        print("[License] Install cryptography: pip install cryptography")
        sys.exit(1)

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_path = KEYS_DIR / "kwyre_signing.key"
    pub_path = KEYS_DIR / "kwyre_signing.pub"

    with open(priv_path, "wb") as f:
        f.write(priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    os.chmod(priv_path, 0o600)

    with open(pub_path, "wb") as f:
        f.write(pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))

    pub_b64 = base64.b64encode(
        pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).decode()

    print(f"[License] Keypair generated.")
    print(f"[License] Private key: {priv_path} (KEEP SECRET)")
    print(f"[License] Public key:  {pub_path}")
    print()
    print(f"Embed this public key in serve_local_4bit.py or set KWYRE_LICENSE_PUBKEY:")
    print(f"  {pub_b64}")
    print()
    print(f"Add to .gitignore: security/.keys/")


def get_machine_fingerprint() -> str:
    """Generate a stable fingerprint for the current machine."""
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
    ]
    try:
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(
                ["wmic", "bios", "get", "serialnumber"],
                capture_output=True, text=True, timeout=5
            )
            bios = result.stdout.strip().split("\n")[-1].strip()
            if bios and bios != "To be filled by O.E.M.":
                parts.append(bios)
        elif sys.platform == "linux":
            mid_path = Path("/etc/machine-id")
            if mid_path.exists():
                parts.append(mid_path.read_text().strip())
    except Exception:
        pass

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def issue_license(tier: str, machines: int = None, customer: str = "",
                  perpetual: bool = True, days: int = 0) -> str:
    """Issue a signed license key."""
    if not HAS_CRYPTO:
        print("[License] Install cryptography: pip install cryptography")
        sys.exit(1)

    if tier not in TIERS:
        print(f"[License] Unknown tier: {tier}. Options: {list(TIERS.keys())}")
        sys.exit(1)

    if machines is None:
        machines = TIERS[tier]["machines"]

    payload = {
        "v": 1,
        "tier": tier,
        "label": TIERS[tier]["label"],
        "machines": machines,
        "customer": customer or hashlib.sha256(os.urandom(16)).hexdigest()[:12],
        "issued_at": int(time.time()),
        "expires_at": None if perpetual else int(time.time() + days * 86400),
    }

    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

    priv = _load_private_key()
    signature = priv.sign(payload_bytes)

    token_data = {
        "p": base64.b64encode(payload_bytes).decode(),
        "s": base64.b64encode(signature).decode(),
    }

    raw_token = base64.b64encode(
        json.dumps(token_data, separators=(",", ":")).encode()
    ).decode()

    chunks = [raw_token[i:i+48] for i in range(0, len(raw_token), 48)]
    key = "KWYRE-" + "-".join(chunks)

    return key


def validate_license(key: str, pubkey_b64: str = "",
                     check_machine: bool = False) -> dict:
    """
    Validate a license key. Returns the payload dict if valid.
    Raises ValueError if invalid.

    This function works fully offline — no network calls.
    """
    if not HAS_CRYPTO:
        raise ValueError("cryptography library not installed")

    clean = key.replace("KWYRE-", "", 1).replace("-", "").replace("\n", "").replace(" ", "")

    try:
        token_json = base64.b64decode(clean)
        token_data = json.loads(token_json)
    except Exception:
        raise ValueError("Malformed license key")

    try:
        payload_bytes = base64.b64decode(token_data["p"])
        signature = base64.b64decode(token_data["s"])
    except Exception:
        raise ValueError("Malformed license key structure")

    pub = _load_public_key(pubkey_b64)
    if pub is None:
        raise ValueError("No public key available for verification")

    try:
        pub.verify(signature, payload_bytes)
    except InvalidSignature:
        raise ValueError("Invalid license signature — key is forged or corrupted")

    payload = json.loads(payload_bytes)

    if payload.get("expires_at") and payload["expires_at"] < time.time():
        raise ValueError(f"License expired on {time.strftime('%Y-%m-%d', time.localtime(payload['expires_at']))}")

    return payload


def startup_validate(key_source: str = None, pubkey_b64: str = "") -> dict:
    """
    Validate license at server startup. Checks (in order):
      1. key_source argument
      2. KWYRE_LICENSE_KEY env var
      3. ./kwyre.license file
      4. ~/.kwyre/license file

    Returns the license payload if valid.
    Raises SystemExit if no valid license found.
    """
    key = key_source

    if not key:
        key = os.environ.get("KWYRE_LICENSE_KEY", "")

    if not key:
        for p in [Path("kwyre.license"), Path.home() / ".kwyre" / "license"]:
            if p.exists():
                key = p.read_text().strip()
                break

    if not key:
        print("[License] No license key found.")
        print("[License] Set KWYRE_LICENSE_KEY env var or place key in ./kwyre.license")
        print("[License] Purchase at https://kwyre.com")
        return None

    try:
        payload = validate_license(key, pubkey_b64=pubkey_b64)
        print(f"[License] Valid — {payload['label']} ({payload['machines']} machine(s))")
        if payload.get("expires_at"):
            exp = time.strftime("%Y-%m-%d", time.localtime(payload["expires_at"]))
            print(f"[License] Expires: {exp}")
        else:
            print(f"[License] Perpetual license")
        return payload
    except ValueError as e:
        print(f"[License] INVALID: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Kwyre License Key System")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("keygen", help="Generate Ed25519 signing keypair")

    issue_p = sub.add_parser("issue", help="Issue a license key")
    issue_p.add_argument("--tier", required=True, choices=list(TIERS.keys()))
    issue_p.add_argument("--machines", type=int, default=None)
    issue_p.add_argument("--customer", default="")
    issue_p.add_argument("--days", type=int, default=0, help="Expiry in days (0=perpetual)")
    issue_p.add_argument("--out", default="", help="Write key to file")

    val_p = sub.add_parser("validate", help="Validate a license key")
    val_p.add_argument("--key", default="")
    val_p.add_argument("--file", default="")

    fp_p = sub.add_parser("fingerprint", help="Show this machine's fingerprint")

    args = parser.parse_args()

    if args.command == "keygen":
        keygen()
    elif args.command == "issue":
        perpetual = args.days == 0
        key = issue_license(args.tier, args.machines, args.customer, perpetual, args.days)
        print(f"\n{'='*60}")
        print(f"  License Key — {TIERS[args.tier]['label']}")
        print(f"{'='*60}\n")
        print(key)
        print()
        if args.out:
            Path(args.out).write_text(key)
            print(f"Written to {args.out}")
    elif args.command == "validate":
        key = args.key
        if args.file:
            key = Path(args.file).read_text().strip()
        if not key:
            print("Provide --key or --file")
            sys.exit(1)
        try:
            payload = validate_license(key)
            print(f"[License] VALID")
            print(json.dumps(payload, indent=2))
        except ValueError as e:
            print(f"[License] INVALID: {e}")
            sys.exit(1)
    elif args.command == "fingerprint":
        print(f"Machine fingerprint: {get_machine_fingerprint()}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
