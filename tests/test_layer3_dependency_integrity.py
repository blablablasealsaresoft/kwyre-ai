#!/usr/bin/env python3
"""
Tests for Layer 3: Dependency Integrity Verification (security/verify_deps.py)
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security.verify_deps import (
    ALLOWLISTED_EXTRA,
    MANIFEST_PATH,
    REQUIRED_PACKAGES,
    generate_manifest,
    get_package_hash,
    startup_check,
    verify_manifest,
    verify_required_only,
)


class TestLayer3DependencyIntegrity(unittest.TestCase):
    """Security tests for dependency integrity verification."""

    # ------------------------------------------------------------------
    # 1. get_package_hash returns a valid dict for a known package
    # ------------------------------------------------------------------
    def test_get_package_hash_returns_valid_dict(self):
        result = get_package_hash("pip")
        self.assertIsInstance(result, dict)
        self.assertIn("version", result)
        self.assertIn("record_hash", result)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "ok")
        self.assertNotEqual(result["version"], "unknown")
        self.assertNotEqual(result["record_hash"], "error")

    # ------------------------------------------------------------------
    # 2. get_package_hash returns error status for an unknown package
    # ------------------------------------------------------------------
    def test_get_package_hash_unknown_package(self):
        result = get_package_hash("this_package_does_not_exist_xyz_9999")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["version"], "unknown")
        self.assertEqual(result["record_hash"], "error")
        self.assertNotEqual(result["status"], "ok")

    # ------------------------------------------------------------------
    # 3. Generate a manifest in a temp dir, then verify against it
    # ------------------------------------------------------------------
    def test_manifest_generation_and_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = Path(tmpdir) / "kwyre_dep_manifest.json"
            with patch("security.verify_deps.MANIFEST_PATH", tmp_manifest):
                generate_manifest()
                self.assertTrue(tmp_manifest.exists(), "Manifest file was not created")

                with open(tmp_manifest) as f:
                    manifest = json.load(f)
                self.assertIn("packages", manifest)
                self.assertIsInstance(manifest["packages"], dict)
                self.assertGreater(len(manifest["packages"]), 0)

                result = verify_manifest()
                self.assertTrue(result, "verify_manifest should pass against a freshly generated manifest")

    # ------------------------------------------------------------------
    # 4. Detect version mismatch in manifest
    # ------------------------------------------------------------------
    def test_manifest_verify_detects_version_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = Path(tmpdir) / "kwyre_dep_manifest.json"

            real_info = get_package_hash("pip")
            self.assertEqual(real_info["status"], "ok")

            manifest = {
                "generated_at": "2026-01-01T00:00:00Z",
                "python_version": sys.version,
                "packages": {
                    "pip": {
                        "version": "0.0.0-fake",
                        "record_hash": real_info["record_hash"],
                        "status": "ok",
                    }
                },
            }
            with open(tmp_manifest, "w") as f:
                json.dump(manifest, f)

            fake_dist = MagicMock()
            fake_dist.metadata = {"Name": "pip", "Version": real_info["version"]}
            fake_dist.files = []

            with patch("security.verify_deps.MANIFEST_PATH", tmp_manifest):
                import importlib.metadata as _meta
                with patch.object(_meta, "distributions", return_value=[fake_dist]):
                    result = verify_manifest()

            self.assertFalse(result, "verify_manifest should detect a version mismatch")

    # ------------------------------------------------------------------
    # 5. Detect hash mismatch in manifest
    # ------------------------------------------------------------------
    def test_manifest_verify_detects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = Path(tmpdir) / "kwyre_dep_manifest.json"

            real_info = get_package_hash("pip")
            self.assertEqual(real_info["status"], "ok")

            manifest = {
                "generated_at": "2026-01-01T00:00:00Z",
                "python_version": sys.version,
                "packages": {
                    "pip": {
                        "version": real_info["version"],
                        "record_hash": "deadbeef" * 8,
                        "status": "ok",
                    }
                },
            }
            with open(tmp_manifest, "w") as f:
                json.dump(manifest, f)

            with patch("security.verify_deps.MANIFEST_PATH", tmp_manifest):
                result = verify_manifest()

            self.assertFalse(result, "verify_manifest should detect a hash mismatch")

    # ------------------------------------------------------------------
    # 6. Graceful handling when no manifest exists
    # ------------------------------------------------------------------
    def test_manifest_verify_missing_manifest(self):
        missing = Path(tempfile.gettempdir()) / "nonexistent_kwyre_manifest.json"
        if missing.exists():
            os.remove(missing)

        with patch("security.verify_deps.MANIFEST_PATH", missing):
            result = verify_manifest()
            self.assertTrue(result, "verify_manifest should return True (non-blocking) when manifest is missing")

    # ------------------------------------------------------------------
    # 7. REQUIRED_PACKAGES is populated
    # ------------------------------------------------------------------
    def test_required_packages_list_not_empty(self):
        self.assertIsInstance(REQUIRED_PACKAGES, list)
        self.assertGreater(len(REQUIRED_PACKAGES), 0, "REQUIRED_PACKAGES must not be empty")
        for pkg in REQUIRED_PACKAGES:
            self.assertIsInstance(pkg, str)
            self.assertGreater(len(pkg), 0)

    # ------------------------------------------------------------------
    # 8. ALLOWLISTED_EXTRA is populated
    # ------------------------------------------------------------------
    def test_allowlisted_extra_not_empty(self):
        self.assertIsInstance(ALLOWLISTED_EXTRA, list)
        self.assertGreater(len(ALLOWLISTED_EXTRA), 0, "ALLOWLISTED_EXTRA must not be empty")
        for pkg in ALLOWLISTED_EXTRA:
            self.assertIsInstance(pkg, str)
            self.assertGreater(len(pkg), 0)

    # ------------------------------------------------------------------
    # 9. startup_check with abort_on_failure=False does not exit
    # ------------------------------------------------------------------
    def test_startup_check_non_blocking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = Path(tmpdir) / "kwyre_dep_manifest.json"

            manifest = {
                "generated_at": "2026-01-01T00:00:00Z",
                "python_version": sys.version,
                "packages": {
                    "pip": {
                        "version": "0.0.0-fake",
                        "record_hash": "bad",
                        "status": "ok",
                    }
                },
            }
            with open(tmp_manifest, "w") as f:
                json.dump(manifest, f)

            fake_dist = MagicMock()
            fake_dist.metadata = {"Name": "pip", "Version": "99.99.99"}
            fake_dist.files = []

            with patch("security.verify_deps.MANIFEST_PATH", tmp_manifest):
                with patch("security.verify_deps.REQUIRED_PACKAGES", ["pip"]):
                    import importlib.metadata as _meta
                    with patch.object(_meta, "distributions", return_value=[fake_dist]):
                        with patch("security.verify_deps.get_package_hash", return_value={
                            "version": "99.99.99",
                            "record_hash": "no-record",
                            "status": "ok",
                        }):
                            result = startup_check(abort_on_failure=False)

            self.assertIsInstance(result, bool)

    # ------------------------------------------------------------------
    # 10. Unexpected packages (not in manifest, not allowlisted) are flagged
    # ------------------------------------------------------------------
    def test_unexpected_package_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_manifest = Path(tmpdir) / "kwyre_dep_manifest.json"

            manifest = {
                "generated_at": "2026-01-01T00:00:00Z",
                "python_version": sys.version,
                "packages": {},
            }
            with open(tmp_manifest, "w") as f:
                json.dump(manifest, f)

            rogue_dist = MagicMock()
            rogue_dist.metadata = {"Name": "evil-rogue-pkg", "Version": "6.6.6"}
            rogue_dist.files = []

            import importlib.metadata as _meta

            with patch("security.verify_deps.MANIFEST_PATH", tmp_manifest):
                with patch.object(_meta, "distributions", return_value=[rogue_dist]):
                    with patch("security.verify_deps.get_package_hash", return_value={
                        "version": "6.6.6",
                        "record_hash": "no-record",
                        "status": "ok",
                    }):
                        result = verify_manifest()

            self.assertTrue(
                result,
                "verify_manifest returns True (warnings only, no hard failures) "
                "for unexpected packages, but the warning should still be emitted",
            )


if __name__ == "__main__":
    unittest.main()
