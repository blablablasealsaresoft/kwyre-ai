#!/usr/bin/env python3
"""
Kwyre AI — Air-Gap Safe Update System
======================================
Offline-only update mechanism for air-gapped deployments.

The updater NEVER makes network requests. Users manually download update
packages from kwyre.com (or receive them on USB) and place them in a known
directory. The updater detects, verifies (Ed25519 + SHA-256), and applies them.

Update package format (.kwyre-update):
  A ZIP archive containing:
    - MANIFEST.sig.json  — Ed25519-signed manifest
    - update.json        — version metadata + changelog + file list
    - <files>            — the actual updated files

CLI:
    python updater.py check
    python updater.py verify  --package path/to/update.kwyre-update
    python updater.py apply   --package path/to/update.kwyre-update --dir /opt/kwyre
    python updater.py rollback --dir /opt/kwyre
    python updater.py create  --source build/kwyre-dist --version 1.1.0 \\
                              --changelog "Bug fixes" --output kwyre-1.1.0.kwyre-update
    python updater.py version

Server integration (serve_local_4bit.py):
    A /v1/update/check endpoint could call KwyreUpdater.check_for_update()
    and return the list of available packages as JSON. The server would NOT
    download anything — it only reports what .kwyre-update files are already
    present on disk so the chat UI can prompt the operator.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
        load_pem_private_key,
        load_pem_public_key,
        load_der_public_key,
    )
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

KEYS_DIR = Path(__file__).parent / ".keys"

EMBEDDED_PUBLIC_KEY = ""

UPDATE_EXTENSION = ".kwyre-update"

DEFAULT_SEARCH_DIRS = [
    Path.cwd(),
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / ".kwyre" / "updates",
]


@dataclass
class UpdateInfo:
    version: str
    changelog: str
    files_changed: List[str]
    min_version: str
    verified: bool
    package_path: str
    signed_at: str = ""


@dataclass
class UpdatePackage:
    path: str
    version: str
    changelog: str = ""
    min_version: str = "0.0.0"


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_private_key():
    key_path = KEYS_DIR / "kwyre_signing.key"
    if not key_path.exists():
        raise FileNotFoundError(
            f"Private key not found at {key_path}. Run: python license.py keygen"
        )
    with open(key_path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _load_public_key(pubkey_b64: str = ""):
    import base64

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


class KwyreUpdater:

    def check_for_update(self, search_dirs: List[str] = None) -> List[UpdatePackage]:
        dirs = list(DEFAULT_SEARCH_DIRS)
        if search_dirs:
            dirs.extend(Path(d) for d in search_dirs)

        seen = set()
        packages = []

        for d in dirs:
            if not d.is_dir():
                continue
            for entry in d.iterdir():
                if not entry.name.endswith(UPDATE_EXTENSION):
                    continue
                real = str(entry.resolve())
                if real in seen:
                    continue
                seen.add(real)

                try:
                    meta = self._read_update_meta(str(entry))
                    packages.append(UpdatePackage(
                        path=real,
                        version=meta.get("version", "0.0.0"),
                        changelog=meta.get("changelog", ""),
                        min_version=meta.get("min_version", "0.0.0"),
                    ))
                except Exception:
                    continue

        packages.sort(key=lambda p: _version_tuple(p.version), reverse=True)
        return packages

    def verify_update(self, package_path: str) -> UpdateInfo:
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography library not installed")

        package_path = str(Path(package_path).resolve())

        if not zipfile.is_zipfile(package_path):
            raise ValueError(f"Not a valid ZIP archive: {package_path}")

        with zipfile.ZipFile(package_path, "r") as zf:
            names = zf.namelist()

            if "MANIFEST.sig.json" not in names:
                raise ValueError("Missing MANIFEST.sig.json in update package")
            if "update.json" not in names:
                raise ValueError("Missing update.json in update package")

            import base64

            manifest_raw = zf.read("MANIFEST.sig.json")
            manifest_envelope = json.loads(manifest_raw)

            payload_bytes = base64.b64decode(manifest_envelope["payload"])
            signature = base64.b64decode(manifest_envelope["signature"])

            pub = _load_public_key()
            if pub is None:
                raise ValueError("No public key available for verification")

            try:
                pub.verify(signature, payload_bytes)
            except InvalidSignature:
                return UpdateInfo(
                    version="",
                    changelog="",
                    files_changed=[],
                    min_version="",
                    verified=False,
                    package_path=package_path,
                )

            manifest = json.loads(payload_bytes)
            file_hashes = manifest.get("files", {})

            for fname, expected_hash in file_hashes.items():
                if fname in ("MANIFEST.sig.json", "update.json"):
                    continue
                if fname not in names:
                    raise ValueError(f"Manifest references missing file: {fname}")
                actual_hash = _sha256_bytes(zf.read(fname))
                if actual_hash != expected_hash:
                    raise ValueError(
                        f"Hash mismatch for {fname}: expected {expected_hash}, got {actual_hash}"
                    )

            update_meta = json.loads(zf.read("update.json"))

            return UpdateInfo(
                version=update_meta.get("version", ""),
                changelog=update_meta.get("changelog", ""),
                files_changed=list(file_hashes.keys()),
                min_version=update_meta.get("min_version", "0.0.0"),
                verified=True,
                package_path=package_path,
                signed_at=manifest.get("signed_at", ""),
            )

    def apply_update(self, package_path: str, install_dir: str) -> bool:
        info = self.verify_update(package_path)
        if not info.verified:
            raise ValueError("Update package failed signature verification")

        install_dir = str(Path(install_dir).resolve())
        current_version = get_current_version(install_dir)

        if info.min_version and _version_tuple(current_version) < _version_tuple(info.min_version):
            raise ValueError(
                f"Current version {current_version} is below minimum required "
                f"{info.min_version} for this update"
            )

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(install_dir, f".backup-{timestamp}")

        try:
            os.makedirs(backup_dir, exist_ok=True)

            with zipfile.ZipFile(package_path, "r") as zf:
                for fname in info.files_changed:
                    if fname in ("MANIFEST.sig.json", "update.json"):
                        continue
                    dest = os.path.join(install_dir, fname)
                    if os.path.exists(dest):
                        backup_dest = os.path.join(backup_dir, fname)
                        os.makedirs(os.path.dirname(backup_dest), exist_ok=True)
                        shutil.copy2(dest, backup_dest)

            version_json_path = os.path.join(install_dir, "version.json")
            if os.path.exists(version_json_path):
                shutil.copy2(version_json_path, os.path.join(backup_dir, "version.json"))

            with zipfile.ZipFile(package_path, "r") as zf:
                for fname in info.files_changed:
                    if fname in ("MANIFEST.sig.json", "update.json"):
                        continue
                    dest = os.path.join(install_dir, fname)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(fname) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            _update_version_json(install_dir, info.version, current_version)
            return True

        except Exception:
            try:
                self._restore_backup(backup_dir, install_dir)
            except Exception:
                pass
            raise

    def rollback(self, install_dir: str) -> bool:
        install_dir = str(Path(install_dir).resolve())

        backups = sorted(
            (
                entry for entry in Path(install_dir).iterdir()
                if entry.is_dir() and entry.name.startswith(".backup-")
            ),
            key=lambda p: p.name,
            reverse=True,
        )

        if not backups:
            raise FileNotFoundError(f"No backups found in {install_dir}")

        latest_backup = str(backups[0])
        self._restore_backup(latest_backup, install_dir)
        return True

    def create_update_package(
        self,
        source_dir: str,
        version: str,
        changelog: str,
        output_path: str,
        min_version: str = "0.0.0",
    ) -> str:
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography library not installed")

        source_dir = str(Path(source_dir).resolve())
        output_path = str(Path(output_path).resolve())

        if not output_path.endswith(UPDATE_EXTENSION):
            output_path += UPDATE_EXTENSION

        file_hashes = {}
        file_list = []
        for root, _dirs, files in os.walk(source_dir):
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, source_dir).replace("\\", "/")
                file_hashes[rel] = _sha256_file(full)
                file_list.append(rel)

        update_meta = {
            "version": version,
            "changelog": changelog,
            "min_version": min_version,
            "files_changed": sorted(file_list),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        manifest_payload = {
            "version": version,
            "files": file_hashes,
            "signed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        import base64

        payload_bytes = json.dumps(
            manifest_payload, separators=(",", ":"), sort_keys=True
        ).encode()

        priv = _load_private_key()
        signature = priv.sign(payload_bytes)

        manifest_envelope = {
            "payload": base64.b64encode(payload_bytes).decode(),
            "signature": base64.b64encode(signature).decode(),
        }

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "MANIFEST.sig.json",
                json.dumps(manifest_envelope, indent=2),
            )
            zf.writestr(
                "update.json",
                json.dumps(update_meta, indent=2),
            )
            for rel in sorted(file_list):
                full = os.path.join(source_dir, rel)
                zf.write(full, rel)

        return output_path

    def _read_update_meta(self, package_path: str) -> dict:
        with zipfile.ZipFile(package_path, "r") as zf:
            if "update.json" not in zf.namelist():
                raise ValueError("No update.json in package")
            return json.loads(zf.read("update.json"))

    def _restore_backup(self, backup_dir: str, install_dir: str):
        for root, _dirs, files in os.walk(backup_dir):
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, backup_dir)
                dest = os.path.join(install_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)


def get_current_version(install_dir: str) -> str:
    version_path = os.path.join(install_dir, "version.json")
    if not os.path.exists(version_path):
        return "0.0.0"
    try:
        with open(version_path, "r") as f:
            data = json.load(f)
        return data.get("version", "0.0.0")
    except (json.JSONDecodeError, OSError):
        return "0.0.0"


def _update_version_json(install_dir: str, new_version: str, old_version: str):
    version_path = os.path.join(install_dir, "version.json")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    data = {
        "version": new_version,
        "installed_at": now,
        "updated_at": now,
        "update_history": [],
    }

    if os.path.exists(version_path):
        try:
            with open(version_path, "r") as f:
                existing = json.load(f)
            data["installed_at"] = existing.get("installed_at", now)
            data["update_history"] = existing.get("update_history", [])
        except (json.JSONDecodeError, OSError):
            pass

    data["version"] = new_version
    data["updated_at"] = now
    data["update_history"].append({
        "from_version": old_version,
        "to_version": new_version,
        "applied_at": now,
    })

    with open(version_path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Kwyre AI — Air-Gap Safe Updater")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="Scan for available .kwyre-update packages")

    verify_p = sub.add_parser("verify", help="Verify update package integrity")
    verify_p.add_argument("--package", required=True, help="Path to .kwyre-update file")

    apply_p = sub.add_parser("apply", help="Apply an update package")
    apply_p.add_argument("--package", required=True, help="Path to .kwyre-update file")
    apply_p.add_argument("--dir", required=True, help="Kwyre installation directory")

    rollback_p = sub.add_parser("rollback", help="Rollback to previous version")
    rollback_p.add_argument("--dir", required=True, help="Kwyre installation directory")

    create_p = sub.add_parser("create", help="Create an update package")
    create_p.add_argument("--source", required=True, help="Source distribution directory")
    create_p.add_argument("--version", required=True, help="Version string (e.g. 1.1.0)")
    create_p.add_argument("--changelog", default="", help="Changelog text")
    create_p.add_argument("--output", required=True, help="Output .kwyre-update path")
    create_p.add_argument("--min-version", default="0.0.0", help="Minimum installed version required")

    sub.add_parser("version", help="Show current installed version")

    args = parser.parse_args()
    updater = KwyreUpdater()

    if args.command == "check":
        packages = updater.check_for_update()
        if not packages:
            print("[Updater] No update packages found.")
            print("[Updater] Place .kwyre-update files in ~/Downloads, ~/Desktop, or ~/.kwyre/updates/")
        else:
            print(f"[Updater] Found {len(packages)} update package(s):\n")
            for pkg in packages:
                print(f"  v{pkg.version}  {pkg.path}")
                if pkg.changelog:
                    print(f"           {pkg.changelog}")

    elif args.command == "verify":
        try:
            info = updater.verify_update(args.package)
            if info.verified:
                print(f"[Updater] VERIFIED — v{info.version}")
                print(f"  Changelog:     {info.changelog}")
                print(f"  Min version:   {info.min_version}")
                print(f"  Files changed: {len(info.files_changed)}")
                print(f"  Signed at:     {info.signed_at}")
                for fname in sorted(info.files_changed):
                    print(f"    {fname}")
            else:
                print("[Updater] FAILED — Signature verification failed.")
                sys.exit(1)
        except (ValueError, RuntimeError) as e:
            print(f"[Updater] FAILED — {e}")
            sys.exit(1)

    elif args.command == "apply":
        try:
            info = updater.verify_update(args.package)
            if not info.verified:
                print("[Updater] Refusing to apply: signature verification failed.")
                sys.exit(1)

            current = get_current_version(args.dir)
            print(f"[Updater] Current version: {current}")
            print(f"[Updater] Update version:  {info.version}")
            print(f"[Updater] Files to update: {len(info.files_changed)}")

            success = updater.apply_update(args.package, args.dir)
            if success:
                print(f"[Updater] Update applied successfully. Now at v{info.version}")
            else:
                print("[Updater] Update failed.")
                sys.exit(1)
        except (ValueError, RuntimeError) as e:
            print(f"[Updater] FAILED — {e}")
            sys.exit(1)

    elif args.command == "rollback":
        try:
            success = updater.rollback(args.dir)
            if success:
                new_ver = get_current_version(args.dir)
                print(f"[Updater] Rolled back. Now at v{new_ver}")
        except FileNotFoundError as e:
            print(f"[Updater] {e}")
            sys.exit(1)

    elif args.command == "create":
        try:
            out = updater.create_update_package(
                source_dir=args.source,
                version=args.version,
                changelog=args.changelog,
                output_path=args.output,
                min_version=args.min_version,
            )
            size_mb = os.path.getsize(out) / (1024 * 1024)
            print(f"[Updater] Package created: {out} ({size_mb:.1f} MB)")
        except (RuntimeError, FileNotFoundError) as e:
            print(f"[Updater] FAILED — {e}")
            sys.exit(1)

    elif args.command == "version":
        install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version = get_current_version(install_dir)
        print(f"Kwyre AI v{version}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
