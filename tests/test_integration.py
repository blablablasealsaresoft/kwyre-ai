"""
Kwyre AI — Integration Tests
=============================
Tests against a running Kwyre server at http://127.0.0.1:8000.
Skips automatically if the server is not running.

Run:
    python -m unittest tests.test_integration -v
"""

import json
import time
import unittest
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "sk-kwyre-dev-local"


def _server_available() -> bool:
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=3)
        return True
    except Exception:
        return False


def _request(method: str, path: str, body: dict | None = None,
             auth: bool = True, timeout: int = 120) -> tuple[int, dict | str]:
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
        except json.JSONDecodeError:
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _stream_request(path: str, body: dict, timeout: int = 120) -> tuple[list[dict], str]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=timeout)

    events = []
    full_text = ""
    for line in resp:
        line = line.decode().strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            events.append(chunk)
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            full_text += delta
        except json.JSONDecodeError:
            pass

    return events, full_text


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestHealthEndpoint(unittest.TestCase):

    def test_health_unauthenticated(self):
        status, data = _request("GET", "/health", auth=False)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertNotIn("model", data)

    def test_health_authenticated(self):
        status, data = _request("GET", "/health", auth=True)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertIn("model", data)
        self.assertIn("security", data)
        security = data["security"]
        self.assertIn("l1_network_binding", security)
        self.assertIn("l5_conversation_storage", security)
        self.assertIn("l6_intrusion_watchdog", security)
        watchdog = security["l6_intrusion_watchdog"]
        self.assertTrue(watchdog["running"])
        self.assertFalse(watchdog["triggered"])


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestModelsEndpoint(unittest.TestCase):

    def test_models_list(self):
        status, data = _request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(data["object"], "list")
        self.assertGreater(len(data["data"]), 0)
        model = data["data"][0]
        self.assertIn("id", model)
        self.assertEqual(model["object"], "model")
        self.assertEqual(model["owned_by"], "kwyre")


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestAuthErrors(unittest.TestCase):

    def test_invalid_api_key(self):
        status, data = _request("GET", "/v1/models", auth=False)
        headers = {"Authorization": "Bearer sk-invalid-key-xxx"}
        url = f"{BASE_URL}/v1/models"
        req = urllib.request.Request(url, headers=headers)
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_missing_auth_header(self):
        status, data = _request("GET", "/v1/models", auth=False)
        self.assertEqual(status, 401)


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestBlockingInference(unittest.TestCase):

    def test_basic_completion(self):
        status, data = _request("POST", "/v1/chat/completions", body={
            "messages": [{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            "max_tokens": 16,
            "temperature": 0.1,
        })
        self.assertEqual(status, 200)
        self.assertIn("choices", data)
        self.assertEqual(len(data["choices"]), 1)
        reply = data["choices"][0]["message"]["content"]
        self.assertIn("4", reply)
        self.assertIn("model", data)
        self.assertIn("session_id", data)
        self.assertIn("usage", data)
        self.assertGreater(data["usage"]["completion_tokens"], 0)

    def test_invalid_json(self):
        url = f"{BASE_URL}/v1/chat/completions"
        req = urllib.request.Request(url, data=b"not json",
                                      headers={"Content-Type": "application/json",
                                                "Authorization": f"Bearer {API_KEY}"},
                                      method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("Expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_empty_messages(self):
        status, data = _request("POST", "/v1/chat/completions", body={
            "messages": [],
            "max_tokens": 16,
        })
        self.assertEqual(status, 200)

    def test_parameter_validation(self):
        status, data = _request("POST", "/v1/chat/completions", body={
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": "not_a_number",
        })
        self.assertEqual(status, 400)


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestStreamingInference(unittest.TestCase):

    def test_sse_format(self):
        events, full_text = _stream_request("/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Say hello in exactly one word."}],
            "max_tokens": 16,
            "temperature": 0.1,
            "stream": True,
        })
        self.assertGreater(len(events), 0, "Expected at least one SSE event")

        for event in events[:-1]:
            self.assertIn("choices", event)
            delta = event["choices"][0].get("delta", {})
            self.assertIn("content", delta)

        last = events[-1]
        self.assertEqual(last["choices"][0].get("finish_reason"), "stop")

        self.assertGreater(len(full_text.strip()), 0, "Expected non-empty response text")

    def test_stream_has_usage(self):
        events, _ = _stream_request("/v1/chat/completions", {
            "messages": [{"role": "user", "content": "Say yes."}],
            "max_tokens": 8,
            "temperature": 0.1,
            "stream": True,
        })
        last = events[-1]
        self.assertIn("usage", last)
        self.assertGreater(last["usage"]["completion_tokens"], 0)
        self.assertGreater(last["usage"]["tokens_per_second"], 0)


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestSessionWipe(unittest.TestCase):

    def test_wipe_session(self):
        status, data = _request("POST", "/v1/chat/completions", body={
            "messages": [{"role": "user", "content": "Remember: the code is ALPHA7."}],
            "max_tokens": 16,
            "session_id": "a" * 32,
        })
        self.assertEqual(status, 200)
        sid = data.get("session_id", "a" * 32)

        status, data = _request("POST", "/v1/session/end", body={"session_id": sid})
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "wiped")
        self.assertIn("unrecoverable", data["message"].lower())


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestAuditEndpoint(unittest.TestCase):

    def test_audit_log(self):
        status, data = _request("GET", "/audit")
        self.assertEqual(status, 200)
        self.assertIn("active_sessions", data)
        self.assertIn("security_controls", data)
        self.assertIn("timestamp", data)
        controls = data["security_controls"]
        self.assertEqual(controls["content_logging"], "NEVER")


@unittest.skipUnless(_server_available(), "Kwyre server not running at 127.0.0.1:8000")
class TestKVCache(unittest.TestCase):

    def test_multi_turn_uses_cache(self):
        sid = "kvcache" + "0" * 25
        _request("POST", "/v1/session/end", body={"session_id": sid})
        time.sleep(0.5)

        t0 = time.time()
        status1, data1 = _request("POST", "/v1/chat/completions", body={
            "messages": [{"role": "user", "content": "The secret project name is ZEPHYR. Acknowledge."}],
            "max_tokens": 32,
            "temperature": 0.1,
            "session_id": sid,
        })
        first_time = time.time() - t0
        self.assertEqual(status1, 200)

        t0 = time.time()
        status2, data2 = _request("POST", "/v1/chat/completions", body={
            "messages": [
                {"role": "user", "content": "The secret project name is ZEPHYR. Acknowledge."},
                {"role": "assistant", "content": data1["choices"][0]["message"]["content"]},
                {"role": "user", "content": "What was the project name I mentioned?"},
            ],
            "max_tokens": 32,
            "temperature": 0.1,
            "session_id": sid,
        })
        second_time = time.time() - t0
        self.assertEqual(status2, 200)

        status, health = _request("GET", "/health")
        kv = health.get("kv_cache", {})
        self.assertGreater(kv.get("cached_sessions", 0), 0,
                          "Expected at least one cached KV session")

        _request("POST", "/v1/session/end", body={"session_id": sid})


if __name__ == "__main__":
    unittest.main()
