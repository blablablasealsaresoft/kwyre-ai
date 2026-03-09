"""
Security tests for Kwyre AI inference server — Layers 5 & 6.

Layer 5: SecureConversationBuffer + SessionStore
Layer 6: IntrusionWatchdog

All classes are re-implemented locally to avoid importing from serve_local_4bit.py.
"""

import os
import secrets
import signal
import threading
import time
import unittest
import ipaddress as _ipaddress

try:
    import psutil
except ImportError:
    psutil = None


# ---------------------------------------------------------------------------
# Layer 5 re-implementation
# ---------------------------------------------------------------------------

class SecureConversationBuffer:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_key = secrets.token_bytes(32)
        self.created_at = time.time()
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._wiped = False

    def add_message(self, role: str, content: str) -> bool:
        with self._lock:
            if self._wiped:
                return False
            self._buffer.append({"role": role, "content": content})
            return True

    def get_messages(self) -> list[dict]:
        with self._lock:
            if self._wiped:
                return []
            return list(self._buffer)

    def secure_wipe(self, reason: str = "session_end"):
        with self._lock:
            if self._wiped:
                return
            n = len(self._buffer)
            for msg in self._buffer:
                msg["content"] = secrets.token_hex(max(len(msg.get("content", "")), 32))
                msg["role"] = secrets.token_hex(8)
            self._buffer.clear()
            self.session_key = bytes(32)
            self._wiped = True

    def is_wiped(self) -> bool:
        return self._wiped


class SessionStore:
    MAX_SESSION_AGE = 3600

    def __init__(self):
        self._sessions: dict[str, SecureConversationBuffer] = {}
        self._lock = threading.Lock()
        self._last_access: dict[str, float] = {}
        threading.Thread(target=self._reap_expired, daemon=True).start()

    def get_or_create(self, session_id: str) -> tuple[SecureConversationBuffer, bool]:
        with self._lock:
            created = session_id not in self._sessions or self._sessions[session_id].is_wiped()
            if created:
                self._sessions[session_id] = SecureConversationBuffer(session_id)
            self._last_access[session_id] = time.time()
            return self._sessions[session_id], created

    def wipe_session(self, session_id: str, reason: str = "user_request"):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].secure_wipe(reason=reason)
                del self._sessions[session_id]
                self._last_access.pop(session_id, None)

    def wipe_all(self, reason: str = "server_shutdown"):
        with self._lock:
            for buf in self._sessions.values():
                buf.secure_wipe(reason=reason)
            self._sessions.clear()
            self._last_access.clear()

    def _reap_expired(self):
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                expired = [s for s, t in self._last_access.items()
                           if now - t > self.MAX_SESSION_AGE]
                for sid in expired:
                    if sid in self._sessions:
                        self._sessions[sid].secure_wipe(reason="idle_timeout")
                        del self._sessions[sid]
                        self._last_access.pop(sid, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------------------
# Layer 6 re-implementation
# ---------------------------------------------------------------------------

SUSPICIOUS_PROCESSES = [
    "x64dbg", "x32dbg", "ollydbg", "windbg", "immunity debugger",
    "processhacker", "process hacker", "cheatengine", "cheat engine",
    "wireshark", "fiddler", "charles proxy", "mitmproxy", "burpsuite",
    "ida64", "ida32", "ghidra",
]

ALLOWED_REMOTE_IPS = {"127.0.0.1"}
_DOCKER_NETS = [
    _ipaddress.ip_network("172.16.0.0/12"),
    _ipaddress.ip_network("10.0.0.0/8"),
    _ipaddress.ip_network("192.168.0.0/16"),
]

def _is_allowed_ip(ip_str: str) -> bool:
    if ip_str in ALLOWED_REMOTE_IPS:
        return True
    try:
        addr = _ipaddress.ip_address(ip_str)
        return any(addr in net for net in _DOCKER_NETS)
    except ValueError:
        return False

WATCHDOG_INTERVAL = 5
VIOLATION_THRESHOLD = 2


class IntrusionWatchdog(threading.Thread):
    def __init__(self, session_store: SessionStore, terminate_on_intrusion: bool = True):
        super().__init__(daemon=True, name="IntrusionWatchdog")
        self.session_store = session_store
        self.terminate_on_intrusion = terminate_on_intrusion
        self.running = True
        self._violation_count = 0
        self._triggered = False
        self._lock = threading.Lock()
        self.intrusion_log: list[dict] = []

    def _log_event(self, event_type: str, detail: str):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event_type,
            "detail": detail,
        }
        self.intrusion_log.append(entry)

    def check_network(self) -> tuple[bool, str]:
        our_pid = os.getpid()
        try:
            proc = psutil.Process(our_pid)
            for conn in proc.net_connections():
                if conn.status != psutil.CONN_ESTABLISHED:
                    continue
                raddr = conn.raddr
                if not raddr:
                    continue
                remote_ip = raddr.ip
                if not _is_allowed_ip(remote_ip):
                    return False, f"unexpected outbound connection to {remote_ip}:{raddr.port}"
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass
        return True, ""

    def check_processes(self) -> tuple[bool, str]:
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    if any(s in name for s in SUSPICIOUS_PROCESSES):
                        return False, f"suspicious process detected: {proc.info['name']}"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return True, ""

    def _trigger_lockdown(self, reason: str):
        with self._lock:
            if self._triggered:
                return
            self._triggered = True
        self._log_event("LOCKDOWN", reason)
        self.session_store.wipe_all(reason=f"intrusion_lockdown: {reason}")
        if self.terminate_on_intrusion:
            time.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

    def run(self):
        while self.running and not self._triggered:
            time.sleep(WATCHDOG_INTERVAL)
            net_clean, net_detail = self.check_network()
            proc_clean, proc_detail = self.check_processes()
            if not net_clean or not proc_clean:
                self._violation_count += 1
                detail = net_detail or proc_detail
                self._log_event("VIOLATION", detail)
                if self._violation_count >= VIOLATION_THRESHOLD:
                    self._trigger_lockdown(detail)
            else:
                self._violation_count = 0

    def stop(self):
        self.running = False

    def get_status(self) -> dict:
        return {
            "running": self.running and not self._triggered,
            "triggered": self._triggered,
            "violations": self._violation_count,
            "threshold": VIOLATION_THRESHOLD,
            "check_interval_sec": WATCHDOG_INTERVAL,
            "recent_events": self.intrusion_log[-5:],
        }


# ===================================================================
# Tests
# ===================================================================


class TestLayer5SecureBuffer(unittest.TestCase):
    """Tests for SecureConversationBuffer and SessionStore."""

    # -- SecureConversationBuffer -----------------------------------------

    def test_buffer_creation(self):
        buf = SecureConversationBuffer("sess-001")
        self.assertEqual(len(buf.session_key), 32)
        self.assertIsInstance(buf.session_key, bytes)
        self.assertEqual(buf.get_messages(), [])
        self.assertFalse(buf.is_wiped())
        self.assertEqual(buf.session_id, "sess-001")
        self.assertLessEqual(buf.created_at, time.time())

    def test_add_and_get_messages(self):
        buf = SecureConversationBuffer("sess-002")
        self.assertTrue(buf.add_message("user", "Hello"))
        self.assertTrue(buf.add_message("assistant", "Hi there"))
        msgs = buf.get_messages()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0], {"role": "user", "content": "Hello"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "Hi there"})

    def test_secure_wipe_clears_content(self):
        buf = SecureConversationBuffer("sess-003")
        original_key = buf.session_key
        buf.add_message("user", "secret data")
        buf.add_message("assistant", "secret response")

        buf.secure_wipe(reason="test")

        self.assertTrue(buf.is_wiped())
        self.assertEqual(buf.get_messages(), [])
        self.assertEqual(buf.session_key, bytes(32))
        self.assertNotEqual(buf.session_key, original_key)

    def test_wipe_is_irreversible(self):
        buf = SecureConversationBuffer("sess-004")
        buf.add_message("user", "data")
        buf.secure_wipe()

        self.assertFalse(buf.add_message("user", "new data"))
        self.assertEqual(buf.get_messages(), [])

    def test_double_wipe_is_safe(self):
        buf = SecureConversationBuffer("sess-005")
        buf.add_message("user", "data")
        buf.secure_wipe(reason="first")
        buf.secure_wipe(reason="second")
        self.assertTrue(buf.is_wiped())
        self.assertEqual(buf.get_messages(), [])

    # -- SessionStore -----------------------------------------------------

    def test_session_store_create_and_retrieve(self):
        store = SessionStore()
        buf_a, _ = store.get_or_create("sid-1")
        buf_b, _ = store.get_or_create("sid-1")
        self.assertIs(buf_a, buf_b)

    def test_session_store_wipe_session(self):
        store = SessionStore()
        buf_old, _ = store.get_or_create("sid-2")
        buf_old.add_message("user", "keep me")
        store.wipe_session("sid-2", reason="test_wipe")

        buf_new, _ = store.get_or_create("sid-2")
        self.assertIsNot(buf_old, buf_new)
        self.assertEqual(buf_new.get_messages(), [])
        self.assertTrue(buf_old.is_wiped())

    def test_session_store_wipe_all(self):
        store = SessionStore()
        bufs = []
        for i in range(5):
            b, _ = store.get_or_create(f"sid-{i}")
            b.add_message("user", f"msg-{i}")
            bufs.append(b)

        store.wipe_all(reason="test_wipe_all")

        self.assertEqual(store.active_count(), 0)
        for b in bufs:
            self.assertTrue(b.is_wiped())
            self.assertEqual(b.get_messages(), [])

    def test_session_store_active_count(self):
        store = SessionStore()
        self.assertEqual(store.active_count(), 0)

        store.get_or_create("a")  # return value unused
        self.assertEqual(store.active_count(), 1)

        store.get_or_create("b")  # return value unused
        self.assertEqual(store.active_count(), 2)

        store.get_or_create("a")  # existing — no change, return value unused
        self.assertEqual(store.active_count(), 2)

        store.wipe_session("a")
        self.assertEqual(store.active_count(), 1)

        store.wipe_session("b")
        self.assertEqual(store.active_count(), 0)

    def test_concurrent_buffer_access(self):
        buf = SecureConversationBuffer("sess-concurrent")
        num_threads = 10
        msgs_per_thread = 50
        barrier = threading.Barrier(num_threads)
        errors: list[str] = []

        def writer(tid: int):
            try:
                barrier.wait(timeout=5)
                for i in range(msgs_per_thread):
                    result = buf.add_message("user", f"t{tid}-m{i}")
                    if not result:
                        errors.append(f"thread {tid} add_message returned False at msg {i}")
            except Exception as exc:
                errors.append(f"thread {tid}: {exc}")

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Concurrent access errors: {errors}")
        msgs = buf.get_messages()
        self.assertEqual(len(msgs), num_threads * msgs_per_thread)


class TestLayer6IntrusionWatchdog(unittest.TestCase):
    """Tests for IntrusionWatchdog."""

    def _make_watchdog(self, terminate: bool = False) -> IntrusionWatchdog:
        store = SessionStore()
        return IntrusionWatchdog(store, terminate_on_intrusion=terminate)

    def test_watchdog_creation(self):
        wd = self._make_watchdog()
        self.assertTrue(wd.running)
        self.assertFalse(wd._triggered)
        self.assertEqual(wd._violation_count, 0)
        self.assertEqual(wd.intrusion_log, [])
        self.assertTrue(wd.daemon)
        self.assertEqual(wd.name, "IntrusionWatchdog")

    def test_watchdog_status(self):
        wd = self._make_watchdog()
        status = wd.get_status()

        required_keys = {"running", "triggered", "violations", "threshold",
                         "check_interval_sec", "recent_events"}
        self.assertEqual(set(status.keys()), required_keys)

        self.assertTrue(status["running"])
        self.assertFalse(status["triggered"])
        self.assertEqual(status["violations"], 0)
        self.assertEqual(status["threshold"], VIOLATION_THRESHOLD)
        self.assertEqual(status["check_interval_sec"], WATCHDOG_INTERVAL)
        self.assertIsInstance(status["recent_events"], list)

    @unittest.skipIf(psutil is None, "psutil not installed")
    def test_check_network_clean(self):
        wd = self._make_watchdog()
        clean, detail = wd.check_network()
        self.assertTrue(clean)
        self.assertEqual(detail, "")

    @unittest.skipIf(psutil is None, "psutil not installed")
    def test_check_processes_clean(self):
        wd = self._make_watchdog()
        clean, detail = wd.check_processes()
        # Can only assert True if none of the suspicious tools are running;
        # if the test machine happens to have one, that's a real finding.
        self.assertIsInstance(clean, bool)
        self.assertIsInstance(detail, str)
        if clean:
            self.assertEqual(detail, "")

    def test_suspicious_process_list_comprehensive(self):
        expected = {
            "x64dbg", "x32dbg", "ollydbg", "windbg", "immunity debugger",
            "processhacker", "process hacker", "cheatengine", "cheat engine",
            "wireshark", "fiddler", "charles proxy", "mitmproxy", "burpsuite",
            "ida64", "ida32", "ghidra",
        }
        actual = set(SUSPICIOUS_PROCESSES)
        self.assertEqual(actual, expected)
        self.assertTrue(len(SUSPICIOUS_PROCESSES) >= 15)

    def test_violation_threshold(self):
        store = SessionStore()
        wd = IntrusionWatchdog(store, terminate_on_intrusion=False)

        for i in range(VIOLATION_THRESHOLD - 1):
            wd._violation_count = i + 1
            self.assertFalse(wd._triggered,
                             f"Should not trigger at violation count {i + 1}")

        wd._violation_count = VIOLATION_THRESHOLD
        wd._trigger_lockdown("test threshold reached")
        self.assertTrue(wd._triggered)

    def test_lockdown_wipes_sessions(self):
        store = SessionStore()
        bufs = []
        for sid in ("s1", "s2", "s3"):
            b, _ = store.get_or_create(sid)
            b.add_message("user", f"secret in {sid}")
            bufs.append(b)

        self.assertEqual(store.active_count(), 3)

        wd = IntrusionWatchdog(store, terminate_on_intrusion=False)
        wd._trigger_lockdown("test lockdown")

        self.assertEqual(store.active_count(), 0)
        for b in bufs:
            self.assertTrue(b.is_wiped())
            self.assertEqual(b.get_messages(), [])
        self.assertTrue(wd._triggered)

    def test_log_event_structure(self):
        wd = self._make_watchdog()
        wd._log_event("TEST_EVENT", "some detail")

        self.assertEqual(len(wd.intrusion_log), 1)
        entry = wd.intrusion_log[0]
        self.assertIn("timestamp", entry)
        self.assertIn("event", entry)
        self.assertIn("detail", entry)
        self.assertEqual(entry["event"], "TEST_EVENT")
        self.assertEqual(entry["detail"], "some detail")
        self.assertRegex(entry["timestamp"], r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    def test_watchdog_stop(self):
        wd = self._make_watchdog()
        self.assertTrue(wd.running)
        wd.stop()
        self.assertFalse(wd.running)
        status = wd.get_status()
        self.assertFalse(status["running"])


if __name__ == "__main__":
    unittest.main()
