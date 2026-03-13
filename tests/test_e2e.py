"""
Kwyre AI — End-to-End Test Suite
=================================
Comprehensive tests covering the full request lifecycle.
Skips automatically if the server is not running.

Run: python -m unittest tests.test_e2e -v
"""

import json
import time
import unittest
import urllib.request
import urllib.error
import os
import hashlib

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "sk-kwyre-dev-local"


def _server_available():
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=3)
        return True
    except:
        return False


def _request(method, path, body=None, auth=True, timeout=120):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode()
        try:
            return resp.status, json.loads(raw)
        except:
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except:
            return e.code, raw


# ── SERVER LIFECYCLE ──────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestServerHealth(unittest.TestCase):
    """Tests that the server is alive and reporting correct status."""

    def test_unauthenticated_health(self):
        status, data = _request("GET", "/health", auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertNotIn("security", data)

    def test_authenticated_health_has_security(self):
        status, data = _request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIn("security", data)
        sec = data["security"]
        self.assertIn("l1_network_binding", sec)
        self.assertIn("l5_conversation_storage", sec)
        self.assertIn("l6_intrusion_watchdog", sec)

    def test_health_watchdog_running(self):
        status, data = _request("GET", "/health")
        watchdog = data["security"]["l6_intrusion_watchdog"]
        self.assertTrue(watchdog["running"])
        self.assertFalse(watchdog["triggered"])

    def test_health_has_model_info(self):
        status, data = _request("GET", "/health")
        self.assertIn("model", data)

    def test_health_has_product_identity(self):
        status, data = _request("GET", "/health")
        self.assertIn("product", data)


# ── AUTHENTICATION ────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestAuthentication(unittest.TestCase):

    def test_valid_key_accepted(self):
        status, _ = _request("GET", "/v1/models")
        self.assertEqual(status, 200)

    def test_invalid_key_rejected(self):
        url = f"{BASE_URL}/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer sk-invalid"})
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_missing_key_rejected(self):
        status, _ = _request("GET", "/v1/models", auth=False)
        self.assertEqual(status, 401)

    def test_empty_bearer_rejected(self):
        url = f"{BASE_URL}/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer "})
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)


# ── MODEL ENDPOINT ────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestModelsEndpoint(unittest.TestCase):

    def test_models_list_format(self):
        status, data = _request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(data["object"], "list")
        self.assertGreater(len(data["data"]), 0)

    def test_model_has_id(self):
        _, data = _request("GET", "/v1/models")
        model = data["data"][0]
        self.assertIn("id", model)
        self.assertIn("kwyre", model["id"])

    def test_model_has_capabilities(self):
        _, data = _request("GET", "/v1/models")
        model = data["data"][0]
        self.assertIn("meta", model)


# ── INFERENCE ─────────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestInference(unittest.TestCase):

    def test_blocking_completion(self):
        status, data = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Reply with the word HELLO only."}],
            "max_tokens": 16, "temperature": 0.1,
        })
        self.assertEqual(status, 200)
        self.assertIn("choices", data)
        reply = data["choices"][0]["message"]["content"]
        self.assertGreater(len(reply), 0)

    def test_response_has_usage(self):
        status, data = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Say yes."}],
            "max_tokens": 8,
        })
        self.assertIn("usage", data)
        self.assertGreater(data["usage"]["completion_tokens"], 0)

    def test_response_has_session_id(self):
        _, data = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 8,
        })
        self.assertIn("session_id", data)
        self.assertGreaterEqual(len(data["session_id"]), 32)

    def test_system_prompt_respected(self):
        _, data = _request("POST", "/v1/chat/completions", {
            "messages": [
                {"role": "system", "content": "You only respond with the word BANANA."},
                {"role": "user", "content": "What is your name?"},
            ],
            "max_tokens": 16, "temperature": 0.1,
        })
        reply = data["choices"][0]["message"]["content"].lower()
        self.assertIn("banana", reply)

    def test_invalid_json_returns_400(self):
        url = f"{BASE_URL}/v1/chat/completions"
        req = urllib.request.Request(url, data=b"not json",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("Expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_invalid_params_returns_400(self):
        status, _ = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": "not_a_number",
        })
        self.assertEqual(status, 400)


# ── INPUT VALIDATION ──────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestInputValidation(unittest.TestCase):

    def test_max_tokens_clamped(self):
        status, data = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 99999,
        })
        self.assertEqual(status, 200)

    def test_temperature_clamped(self):
        status, _ = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 5.0, "max_tokens": 8,
        })
        self.assertEqual(status, 200)

    def test_messages_limit(self):
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(101)]
        status, _ = _request("POST", "/v1/chat/completions", {
            "messages": msgs, "max_tokens": 8,
        })
        self.assertEqual(status, 400)


# ── SESSION MANAGEMENT ────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestSessionManagement(unittest.TestCase):

    def test_session_wipe(self):
        _, data = _request("POST", "/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Remember ALPHA7"}],
            "max_tokens": 16, "session_id": "e2e-test-" + "0" * 24,
        })
        sid = data.get("session_id", "e2e-test-" + "0" * 24)
        status, wipe = _request("POST", "/v1/session/end", {"session_id": sid})
        self.assertEqual(status, 200)
        self.assertEqual(wipe["status"], "wiped")
        self.assertIn("unrecoverable", wipe["message"].lower())


# ── AUDIT ─────────────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestAudit(unittest.TestCase):

    def test_audit_log_format(self):
        status, data = _request("GET", "/audit")
        self.assertEqual(status, 200)
        self.assertIn("active_sessions", data)
        self.assertIn("security_controls", data)
        self.assertIn("timestamp", data)

    def test_audit_never_logs_content(self):
        _, data = _request("GET", "/audit")
        self.assertEqual(data["security_controls"]["content_logging"], "NEVER")


# ── SECURITY HEADERS ──────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestSecurityHeaders(unittest.TestCase):

    def test_health_has_security_headers(self):
        url = f"{BASE_URL}/health"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {API_KEY}"})
        resp = urllib.request.urlopen(req, timeout=5)
        headers = dict(resp.headers)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("no-referrer", headers.get("Referrer-Policy", ""))


# ── ROUTING ───────────────────────────────────────────────────────────────

@unittest.skipUnless(_server_available(), "Server not running")
class TestRouting(unittest.TestCase):

    def test_root_serves_html(self):
        url = f"{BASE_URL}/"
        resp = urllib.request.urlopen(url, timeout=5)
        self.assertEqual(resp.status, 200)
        content_type = resp.headers.get("Content-Type", "")
        self.assertIn("text/html", content_type)

    def test_chat_serves_html(self):
        url = f"{BASE_URL}/chat"
        resp = urllib.request.urlopen(url, timeout=5)
        self.assertEqual(resp.status, 200)

    def test_unknown_path_returns_404(self):
        try:
            urllib.request.urlopen(f"{BASE_URL}/nonexistent", timeout=5)
            self.fail("Expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_favicon_returns_204(self):
        url = f"{BASE_URL}/favicon.ico"
        resp = urllib.request.urlopen(url, timeout=5)
        self.assertEqual(resp.status, 204)


if __name__ == "__main__":
    unittest.main()
