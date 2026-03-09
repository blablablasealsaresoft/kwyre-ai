"""
Kwyre AI — Shared Security Infrastructure
==========================================
Extracted from serve_local_4bit.py so both GPU and CPU (Kwyre Air)
servers can share the same security layers without importing torch.

Provides:
  - SecureConversationBuffer  (L5 — RAM-only session storage + crypto wipe)
  - SessionStore              (L5 — session lifecycle management)
  - IntrusionWatchdog         (L6 — process/network intrusion detection)
  - API key loading + rate limiting helpers
  - Security header helpers
  - HTML page serving helpers
"""

import hmac
import ipaddress as _ipaddress
import json
import os
import re
import secrets
import signal
import sys
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler

import psutil


# ---------------------------------------------------------------------------
# LAYER 1: Network binding
# ---------------------------------------------------------------------------
BIND_HOST = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")


# ---------------------------------------------------------------------------
# LAYER 5: Secure conversation buffer
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
            print(f"[SecureBuffer] {self.session_id[:8]}... wiped ({n} msgs, reason={reason})")

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
            print(f"[SessionStore] Wiping {len(self._sessions)} sessions ({reason})...")
            for buf in self._sessions.values():
                buf.secure_wipe(reason=reason)
            self._sessions.clear()
            self._last_access.clear()
        print("[SessionStore] All sessions wiped.")

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

    def get_sessions_for_user(self, user_id: str) -> list[str]:
        """Return session IDs owned by a specific user (namespaced as user_id:sid)."""
        prefix = f"{user_id}:"
        with self._lock:
            return [s for s in self._sessions if s.startswith(prefix)]

    def count_sessions_for_user(self, user_id: str) -> int:
        return len(self.get_sessions_for_user(user_id))

    def wipe_user_sessions(self, user_id: str, reason: str = "admin_wipe"):
        for sid in self.get_sessions_for_user(user_id):
            self.wipe_session(sid, reason=reason)

    def list_all_session_metadata(self) -> list[dict]:
        """Return metadata for all sessions. Never exposes content."""
        with self._lock:
            result = []
            for sid, buf in self._sessions.items():
                parts = sid.split(":", 1)
                result.append({
                    "session_id": sid,
                    "user_id": parts[0] if len(parts) == 2 else "unknown",
                    "created_at": buf.created_at,
                    "message_count": len(buf._buffer),
                    "wiped": buf.is_wiped(),
                })
            return result


# ---------------------------------------------------------------------------
# LAYER 6: Intrusion watchdog
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

WATCHDOG_INTERVAL = 5
VIOLATION_THRESHOLD = 2


def _is_allowed_ip(ip_str: str) -> bool:
    if ip_str in ALLOWED_REMOTE_IPS:
        return True
    try:
        addr = _ipaddress.ip_address(ip_str)
        return any(addr in net for net in _DOCKER_NETS)
    except ValueError:
        return False


class IntrusionWatchdog(threading.Thread):
    """
    Background thread that monitors for:
      1. Unexpected outbound network connections from this process
      2. Known debugging / traffic analysis tools running on the system

    On confirmed intrusion:
      - Wipes all active sessions immediately
      - Logs the event with timestamp and reason
      - Optionally terminates the server process entirely

    Conservative by design — two consecutive violations required
    before triggering to reduce false positives.
    """

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
        if len(self.intrusion_log) > 100:
            self.intrusion_log = self.intrusion_log[-100:]
        print(f"[Watchdog] {event_type}: {detail}")

    def check_network(self) -> tuple[bool, str]:
        our_pid = os.getpid()
        try:
            proc = psutil.Process(our_pid)
            all_procs = [proc] + proc.children(recursive=True)
            for p in all_procs:
                for conn in p.net_connections():
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
        except Exception as e:
            print(f"[Watchdog] network check error (non-fatal): {e}")
        return True, ""

    def check_processes(self) -> tuple[bool, str]:
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    if any(s in name for s in SUSPICIOUS_PROCESSES):
                        return False, f"suspicious process detected: {proc.info['name']} (pid={proc.info['pid']})"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            print(f"[Watchdog] process check error (non-fatal): {e}")
        return True, ""

    def _trigger_lockdown(self, reason: str):
        with self._lock:
            if self._triggered:
                return
            self._triggered = True

        print(f"\n[Watchdog] *** INTRUSION LOCKDOWN TRIGGERED ***")
        print(f"[Watchdog] Reason: {reason}")
        self._log_event("LOCKDOWN", reason)

        self.session_store.wipe_all(reason=f"intrusion_lockdown: {reason}")

        if self.terminate_on_intrusion:
            print("[Watchdog] Terminating server process.")
            time.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

    def run(self):
        print(f"[Watchdog] Started — checking every {WATCHDOG_INTERVAL}s "
              f"(threshold={VIOLATION_THRESHOLD} violations)")
        while self.running and not self._triggered:
            time.sleep(WATCHDOG_INTERVAL)

            net_clean, net_detail = self.check_network()
            proc_clean, proc_detail = self.check_processes()

            if not net_clean or not proc_clean:
                self._violation_count += 1
                detail = net_detail or proc_detail
                print(f"[Watchdog] Violation {self._violation_count}/{VIOLATION_THRESHOLD}: {detail}")
                self._log_event("VIOLATION", detail)

                if self._violation_count >= VIOLATION_THRESHOLD:
                    self._trigger_lockdown(detail)
            else:
                if self._violation_count > 0:
                    print(f"[Watchdog] Clear — resetting violation count")
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


# ---------------------------------------------------------------------------
# API keys + rate limiting
# ---------------------------------------------------------------------------
def load_api_keys() -> dict[str, str]:
    env_keys = os.environ.get("KWYRE_API_KEYS", "")
    if env_keys:
        keys = {}
        for pair in env_keys.split(","):
            if ":" in pair:
                k, u = pair.strip().split(":", 1)
                keys[k] = u
        return keys
    return {"sk-kwyre-dev-local": "admin"}


RATE_LIMIT_RPM_DEFAULT = 30
ALLOWED_PAGES = {"landing.html", "index.html", "main.html", "pay.html", "technology.html", "security.html", "platform.html", "custom.html"}


# ---------------------------------------------------------------------------
# Shared request handler mixin — security headers, auth, JSON helpers
# ---------------------------------------------------------------------------
class KwyreHandlerMixin:
    """
    Mixin providing shared HTTP handler methods used by both
    the GPU (serve_local_4bit) and CPU (serve_cpu) servers.

    Subclass must also inherit from BaseHTTPRequestHandler and must set:
      - self._api_keys: dict[str, str]
      - self._rate_tracker: defaultdict(list)
      - self._rate_limit_rpm: int
      - self._bind_host: str
      - self._port: int
      - self._chat_dir: str
    """

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
            for valid_key, user in self._api_keys.items():
                if hmac.compare_digest(key, valid_key):
                    return user
        self._send_json_error(401, "Invalid API key.")
        return None

    def _check_auth_optional(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
            for valid_key, user in self._api_keys.items():
                if hmac.compare_digest(key, valid_key):
                    return user
        return None

    def _check_rate_limit(self, user):
        now = time.time()
        self._rate_tracker[user] = [t for t in self._rate_tracker[user] if now - t < 60]
        if len(self._rate_tracker[user]) >= self._rate_limit_rpm:
            self._send_json_error(429, f"Rate limit exceeded. Max {self._rate_limit_rpm} req/min.")
            return False
        self._rate_tracker[user].append(now)
        if len(self._rate_tracker) > 1000:
            stale = [k for k, v in self._rate_tracker.items() if not v or now - max(v) > 120]
            for k in stale:
                del self._rate_tracker[k]
        return True

    def _get_session_id(self, body: dict) -> str:
        sid = body.get("session_id")
        if not sid or not isinstance(sid, str) or len(sid) < 32:
            sid = secrets.token_hex(16)
        return sid

    def _parse_json_body(self, required: bool = False) -> tuple[dict | None, str | None]:
        try:
            raw_len = self.headers.get("Content-Length")
            if raw_len is None or raw_len.strip() == "":
                if required:
                    return None, "Missing Content-Length header."
                return {}, None
            length = int(raw_len)
        except ValueError:
            return None, "Invalid Content-Length header."
        if length < 0:
            return None, "Invalid Content-Length: negative value."
        if length > 10 * 1024 * 1024:
            return None, "Content-Length exceeds 10MB limit."
        raw = self.rfile.read(length)
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

    def _send_json_error(self, status: int, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def _send_security_headers(self, nonce: str = "", extra_script_src: str = ""):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        script_src = "'self'"
        if nonce:
            script_src += f" 'nonce-{nonce}'"
        else:
            script_src += " 'unsafe-inline'"
        if extra_script_src:
            script_src += f" {extra_script_src}"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"connect-src 'self'; "
            f"img-src 'self' data:; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'",
        )
        self.send_header("Access-Control-Allow-Origin", f"http://{self._bind_host}:{self._port}")

    def _serve_html(self, filename: str):
        filepath = os.path.join(self._chat_dir, filename)
        resolved = os.path.realpath(filepath)
        if not resolved.startswith(os.path.realpath(self._chat_dir)):
            self.send_response(403)
            self._send_security_headers()
            self.end_headers()
            return
        if not os.path.isfile(resolved):
            self.send_response(404)
            self._send_security_headers()
            self.end_headers()
            return
        with open(resolved, "rb") as f:
            html = f.read()
        nonce = secrets.token_urlsafe(16)
        html = html.replace(b"{{CSP_NONCE}}", nonce.encode())
        extra_script_src = "https://cdn.jsdelivr.net" if filename == "pay.html" else ""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self._send_security_headers(nonce=nonce, extra_script_src=extra_script_src)
        self.end_headers()
        self.wfile.write(html)

    @staticmethod
    def _safe_page_name(raw_path: str) -> str | None:
        stripped = raw_path.lstrip("/")
        basename = os.path.basename(stripped)
        if basename in ALLOWED_PAGES and basename == stripped:
            return basename
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self._send_security_headers()
        self.end_headers()
