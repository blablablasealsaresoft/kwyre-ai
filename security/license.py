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

  # Issue a machine-bound license
  python license.py issue --tier professional --fingerprints abc123 def456

  # Bind an existing license to specific machines
  python license.py bind --key "KWYRE-..." --fingerprints abc123 def456

  # Validate a license key
  python license.py validate --key "KWYRE-..."

  # Validate from file
  python license.py validate --file ./kwyre.license

  # Show this machine's fingerprint
  python license.py fingerprint
"""

import argparse  # command-line argument parsing
import base64  # base64 encoding and decoding
import hashlib  # cryptographic hash functions
import json  # JSON serialization and deserialization
import os  # filesystem and path operations
import platform  # hardware and OS identification
import sys  # system-level utilities and exit
import time  # timestamps and time operations
from pathlib import Path  # object-oriented filesystem paths

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # Ed25519 key classes
        Ed25519PrivateKey,  # private key for signing
        Ed25519PublicKey,  # public key for verification
    )
    from cryptography.hazmat.primitives.serialization import (  # key serialization formats
        Encoding,  # PEM/DER encoding selection
        NoEncryption,  # export private key without password
        PrivateFormat,  # PKCS8 private key format
        PublicFormat,  # SubjectPublicKeyInfo public key format
    )
    from cryptography.exceptions import InvalidSignature  # raised when signature check fails
    HAS_CRYPTO = True  # cryptography library is available
except ImportError:
    HAS_CRYPTO = False  # cryptography library not installed

KEYS_DIR = Path(__file__).parent / ".keys"  # directory for signing keypair storage

TIERS = {  # license tier definitions with machine limits
    "personal":     {"machines": 1,  "label": "Personal"},  # single machine license
    "professional": {"machines": 3,  "label": "Professional"},  # up to 3 machines
    "airgapped":    {"machines": 5,  "label": "Air-Gapped Kit"},  # up to 5 air-gapped machines
    "unlimited":    {"machines": 999, "label": "Unlimited (Internal)"},  # internal use only
}

# Embedded public key for license verification (set after keygen)
# This is safe to embed in source — it can only VERIFY, not create licenses.
EMBEDDED_PUBLIC_KEY = ""  # Set after running: python license.py keygen


def _load_private_key():  # load Ed25519 private key from disk
    key_path = KEYS_DIR / "kwyre_signing.key"  # path to private key file
    if not key_path.exists():  # private key not found
        print(f"[License] Private key not found at {key_path}")  # warn about missing key
        print(f"[License] Run: python license.py keygen")  # suggest generating keypair
        sys.exit(1)  # abort without private key
    with open(key_path, "rb") as f:  # open key file in binary mode
        from cryptography.hazmat.primitives.serialization import load_pem_private_key  # PEM key loader
        return load_pem_private_key(f.read(), password=None)  # deserialize PEM private key


def _load_public_key(pubkey_b64: str = ""):  # load Ed25519 public key from various sources
    if pubkey_b64:  # base64-encoded DER public key provided
        raw = base64.b64decode(pubkey_b64)  # decode base64 to raw DER bytes
        from cryptography.hazmat.primitives.serialization import load_der_public_key  # DER key loader
        return load_der_public_key(raw)  # deserialize DER public key

    key_path = KEYS_DIR / "kwyre_signing.pub"  # path to PEM public key file
    if key_path.exists():  # PEM public key file found
        with open(key_path, "rb") as f:  # open key file in binary mode
            from cryptography.hazmat.primitives.serialization import load_pem_public_key  # PEM key loader
            return load_pem_public_key(f.read())  # deserialize PEM public key

    if EMBEDDED_PUBLIC_KEY:  # fallback to source-embedded public key
        return _load_public_key(EMBEDDED_PUBLIC_KEY)  # recursively load embedded key

    return None  # no public key source available


def keygen():  # generate new Ed25519 signing keypair
    """Generate Ed25519 signing keypair."""
    if not HAS_CRYPTO:  # cryptography library required
        print("[License] Install cryptography: pip install cryptography")  # installation instruction
        sys.exit(1)  # abort without dependency

    KEYS_DIR.mkdir(parents=True, exist_ok=True)  # ensure keys directory exists

    priv = Ed25519PrivateKey.generate()  # generate random Ed25519 private key
    pub = priv.public_key()  # derive public key from private key

    priv_path = KEYS_DIR / "kwyre_signing.key"  # output path for private key
    pub_path = KEYS_DIR / "kwyre_signing.pub"  # output path for public key

    with open(priv_path, "wb") as f:  # write private key to file
        f.write(priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))  # serialize as PEM PKCS8
    if sys.platform == "win32":
        # os.chmod on Windows only controls the read-only flag, not ACLs.
        # Use icacls to restrict the private key to the current user.
        try:
            import subprocess as _sp
            _sp.run(
                ["icacls", str(priv_path), "/inheritance:r",
                 "/grant:r", f"{os.environ.get('USERNAME', 'SYSTEM')}:(R,W)"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
    else:
        os.chmod(priv_path, 0o600)

    with open(pub_path, "wb") as f:  # write public key to file
        f.write(pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))  # serialize as PEM SPKI

    pub_b64 = base64.b64encode(  # encode public key for embedding in source
        pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)  # serialize as DER for compactness
    ).decode()  # convert bytes to string

    print(f"[License] Keypair generated.")  # confirm keypair creation
    print(f"[License] Private key: {priv_path} (KEEP SECRET)")  # display private key path
    print(f"[License] Public key:  {pub_path}")  # display public key path
    print()
    print(f"Embed this public key in serve_local_4bit.py or set KWYRE_LICENSE_PUBKEY:")  # embedding instruction
    print(f"  {pub_b64}")  # display base64 public key
    print()
    print(f"Add to .gitignore: security/.keys/")  # remind to exclude keys from git


def get_machine_fingerprint() -> str:  # generate unique hardware identifier
    """Generate a stable fingerprint for the current machine."""
    parts = [  # collect platform identifiers
        platform.node(),  # hostname of the machine
        platform.machine(),  # CPU architecture (x86_64, arm64, etc.)
        platform.processor(),  # processor description string
    ]
    try:
        import subprocess  # spawn external commands for hardware IDs
        if sys.platform == "win32":  # Windows-specific hardware identifiers
            uuid_val = None  # will hold system UUID
            try:
                result = subprocess.run(
                    ["wmic", "csproduct", "get", "uuid"],
                    capture_output=True, text=True, timeout=5
                )
                uuid_val = result.stdout.strip().split("\n")[-1].strip()
                if uuid_val and uuid_val.lower() not in ("", "ffffffff-ffff-ffff-ffff-ffffffffffff"):
                    parts.append(uuid_val)
                else:
                    uuid_val = None
            except Exception:
                uuid_val = None

            # PowerShell/CIM fallback — WMIC is deprecated on Windows 11+
            if not uuid_val:
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Get-CimInstance -ClassName Win32_ComputerSystemProduct"
                         " | Select-Object -ExpandProperty UUID"],
                        capture_output=True, text=True, timeout=10
                    )
                    ps_uuid = result.stdout.strip()
                    if ps_uuid and ps_uuid.lower() not in ("", "ffffffff-ffff-ffff-ffff-ffffffffffff"):
                        uuid_val = ps_uuid
                        parts.append(uuid_val)
                except Exception:
                    pass

            if not uuid_val:
                try:
                    result = subprocess.run(  # query BIOS serial number via WMIC
                        ["wmic", "bios", "get", "serialnumber"],
                        capture_output=True, text=True, timeout=5
                    )
                    bios = result.stdout.strip().split("\n")[-1].strip()  # extract serial from output
                    if bios and bios != "To be filled by O.E.M.":  # skip placeholder values
                        parts.append(bios)  # add BIOS serial to fingerprint
                except Exception:
                    pass  # BIOS serial query failed

            try:
                result = subprocess.run(  # query disk drive serial number
                    ["wmic", "diskdrive", "get", "serialnumber"],
                    capture_output=True, text=True, timeout=5
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n")[1:] if l.strip()]  # parse serial numbers
                if lines:  # at least one disk serial found
                    parts.append(lines[0])  # add first disk serial to fingerprint
            except Exception:
                pass  # disk serial query failed

        elif sys.platform == "darwin":  # macOS-specific hardware identifier
            try:
                result = subprocess.run(  # query IOPlatformUUID from IOKit registry
                    ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):  # scan output for UUID line
                    if "IOPlatformUUID" in line:  # found platform UUID entry
                        uuid_val = line.split("=")[-1].strip().strip('"')  # extract UUID value
                        if uuid_val:  # UUID is non-empty
                            parts.append(uuid_val)  # add macOS UUID to fingerprint
                        break
            except Exception:
                pass  # ioreg command failed

        elif sys.platform == "linux":  # Linux-specific hardware identifiers
            mid_path = Path("/etc/machine-id")  # systemd machine-id file
            if mid_path.exists():  # machine-id file present
                parts.append(mid_path.read_text().strip())  # add machine-id to fingerprint
            product_uuid = Path("/sys/class/dmi/id/product_uuid")  # DMI product UUID
            try:
                if product_uuid.exists():  # product UUID file exists
                    parts.append(product_uuid.read_text().strip())  # add product UUID to fingerprint
            except Exception:
                pass  # permission denied or read failure
    except Exception:
        pass  # subprocess import or platform detection failed

    raw = "|".join(parts)  # concatenate all identifier parts
    return hashlib.sha256(raw.encode()).hexdigest()[:32]  # hash to 32-char hex fingerprint


def _sign_and_encode(payload: dict) -> str:  # sign payload and encode as license key string
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()  # canonical JSON encoding

    priv = _load_private_key()  # load signing private key from disk
    signature = priv.sign(payload_bytes)  # Ed25519 sign the payload bytes

    token_data = {  # combine payload and signature for transport
        "p": base64.b64encode(payload_bytes).decode(),  # base64-encoded payload
        "s": base64.b64encode(signature).decode(),  # base64-encoded signature
    }

    raw_token = base64.b64encode(  # encode entire token as base64 string
        json.dumps(token_data, separators=(",", ":")).encode()
    ).decode()

    chunks = [raw_token[i:i+48] for i in range(0, len(raw_token), 48)]  # split into 48-char chunks for readability
    return "KWYRE-" + "-".join(chunks)  # format as KWYRE-prefixed hyphenated key


def issue_license(tier: str, machines: int = None, customer: str = "",
                  perpetual: bool = True, days: int = 0,
                  machine_ids: list = None) -> str:  # create and sign a new license key
    """Issue a signed license key."""
    if not HAS_CRYPTO:  # cryptography library required
        print("[License] Install cryptography: pip install cryptography")  # installation instruction
        sys.exit(1)  # abort without dependency

    if tier not in TIERS:  # validate tier name
        print(f"[License] Unknown tier: {tier}. Options: {list(TIERS.keys())}")  # show valid tiers
        sys.exit(1)  # abort with invalid tier

    if machines is None:  # no machine count override
        machines = TIERS[tier]["machines"]  # use tier default machine limit

    payload = {  # construct license payload data
        "v": 1,  # license format version
        "tier": tier,  # license tier identifier
        "label": TIERS[tier]["label"],  # human-readable tier name
        "machines": machines,  # maximum allowed machines
        "customer": customer or hashlib.sha256(os.urandom(16)).hexdigest()[:12],  # customer ID or random hash
        "issued_at": int(time.time()),  # Unix timestamp of issuance
        "expires_at": None if perpetual else int(time.time() + days * 86400),  # expiry timestamp or None
    }

    if machine_ids is not None:  # machine-bound license requested
        payload["machine_ids"] = list(machine_ids)  # attach allowed machine fingerprints

    return _sign_and_encode(payload)  # sign and return formatted license key


def validate_license(key: str, pubkey_b64: str = "",
                     check_machine: bool = False) -> dict:  # verify license signature and constraints
    """
    Validate a license key. Returns the payload dict if valid.
    Raises ValueError if invalid.

    This function works fully offline — no network calls.
    """
    if not HAS_CRYPTO:  # cryptography library required
        raise ValueError("cryptography library not installed")

    clean = key.replace("KWYRE-", "", 1).replace("-", "").replace("\n", "").replace(" ", "")  # strip prefix, hyphens, whitespace

    try:
        token_json = base64.b64decode(clean)  # decode base64 outer wrapper
        token_data = json.loads(token_json)  # parse JSON token structure
    except Exception:
        raise ValueError("Malformed license key")  # base64 or JSON decode failed

    try:
        payload_bytes = base64.b64decode(token_data["p"])  # decode base64 payload
        signature = base64.b64decode(token_data["s"])  # decode base64 signature
    except Exception:
        raise ValueError("Malformed license key structure")  # inner decode failed

    pub = _load_public_key(pubkey_b64)  # load verification public key
    if pub is None:  # no public key available
        raise ValueError("No public key available for verification")

    try:
        pub.verify(signature, payload_bytes)  # verify Ed25519 signature against payload
    except InvalidSignature:
        raise ValueError("Invalid license signature — key is forged or corrupted")  # signature verification failed

    payload = json.loads(payload_bytes)  # deserialize verified payload

    if payload.get("expires_at") and payload["expires_at"] < time.time():  # check expiration timestamp
        raise ValueError(f"License expired on {time.strftime('%Y-%m-%d', time.localtime(payload['expires_at']))}")

    if check_machine and payload.get("machine_ids"):  # machine binding check requested
        current_fp = get_machine_fingerprint()  # compute current machine fingerprint
        if current_fp not in payload["machine_ids"]:  # machine not in allowed list
            raise ValueError("License not valid for this machine (fingerprint mismatch)")

    return payload  # return validated license payload


def startup_validate(key_source: str = None, pubkey_b64: str = "") -> dict:  # validate license at server boot
    """
    Validate license at server startup. Checks (in order):
      1. key_source argument
      2. KWYRE_LICENSE_KEY env var
      3. ./kwyre.license file
      4. ~/.kwyre/license file

    Returns the license payload if valid.
    Raises SystemExit if no valid license found.
    """
    key = key_source  # first priority: explicit key argument

    if not key:  # no key argument provided
        key = os.environ.get("KWYRE_LICENSE_KEY", "")  # try environment variable

    if not key:  # env var not set either
        for p in [Path("kwyre.license"), Path.home() / ".kwyre" / "license"]:  # check file locations
            if p.exists():  # license file found
                key = p.read_text().strip()  # read key from file
                break

    if not key:  # no license key found anywhere
        print("[License] No license key found.")  # inform user
        print("[License] Set KWYRE_LICENSE_KEY env var or place key in ./kwyre.license")  # suggest options
        print("[License] Purchase at https://kwyre.com")  # purchase link
        return None  # return None for missing license

    try:
        payload = validate_license(key, pubkey_b64=pubkey_b64, check_machine=True)  # validate with machine check
        print(f"[License] Valid — {payload['label']} ({payload['machines']} machine(s))")  # display license info
        if payload.get("expires_at"):  # license has expiration
            exp = time.strftime("%Y-%m-%d", time.localtime(payload["expires_at"]))  # format expiry date
            print(f"[License] Expires: {exp}")  # display expiry date
        else:
            print(f"[License] Perpetual license")  # no expiration
        return payload  # return validated payload
    except ValueError as e:  # validation failed
        print(f"[License] INVALID: {e}")  # display validation error
        return None  # return None for invalid license


def register_machine(key: str, fingerprint: str = None,
                     pubkey_b64: str = "") -> str:  # add machine to existing license
    """
    Add a machine fingerprint to an existing license and re-sign it.
    Requires the private key. If fingerprint is None, uses the current machine's.
    Returns the new license key string.
    """
    if not HAS_CRYPTO:  # cryptography library required
        raise ValueError("cryptography library not installed")

    if fingerprint is None:  # no fingerprint provided
        fingerprint = get_machine_fingerprint()  # use current machine's fingerprint

    payload = validate_license(key, pubkey_b64=pubkey_b64, check_machine=False)  # validate without machine check

    existing = payload.get("machine_ids", [])  # get currently bound machines
    if fingerprint in existing:  # machine already registered
        return key  # return original key unchanged

    max_machines = payload.get("machines", 1)  # get machine limit from payload
    if len(existing) >= max_machines:  # machine limit reached
        raise ValueError(
            f"Machine limit reached ({max_machines}). Cannot register additional machines."
        )

    payload["machine_ids"] = existing + [fingerprint]  # append new fingerprint to list
    return _sign_and_encode(payload)  # re-sign and return updated license key


def main():  # CLI entry point for license management
    parser = argparse.ArgumentParser(description="Kwyre License Key System")  # create CLI parser
    sub = parser.add_subparsers(dest="command")  # create subcommand parser group

    sub.add_parser("keygen", help="Generate Ed25519 signing keypair")  # keygen subcommand

    issue_p = sub.add_parser("issue", help="Issue a license key")  # issue subcommand
    issue_p.add_argument("--tier", required=True, choices=list(TIERS.keys()))  # required license tier
    issue_p.add_argument("--machines", type=int, default=None)  # optional machine count override
    issue_p.add_argument("--customer", default="")  # optional customer identifier
    issue_p.add_argument("--days", type=int, default=0, help="Expiry in days (0=perpetual)")  # expiry duration
    issue_p.add_argument("--out", default="", help="Write key to file")  # optional output file path
    issue_p.add_argument("--fingerprints", nargs="*", default=None,  # optional machine fingerprint binding
                         help="Bind license to specific machine fingerprints")

    val_p = sub.add_parser("validate", help="Validate a license key")  # validate subcommand
    val_p.add_argument("--key", default="")  # license key string input
    val_p.add_argument("--file", default="")  # license key file input

    fp_p = sub.add_parser("fingerprint", help="Show this machine's fingerprint")  # fingerprint subcommand

    bind_p = sub.add_parser("bind", help="Bind an existing license to machine fingerprints")  # bind subcommand
    bind_p.add_argument("--key", required=True, help="Existing license key")  # required existing key
    bind_p.add_argument("--fingerprints", nargs="+", required=True,  # required fingerprints to bind
                        help="Machine fingerprints to bind")

    args = parser.parse_args()  # parse command-line arguments

    if args.command == "keygen":  # generate signing keypair
        keygen()
    elif args.command == "issue":  # issue new license key
        perpetual = args.days == 0  # zero days means perpetual license
        key = issue_license(args.tier, args.machines, args.customer, perpetual, args.days,  # create signed key
                            machine_ids=args.fingerprints)
        print(f"\n{'='*60}")  # print header separator
        print(f"  License Key — {TIERS[args.tier]['label']}")  # display tier label
        print(f"{'='*60}\n")  # print footer separator
        print(key)  # output the license key
        print()
        if args.fingerprints:  # machine-bound license was issued
            print(f"Bound to {len(args.fingerprints)} machine(s): {', '.join(args.fingerprints)}")  # show bound machines
        if args.out:  # output file requested
            Path(args.out).write_text(key)  # write license key to file
            print(f"Written to {args.out}")  # confirm file write
    elif args.command == "validate":  # validate existing license key
        key = args.key  # use key from argument
        if args.file:  # key file provided instead
            key = Path(args.file).read_text().strip()  # read key from file
        if not key:  # no key source provided
            print("Provide --key or --file")  # prompt for key input
            sys.exit(1)  # abort without key
        try:
            payload = validate_license(key)  # validate the license key
            print(f"[License] VALID")  # confirm valid license
            print(json.dumps(payload, indent=2))  # display payload as formatted JSON
        except ValueError as e:  # validation failed
            print(f"[License] INVALID: {e}")  # display error message
            sys.exit(1)  # exit with error code
    elif args.command == "bind":  # bind license to machine fingerprints
        try:
            payload = validate_license(args.key, check_machine=False)  # validate without machine check
            payload["machine_ids"] = list(args.fingerprints)  # set new fingerprint list
            new_key = _sign_and_encode(payload)  # re-sign with updated fingerprints
            print(f"\n{'='*60}")  # print header separator
            print(f"  Re-issued License — bound to {len(args.fingerprints)} machine(s)")  # display binding info
            print(f"{'='*60}\n")  # print footer separator
            print(new_key)  # output the new license key
            print()
            print(f"Fingerprints: {', '.join(args.fingerprints)}")  # display bound fingerprints
        except ValueError as e:  # validation or signing failed
            print(f"[License] ERROR: {e}")  # display error message
            sys.exit(1)  # exit with error code
    elif args.command == "fingerprint":  # show current machine fingerprint
        print(f"Machine fingerprint: {get_machine_fingerprint()}")  # output fingerprint hash
    else:
        parser.print_help()  # no subcommand given, show usage


if __name__ == "__main__":  # only run when executed directly
    main()  # invoke CLI entry point
