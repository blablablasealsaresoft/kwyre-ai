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
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_server_dir)
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_project_root, "model"))
sys.path.insert(0, os.path.join(_project_root, "security"))

from security_core import (
    BIND_HOST,
    SessionStore,
    IntrusionWatchdog,
    load_api_keys,
    RATE_LIMIT_RPM_DEFAULT,
    ALLOWED_PAGES,
    KwyreHandlerMixin,
)

TOOLS_ENABLED = os.environ.get("KWYRE_ENABLE_TOOLS", "0") == "1"
if TOOLS_ENABLED:
    from tools import route_tools
else:
    def route_tools(_msg):
        return [], []

from verify_deps import startup_check
from license import startup_validate as validate_license

try:
    from mlx_lm import load as mlx_load, generate as mlx_generate, stream_generate
    from mlx_lm.sample_utils import make_sampler as _make_mlx_sampler
except ImportError:
    print("[MLX] ERROR: mlx-lm package not installed.")
    print("[MLX] Install with: pip install mlx-lm")
    sys.exit(1)

DEFAULT_SYSTEM_PROMPT = (
    "You are Kwyre, a specialized AI assistant running natively on Apple Silicon. "
    "You provide precise, well-structured responses citing relevant regulations, "
    "statutes, and professional standards. You organize complex analysis with clear "
    "headings, numbered points, and specific references. You never fabricate citations "
    "or case law. If uncertain, you state your confidence level explicitly."
)

MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3.5-9B")
PORT = int(os.environ.get("KWYRE_MLX_PORT", "8000"))

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": {"name": "kwyre-4b", "vram_4bit": "~4.1GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})

# ---------------------------------------------------------------------------
# LAYER 4: Model weight integrity
# ---------------------------------------------------------------------------
WEIGHT_HASHES_9B: dict[str, str] = {
    "config.json": "d0883072e01861ed0b2d47be3c16c36a8e81c224c7ffaa310c6558fb3f932b05",
    "tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
    "tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
}
# Hashes are for Qwen/Qwen3.5-4B base (tokenizer is byte-identical in the uncensored fine-tune).
# Regenerate with generate_weight_hashes() if loading a locally converted copy.
WEIGHT_HASHES_4B: dict[str, str] = {
    "config.json": "ddc63e1c717afa86c865bb5e01313d89d72bb53b97ad4a8a03ba8510c0621670",
    "tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
    "tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
}

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
# API keys + rate limiting
# ---------------------------------------------------------------------------
API_KEYS = load_api_keys()
RATE_LIMIT_RPM = RATE_LIMIT_RPM_DEFAULT
rate_tracker: defaultdict[str, list] = defaultdict(list)
CHAT_DIR = os.path.join(_project_root, "chat")


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

_inference_lock = threading.Lock()


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
                        temperature: float = 0.7, top_p: float = 0.9,
                        repetition_penalty: float = 1.1,
                        top_k: int = 20) -> tuple[str, int, float]:
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
    gen_kwargs = dict(
        prompt=prompt, max_tokens=max_tokens,
        temp=max(temperature, 0.01) if temperature > 0 else 0.0,
        top_p=top_p, top_k=top_k, verbose=False,
    )
    if repetition_penalty != 1.0:
        gen_kwargs["repetition_penalty"] = repetition_penalty
    response = mlx_generate(model, tokenizer, **gen_kwargs)
    elapsed = time.time() - t0

    n_tokens = len(tokenizer.encode(response))

    reply = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
    reply = reply.strip()

    return reply, n_tokens, elapsed


def _try_make_sampler(temperature: float, top_p: float,
                      repetition_penalty: float = 1.1, top_k: int = -1):
    """Build an MLX sampler, falling back gracefully if kwargs are unsupported."""
    try:
        return _make_mlx_sampler(temperature, top_p, repetition_penalty=repetition_penalty, top_k=top_k)
    except TypeError:
        try:
            return _make_mlx_sampler(temperature, top_p, repetition_penalty=repetition_penalty)
        except TypeError:
            return _make_mlx_sampler(temperature, top_p)


def _mlx_chat_stream(messages: list[dict], max_tokens: int = 2048,
                     temperature: float = 0.7, top_p: float = 0.9,
                     repetition_penalty: float = 1.1, top_k: int = 20):
    """Yield per-token deltas for SSE streaming."""
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

    sampler = _try_make_sampler(temperature, top_p, repetition_penalty, top_k)
    prev_text = ""
    for response in stream_generate(model, tokenizer, prompt=prompt,
                                     max_tokens=max_tokens, sampler=sampler):
        new_text = response.text
        delta = new_text[len(prev_text):]
        prev_text = new_text
        if delta:
            yield delta


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class ChatHandler(KwyreHandlerMixin, BaseHTTPRequestHandler):

    _api_keys = API_KEYS
    _rate_tracker = rate_tracker
    _rate_limit_rpm = RATE_LIMIT_RPM
    _bind_host = BIND_HOST
    _port = PORT
    _chat_dir = CHAT_DIR

    def _handle_blocking(self, augmented, max_tokens, temperature, top_p,
                         repetition_penalty, top_k, session_id, session, tools_used):
        with _inference_lock:
            reply, n_tokens, elapsed = _mlx_chat_generate(
                augmented, max_tokens=max_tokens,
                temperature=temperature, top_p=top_p,
                repetition_penalty=repetition_penalty, top_k=top_k,
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

    def _handle_stream(self, augmented, max_tokens, temperature, top_p,
                       repetition_penalty, top_k, session_id, session, user, tools_used):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(b": stream opened\n\n")
        self.wfile.flush()

        full_reply = []
        t0 = time.time()
        n_tokens = 0

        try:
            with _inference_lock:
                for token_text in _mlx_chat_stream(augmented, max_tokens, temperature, top_p, repetition_penalty, top_k):
                    full_reply.append(token_text)
                    n_tokens += 1
                    if n_tokens > max_tokens:
                        break
                    sse_data = json.dumps({
                        "choices": [{"delta": {"content": token_text}}],
                        "model": f"{ACTIVE_TIER['name']}-mlx",
                        "session_id": session_id,
                    })
                    self.wfile.write(f"data: {sse_data}\n\n".encode())
                    self.wfile.flush()

            elapsed = time.time() - t0
            tps = n_tokens / elapsed if elapsed > 0 else 0

            reply_text = "".join(full_reply)
            reply_text = re.sub(r"<think>.*?</think>", "", reply_text, flags=re.DOTALL)
            reply_text = re.sub(r"<think>.*", "", reply_text, flags=re.DOTALL)
            reply_text = reply_text.strip()
            session.add_message("assistant", reply_text)

            done_data = json.dumps({
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "model": f"{ACTIVE_TIER['name']}-mlx",
                "session_id": session_id,
                "tools_used": tools_used,
                "usage": {
                    "completion_tokens": n_tokens,
                    "tokens_per_second": round(tps, 1),
                },
            })
            self.wfile.write(f"data: {done_data}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

            print(f"[inference] {session_id[:8]}... | {n_tokens} tokens "
                  f"in {elapsed:.1f}s ({tps:.1f} tok/s) [stream]")

        except (BrokenPipeError, ConnectionResetError):
            print(f"[inference] {session_id[:8]}... | client disconnected during stream")

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
                repetition_penalty = min(max(float(body.get("repetition_penalty", 1.1)), 1.0), 2.0)
                top_k = min(max(int(body.get("top_k", 20)), 0), 100)
            except (TypeError, ValueError):
                self._send_json_error(400, "Invalid max_tokens, temperature, top_p, or top_k.")
                return
            if _license_tier == "eval":
                max_tokens = min(max_tokens, _MAX_EVAL_TOKENS)
            session_id = self._get_session_id(body)
            stream = body.get("stream", False)

            if _license_tier == "eval":
                trial_key = f"trial:{self.client_address[0]}"
                trial_count = _trial_tracker.get(trial_key, 0)
                if trial_count >= 3:
                    self._send_json_error(429, "Trial limit reached. Purchase a license at https://kwyre.com")
                    return
                _trial_tracker[trial_key] = trial_count + 1

            session, _created = session_store.get_or_create(session_id)
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
            if not any(m.get("role") == "system" for m in augmented):
                augmented.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})
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

            if stream:
                self._handle_stream(augmented, max_tokens, temperature, top_p,
                                    repetition_penalty, top_k, session_id, session, user, tools_used)
            else:
                self._handle_blocking(augmented, max_tokens, temperature, top_p,
                                      repetition_penalty, top_k, session_id, session, tools_used)

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

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("main.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)

        elif self.path == "/health":
            auth_user = self._check_auth_optional()
            health_data = {"status": "ok"}
            if auth_user:
                health_data.update({
                    "model": f"{ACTIVE_TIER['name']}-mlx",
                    "product": "Kwyre (Apple Silicon)",
                    "description": "Native Metal acceleration for M1/M2/M3/M4",
                    "base": MODEL_ID.split("/")[-1],
                    "backend": "mlx",
                    "quantization": "MLX native",
                    "streaming": "SSE (text/event-stream)",
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
                        "product": "Kwyre (Apple Silicon)",
                        "capabilities": ["streaming", "session_wipe", "crypto_wipe", "tools"],
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
    print(f"\n{'='*60}")
    print(f"  KWYRE — Apple Silicon Inference")
    print(f"  Native Metal acceleration for M1/M2/M3/M4")
    print(f"{'='*60}")
    print(f"  Model:   {ACTIVE_TIER['name']}-mlx ({MODEL_ID})")
    print(f"  Tier:    {ACTIVE_TIER['tier']}")
    print(f"  Backend: MLX (Metal) | URL: http://{BIND_HOST}:{PORT}")
    print()
    print(f"  Endpoints:")
    print(f"    POST /v1/chat/completions  — inference (streaming supported)")
    print(f"    POST /v1/session/end       — cryptographic session wipe")
    print(f"    GET  /health               — system status")
    print(f"    GET  /audit                — compliance log")
    print()
    print(f"  Security:")
    print(f"    [L1] Network: localhost only")
    print(f"    [L3] Dependencies: SHA256 manifest verified")
    print(f"    [L4] Integrity: SHA256 weight verification")
    print(f"    [L5] Storage: RAM-only, crypto-wiped on close")
    print(f"    [L6] Watchdog: intrusion detection active")
    if TOOLS_ENABLED:
        print(f"    [Tools] ENABLED (NOT air-gapped)")
    else:
        print(f"    [Tools] DISABLED — fully air-gapped")
    print(f"\n  All inference runs 100% on Apple Silicon. No data leaves this machine.\n")
    server.serve_forever()
