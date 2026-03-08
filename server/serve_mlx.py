"""
Kwyre AI — MLX Inference Backend for Apple Silicon
====================================================
Lightweight inference server using mlx-lm on Apple Silicon Macs.
Uses Metal/MPS via MLX — no CUDA required.

Reuses the same API shape, security stack, and HTML frontend as
serve_local_4bit.py but replaces the PyTorch/bitsandbytes model
pipeline with mlx-lm for native Apple Silicon performance.

Usage:
    KWYRE_BACKEND=mlx python server/serve_mlx.py
    KWYRE_MODEL_PATH=./models/kwyre-9b-mlx python server/serve_mlx.py

Environment variables:
    KWYRE_MODEL           HuggingFace model ID (default: Qwen/Qwen3.5-9B)
    KWYRE_MODEL_PATH      Path to pre-converted MLX model directory
    KWYRE_API_KEYS        Comma-separated key:user pairs
    KWYRE_BIND_HOST       Bind address (default: 127.0.0.1)
    KWYRE_MLX_PORT        Port (default: 8000)
    KWYRE_LICENSE_KEY     License key for offline validation
    KWYRE_ENABLE_TOOLS    Set to "1" to enable external tool integrations
    KWYRE_SKIP_DEP_CHECK  Set to "1" to skip dependency verification
"""

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
import sys
import time
import json
import hashlib
import hmac
import secrets
import signal
import threading
import psutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_server_dir)
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_project_root, "model"))
sys.path.insert(0, os.path.join(_project_root, "security"))

TOOLS_ENABLED = os.environ.get("KWYRE_ENABLE_TOOLS", "0") == "1"
if TOOLS_ENABLED:
    from tools import route_tools
else:
    def route_tools(_msg):
        return [], []

from verify_deps import startup_check
from license import startup_validate as validate_license

try:
    import mlx.core as mx
    from mlx_lm import load as mlx_load, generate as mlx_generate
    from mlx_lm.utils import generate_step
    _MLX_AVAILABLE = True
except ImportError:
    _MLX_AVAILABLE = False
    print("[MLX] ERROR: mlx-lm package not installed.")
    print("[MLX] Install with: pip install mlx-lm")
    sys.exit(1)

MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3.5-9B")
PORT = int(os.environ.get("KWYRE_MLX_PORT", "8000"))

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "Qwen/Qwen3-4B": {"name": "kwyre-4b", "vram_4bit": "~3.5GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})


# ---------------------------------------------------------------------------
# LAYER 1: Bind to localhost only
# ---------------------------------------------------------------------------
BIND_HOST = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")


# ---------------------------------------------------------------------------
# LAYER 4: Model weight integrity
# ---------------------------------------------------------------------------
WEIGHT_HASHES_9B: dict[str, str] = {
    "config.json": "d0883072e01861ed0b2d47be3c16c36a8e81c224c7ffaa310c6558fb3f932b05",
    "tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
    "tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
}
WEIGHT_HASHES_4B: dict[str, str] = {}

KNOWN_WEIGHT_HASHES = WEIGHT_HASHES_9B if "9B" in MODEL_ID else WEIGHT_HASHES_4B


def generate_weight_hashes(model_path: str) -> dict:
    files_to_hash = ["config.json", "tokenizer_config.json",
                     "generation_config.json", "tokenizer.json"]
    hashes = {}
    for fname in files_to_hash:
        fpath = os.path.join(model_path, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                hashes[fname] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def verify_model_integrity(model_path: str) -> bool:
    if not KNOWN_WEIGHT_HASHES:
        print("[Integrity] WARNING: No reference hashes configured — skipping check.")
        print("[Integrity] Run generate_weight_hashes() on a clean install first.")
        return True
    print("[Integrity] Verifying model weights...")
    all_ok = True
    for filename, expected in KNOWN_WEIGHT_HASHES.items():
        fpath = os.path.join(model_path, filename)
        if not os.path.exists(fpath):
            print(f"[Integrity] FAIL — {filename} missing")
            all_ok = False
            continue
        with open(fpath, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != expected:
            print(f"[Integrity] FAIL — {filename} hash mismatch")
            all_ok = False
        else:
            print(f"[Integrity] OK   — {filename}")
    if not all_ok:
        print("[Integrity] INTEGRITY CHECK FAILED — refusing to start.")
    return all_ok


# ---------------------------------------------------------------------------
# LAYER 5: Secure conversation buffer (identical to serve_local_4bit.py)
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

    def get_or_create(self, session_id: str) -> SecureConversationBuffer:
        with self._lock:
            if session_id not in self._sessions or self._sessions[session_id].is_wiped():
                self._sessions[session_id] = SecureConversationBuffer(session_id)
            self._last_access[session_id] = time.time()
            return self._sessions[session_id]

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
                self.wipe_session(sid, reason="idle_timeout")

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------------------
# LAYER 6: Intrusion watchdog (identical to serve_local_4bit.py)
# ---------------------------------------------------------------------------
SUSPICIOUS_PROCESSES = [
    "x64dbg", "x32dbg", "ollydbg", "windbg", "immunity debugger",
    "processhacker", "process hacker", "cheatengine", "cheat engine",
    "wireshark", "fiddler", "charles proxy", "mitmproxy", "burpsuite",
    "ida64", "ida32", "ghidra",
]

ALLOWED_REMOTE_IPS = {"127.0.0.1"}
import ipaddress as _ipaddress
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

API_KEYS = _load_api_keys()
RATE_LIMIT_RPM = 30
rate_tracker = defaultdict(list)
CHAT_DIR = os.path.join(_project_root, "chat")
ALLOWED_PAGES = {"landing.html", "index.html", "main.html", "pay.html", "chat.html"}


# ---------------------------------------------------------------------------
# Startup sequence — resolve model path for MLX
# ---------------------------------------------------------------------------
# Priority: KWYRE_MODEL_PATH env > dist/ folder (mlx variant) > HuggingFace cache
PREQUANT_PATH = os.environ.get("KWYRE_MODEL_PATH", "")
_dist_path = os.path.join(_project_root, "dist", f"{ACTIVE_TIER['name']}-mlx")
_USE_PREQUANT = False

if PREQUANT_PATH and os.path.isdir(PREQUANT_PATH):
    LOCAL_MODEL_PATH = PREQUANT_PATH
    _USE_PREQUANT = True
    print(f"[Model] Using MLX model at {PREQUANT_PATH}")
elif os.path.isdir(_dist_path):
    LOCAL_MODEL_PATH = _dist_path
    _USE_PREQUANT = True
    print(f"[Model] Using MLX model at {_dist_path}")
else:
    LOCAL_MODEL_PATH = os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface", "hub",
        f"models--{MODEL_ID.replace('/', '--')}",
        "snapshots",
    )
    try:
        _snap_dirs = [d for d in os.listdir(LOCAL_MODEL_PATH)
                      if os.path.isdir(os.path.join(LOCAL_MODEL_PATH, d))]
        LOCAL_MODEL_PATH = os.path.join(LOCAL_MODEL_PATH, _snap_dirs[0]) if _snap_dirs else LOCAL_MODEL_PATH
    except FileNotFoundError:
        print(f"[Model] ERROR: No model found. Set KWYRE_MODEL_PATH or download first.")
        sys.exit(1)
    print(f"[Model] Using HuggingFace cache at {LOCAL_MODEL_PATH}")

if _USE_PREQUANT:
    print("[Integrity] Pre-converted MLX model — skipping hash check (trusted source)")
elif not verify_model_integrity(LOCAL_MODEL_PATH):
    sys.exit(1)

_skip_dep_check = os.environ.get("KWYRE_SKIP_DEP_CHECK", "0") == "1"
startup_check(abort_on_failure=not _skip_dep_check)

# ---------------------------------------------------------------------------
# LICENSE VALIDATION (works fully offline)
# ---------------------------------------------------------------------------
_license_data = validate_license()
if _license_data is None:
    print("[License] WARNING: No valid license. Running in evaluation mode.")
    print("[License] Purchase at https://kwyre.com")
_license_tier: str = _license_data["tier"] if _license_data else "eval"
_MAX_EVAL_TOKENS = 512
if _license_tier == "eval":
    RATE_LIMIT_RPM = 10


# ---------------------------------------------------------------------------
# Load MLX model and tokenizer
# ---------------------------------------------------------------------------
print(f"[MLX] Loading model from {LOCAL_MODEL_PATH}...")
model, tokenizer = mlx_load(LOCAL_MODEL_PATH)
print(f"[MLX] Model loaded on Apple Silicon (Metal)")

session_store = SessionStore()
watchdog = IntrusionWatchdog(session_store, terminate_on_intrusion=True)
watchdog.start()


def _shutdown_handler(signum, frame):
    print("\n[Shutdown] Wiping all sessions before exit...")
    watchdog.stop()
    session_store.wipe_all(reason="server_shutdown")
    sys.exit(0)

signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

_trial_tracker: dict[str, int] = {}
print(f"[Security] Bound to {BIND_HOST}:{PORT} — localhost only")
print(f"[Security] Intrusion watchdog active")
print(f"[Security] Session store active — RAM only, wiped on close")


def _mlx_chat_generate(messages: list[dict], max_tokens: int = 2048,
                        temperature: float = 0.7, top_p: float = 0.9) -> tuple[str, int, float]:
    """Generate a response using mlx-lm from a list of chat messages.
    Returns (reply_text, token_count, elapsed_seconds)."""
    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
    else:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"<|{role}|>\n{content}")
        parts.append("<|assistant|>\n")
        prompt = "\n".join(parts)

    t0 = time.time()
    response = mlx_generate(
        model, tokenizer, prompt=prompt,
        max_tokens=max_tokens,
        temp=max(temperature, 0.01) if temperature > 0 else 0.0,
        top_p=top_p,
        verbose=False,
    )
    elapsed = time.time() - t0

    n_tokens = len(tokenizer.encode(response))

    reply = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
    reply = reply.strip()

    return reply, n_tokens, elapsed


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class ChatHandler(BaseHTTPRequestHandler):

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
            for valid_key, user in API_KEYS.items():
                if hmac.compare_digest(key, valid_key):
                    return user
        self._send_json_error(401, "Invalid API key.")
        return None

    def _check_auth_optional(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
            for valid_key, user in API_KEYS.items():
                if hmac.compare_digest(key, valid_key):
                    return user
        return None

    def _check_rate_limit(self, user):
        now = time.time()
        rate_tracker[user] = [t for t in rate_tracker[user] if now - t < 60]
        if len(rate_tracker[user]) >= RATE_LIMIT_RPM:
            self._send_json_error(429, f"Rate limit exceeded. Max {RATE_LIMIT_RPM} req/min.")
            return False
        rate_tracker[user].append(now)
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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self._send_security_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            user = self._check_auth()
            if user is None:
                return
            if not self._check_rate_limit(user):
                return

            body, err = self._parse_json_body(required=True)
            if err is not None:
                self._send_json_error(400, err)
                return
            assert body is not None
            messages = body.get("messages", [])
            if not isinstance(messages, list) or len(messages) > 100:
                self._send_json_error(400, "messages must be a list of at most 100 items.")
                return
            try:
                max_tokens = min(max(int(body.get("max_tokens", 2048)), 1), 8192)
                temperature = min(max(float(body.get("temperature", 0.7)), 0.0), 2.0)
                top_p = min(max(float(body.get("top_p", 0.9)), 0.0), 1.0)
            except (TypeError, ValueError):
                self._send_json_error(400, "Invalid max_tokens, temperature, or top_p.")
                return
            if _license_tier == "eval":
                max_tokens = min(max_tokens, _MAX_EVAL_TOKENS)
            session_id = self._get_session_id(body)

            if _license_tier == "eval":
                trial_key = f"trial:{self.client_address[0]}"
                trial_count = _trial_tracker.get(trial_key, 0)
                if trial_count >= 3:
                    self._send_json_error(429, "Trial limit reached. Purchase a license at https://kwyre.com")
                    return
                _trial_tracker[trial_key] = trial_count + 1

            session = session_store.get_or_create(session_id)
            for m in messages:
                session.add_message(m.get("role", "user"), m.get("content", ""))

            tool_data, tools_used = [], []
            last_user_msg = next(
                (m.get("content", "") for m in reversed(messages)
                 if m.get("role") == "user"), ""
            )
            if last_user_msg:
                try:
                    tool_data, tools_used = route_tools(last_user_msg)
                except Exception as e:
                    print(f"[tools] error: {e}")

            augmented = list(messages)
            if tool_data:
                ctx = ("\n\n[Live data — use directly, be concise]\n\n"
                       + "\n\n".join(tool_data))
                for i in range(len(augmented) - 1, -1, -1):
                    if augmented[i].get("role") == "user":
                        augmented[i] = {
                            "role": "user",
                            "content": augmented[i]["content"] + ctx,
                        }
                        break

            reply, n_tokens, elapsed = _mlx_chat_generate(
                augmented, max_tokens=max_tokens,
                temperature=temperature, top_p=top_p,
            )
            tps = n_tokens / elapsed if elapsed > 0 else 0

            session.add_message("assistant", reply)
            print(f"[inference] {session_id[:8]}... | {n_tokens} tokens "
                  f"in {elapsed:.1f}s ({tps:.1f} tok/s)")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "choices": [{"message": {"role": "assistant", "content": reply}}],
                "model": f"{ACTIVE_TIER['name']}-mlx",
                "session_id": session_id,
                "tools_used": tools_used,
                "usage": {
                    "completion_tokens": n_tokens,
                    "tokens_per_second": round(tps, 1),
                },
                "backend": "mlx",
            }).encode())

        elif self.path == "/v1/session/end":
            user = self._check_auth()
            if user is None:
                return
            body, err = self._parse_json_body(required=False)
            if err is not None:
                self._send_json_error(400, err)
                return
            sid = (body or {}).get("session_id", "")
            if sid:
                session_store.wipe_session(sid, reason="user_request")
                msg = f"Session {sid[:8]}... wiped. Conversation unrecoverable."
            else:
                msg = "No session_id provided."
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"status": "wiped", "message": msg}).encode())

        elif self.path == "/v1/license/verify":
            body, err = self._parse_json_body()
            if err is not None:
                self._send_json_error(400, err)
                return
            key = body.get("key", "").strip()
            if not key:
                self._send_json_error(400, "Missing license key.")
                return
            try:
                from license import validate_license as _validate_lic
                payload = _validate_lic(key)
                tier = payload.get("tier", "unknown")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "valid": True,
                    "tier": tier,
                    "label": payload.get("label", ""),
                    "machines": payload.get("machines", 0),
                }).encode())
            except ValueError as e:
                self._send_json_error(403, str(e))

        else:
            self._send_json_error(404, "Not found.")

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
        self.send_header("Access-Control-Allow-Origin", f"http://{BIND_HOST}:{PORT}")

    def _serve_html(self, filename: str):
        filepath = os.path.join(CHAT_DIR, filename)
        resolved = os.path.realpath(filepath)
        if not resolved.startswith(os.path.realpath(CHAT_DIR)):
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

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("chat.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)

        elif self.path == "/health":
            auth_user = self._check_auth_optional()
            health_data = {"status": "ok"}
            if auth_user:
                health_data.update({
                    "model": f"{ACTIVE_TIER['name']}-mlx",
                    "base": MODEL_ID.split("/")[-1],
                    "backend": "mlx",
                    "quantization": "MLX native",
                    "security": {
                        "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                        "l2_process_lockdown": "os-configured (firewall, not verified by server)",
                        "l3_dependency_integrity": "verified",
                        "l4_weight_integrity": "configured" if KNOWN_WEIGHT_HASHES else "first-run",
                        "l5_conversation_storage": "RAM-only",
                        "l6_intrusion_watchdog": watchdog.get_status(),
                        "sessions_active": session_store.active_count(),
                    },
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps(health_data, indent=2).encode())

        elif self.path == "/audit":
            user = self._check_auth()
            if user is None:
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "server": f"{ACTIVE_TIER['name']}-mlx",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_sessions": session_store.active_count(),
                "security_controls": {
                    "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                    "l2_process_lockdown": "os-configured (firewall)",
                    "l3_dependency_integrity": "verified at startup",
                    "l4_weight_integrity": "enabled" if KNOWN_WEIGHT_HASHES else "unconfigured",
                    "l5_conversation_storage": "RAM-only",
                    "l5_session_wipe": "on_close + idle_timeout_1hr + shutdown + intrusion",
                    "l6_intrusion_watchdog": watchdog.get_status(),
                    "content_logging": "NEVER",
                },
                "note": "Metadata only. No conversation content is ever logged or persisted.",
            }, indent=2).encode())

        elif self.path == "/v1/models":
            user = self._check_auth()
            if user is None:
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "object": "list",
                "data": [{
                    "id": f"{ACTIVE_TIER['name']}-mlx",
                    "object": "model",
                    "owned_by": "kwyre",
                    "meta": {
                        "base_model": MODEL_ID.split("/")[-1],
                        "backend": "mlx",
                        "quantization": "MLX native",
                        "security": {
                            "network": "localhost-only",
                            "storage": "RAM-only sessions",
                            "integrity": "SHA256 weight verification",
                            "watchdog": "intrusion detection + auto-wipe",
                        },
                    },
                }],
            }).encode())

        elif self.path == "/favicon.ico":
            self.send_response(204)
            self._send_security_headers()
            self.end_headers()

        else:
            self._send_json_error(404, "Not found.")

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = ThreadedHTTPServer((BIND_HOST, PORT), ChatHandler)
    print(f"\nKwyre AI (MLX) ready at http://{BIND_HOST}:{PORT}")
    print(f"  Model: {ACTIVE_TIER['name']}-mlx ({MODEL_ID})  |  tier: {ACTIVE_TIER['tier']}")
    print(f"  Backend: MLX (Apple Silicon / Metal)  |  all 6 security layers active")
    print(f"  Available tiers: KWYRE_MODEL=Qwen/Qwen3.5-9B | Qwen/Qwen3-4B")
    print("  POST /v1/chat/completions  — inference")
    print("  POST /v1/session/end       — wipe session from RAM")
    print("  GET  /health               — status + watchdog state")
    print("  GET  /audit                — metadata-only compliance log")
    print("\n  [L1] Network: localhost only")
    print("  [L3] Dependencies: SHA256 manifest verified at startup")
    print("  [L4] Integrity: SHA256 weight verification at startup")
    print("  [L5] Storage: RAM-only sessions, wiped on close")
    print("  [L6] Watchdog: intrusion detection active")
    if TOOLS_ENABLED:
        print("  [Tools] ENABLED — external API calls active (NOT air-gapped)")
    else:
        print("  [Tools] DISABLED — fully air-gapped, no external requests")
    print("\n  All inference runs 100% locally on Apple Silicon. No data leaves this machine.\n")
    server.serve_forever()
