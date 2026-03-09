"""
Kwyre Air — CPU-only inference server using llama.cpp
=====================================================
Runs any GGUF model on CPU via llama-cpp-python. No GPU required.

Same OpenAI-compatible API, same security layers, same HTML frontend
as the GPU server (serve_local_4bit.py) — but works on ANY hardware.

Usage:
    python server/serve_cpu.py

Environment variables:
    KWYRE_GGUF_PATH     — path to .gguf model file (required)
    KWYRE_BIND_HOST     — bind address (default 127.0.0.1)
    KWYRE_PORT          — port (default 8000)
    KWYRE_API_KEYS      — API keys (default sk-kwyre-dev-local:admin)
    KWYRE_CTX_LENGTH    — context length (default 8192)
    KWYRE_THREADS       — CPU threads for inference (default auto)
    KWYRE_BACKEND       — set to "cpu" for clarity (optional)
"""

import os
import re
import sys
import json
import time
import signal
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_server_dir)
sys.path.insert(0, _server_dir)
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

from license import startup_validate as validate_license

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are Kwyre, a specialized AI assistant for legal, financial, and forensic "
    "analysis. You provide precise, well-structured responses citing relevant "
    "regulations, statutes, and professional standards. You organize complex analysis "
    "with clear headings, numbered points, and specific references. When analyzing "
    "documents, you identify key obligations, risks, and compliance requirements. "
    "You never fabricate citations or case law. If uncertain, you state your "
    "confidence level explicitly."
)

PORT = int(os.environ.get("KWYRE_PORT", "8000"))
CTX_LENGTH = int(os.environ.get("KWYRE_CTX_LENGTH", "8192"))
N_THREADS = int(os.environ.get("KWYRE_THREADS", "0")) or None  # None = auto-detect
GGUF_PATH = os.environ.get("KWYRE_GGUF_PATH", "")
MODEL_NAME = "kwyre-air"

API_KEYS = load_api_keys()
RATE_LIMIT_RPM = RATE_LIMIT_RPM_DEFAULT
rate_tracker: defaultdict[str, list] = defaultdict(list)
CHAT_DIR = os.path.join(_project_root, "chat")

# ---------------------------------------------------------------------------
# License validation (fully offline)
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
# Resolve GGUF model path
# ---------------------------------------------------------------------------
if not GGUF_PATH:
    _models_dir = os.path.join(_project_root, "models")
    if os.path.isdir(_models_dir):
        for f in os.listdir(_models_dir):
            if f.endswith(".gguf"):
                GGUF_PATH = os.path.join(_models_dir, f)
                break

if not GGUF_PATH or not os.path.isfile(GGUF_PATH):
    print("[Kwyre Air] ERROR: No GGUF model file found.")
    print("[Kwyre Air] Set KWYRE_GGUF_PATH=/path/to/model.gguf")
    print("[Kwyre Air] Or place a .gguf file in the models/ directory.")
    print("[Kwyre Air] To convert a HuggingFace model: python model/convert_gguf.py --help")
    sys.exit(1)

print(f"[Kwyre Air] Loading GGUF model: {GGUF_PATH}")
print(f"[Kwyre Air] Context length: {CTX_LENGTH}")
print(f"[Kwyre Air] Threads: {N_THREADS or 'auto'}")

# ---------------------------------------------------------------------------
# Load model via llama-cpp-python
# ---------------------------------------------------------------------------
try:
    from llama_cpp import Llama
except ImportError:
    print("[Kwyre Air] ERROR: llama-cpp-python not installed.")
    print("[Kwyre Air] Install with: pip install llama-cpp-python")
    sys.exit(1)

t_load = time.time()
llm = Llama(
    model_path=GGUF_PATH,
    n_ctx=CTX_LENGTH,
    n_threads=N_THREADS,
    n_threads_batch=N_THREADS,
    verbose=False,
)
load_elapsed = time.time() - t_load

_gguf_basename = os.path.basename(GGUF_PATH)
_gguf_size_mb = os.path.getsize(GGUF_PATH) / (1024 * 1024)
print(f"[Kwyre Air] Model loaded in {load_elapsed:.1f}s ({_gguf_size_mb:.0f} MB)")

# Inference lock — llama.cpp is not thread-safe for generation
_inference_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Security subsystems
# ---------------------------------------------------------------------------
session_store = SessionStore()
watchdog = IntrusionWatchdog(session_store, terminate_on_intrusion=True)
watchdog.start()

_trial_tracker: dict[str, int] = {}


def _shutdown_handler(signum, frame):
    print("\n[Shutdown] Wiping all sessions before exit...")
    watchdog.stop()
    session_store.wipe_all(reason="server_shutdown")
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

print(f"[Security] Bound to {BIND_HOST}:{PORT} — localhost only")
print(f"[Security] Intrusion watchdog active")
print(f"[Security] Session store active — RAM only, wiped on close")


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class CpuChatHandler(KwyreHandlerMixin, BaseHTTPRequestHandler):

    _api_keys = API_KEYS
    _rate_tracker = rate_tracker
    _rate_limit_rpm = RATE_LIMIT_RPM
    _bind_host = BIND_HOST
    _port = PORT
    _chat_dir = CHAT_DIR

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
                repeat_penalty = min(max(float(body.get("repetition_penalty", 1.1)), 1.0), 2.0)
            except (TypeError, ValueError):
                self._send_json_error(400, "Invalid max_tokens, temperature, or top_p.")
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

            inference_msgs = list(messages)
            if not any(m.get("role") == "system" for m in inference_msgs):
                inference_msgs.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})

            if stream:
                self._handle_stream(inference_msgs, max_tokens, temperature, top_p, repeat_penalty, session_id, session)
            else:
                self._handle_blocking(inference_msgs, max_tokens, temperature, top_p, repeat_penalty, session_id, session)

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
            assert body is not None
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

    def _handle_blocking(self, messages, max_tokens, temperature, top_p, repeat_penalty, session_id, session):
        t0 = time.time()
        with _inference_lock:
            result = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=max(temperature, 0.01),
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                stream=False,
            )
        elapsed = time.time() - t0

        reply = result["choices"][0]["message"]["content"]
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
        reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
        reply = reply.strip()

        usage = result.get("usage", {})
        n_tokens = usage.get("completion_tokens", 0)
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
            "model": MODEL_NAME,
            "session_id": session_id,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": n_tokens,
                "tokens_per_second": round(tps, 1),
            },
        }).encode())

    def _handle_stream(self, messages, max_tokens, temperature, top_p, repeat_penalty, session_id, session):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_security_headers()
        self.end_headers()

        full_reply = []
        t0 = time.time()
        n_tokens = 0

        try:
            with _inference_lock:
                stream = llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=max(temperature, 0.01),
                    top_p=top_p,
                    repeat_penalty=repeat_penalty,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_reply.append(content)
                        n_tokens += 1
                        sse_data = json.dumps({
                            "choices": [{"delta": {"content": content}}],
                            "model": MODEL_NAME,
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
                "model": MODEL_NAME,
                "session_id": session_id,
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

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("chat.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)

        elif self.path == "/health":
            auth_user = self._check_auth_optional()
            health_data: dict = {"status": "ok"}
            if auth_user:
                health_data["model"] = MODEL_NAME
                health_data["backend"] = "llama.cpp (CPU)"
                health_data["gguf_file"] = _gguf_basename
                health_data["gguf_size_mb"] = round(_gguf_size_mb, 1)
                health_data["context_length"] = CTX_LENGTH
                health_data["threads"] = N_THREADS or "auto"
                health_data["security"] = {
                    "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                    "l5_conversation_storage": "RAM-only",
                    "l6_intrusion_watchdog": watchdog.get_status(),
                    "sessions_active": session_store.active_count(),
                }
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
                "server": MODEL_NAME,
                "backend": "llama.cpp (CPU)",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_sessions": session_store.active_count(),
                "security_controls": {
                    "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
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
                    "id": MODEL_NAME,
                    "object": "model",
                    "owned_by": "kwyre",
                    "meta": {
                        "backend": "llama.cpp (CPU)",
                        "gguf_file": _gguf_basename,
                        "quantization": "GGUF (file-level)",
                        "context_length": CTX_LENGTH,
                        "security": {
                            "network": "localhost-only",
                            "storage": "RAM-only sessions",
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

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = ThreadedHTTPServer((BIND_HOST, PORT), CpuChatHandler)
    print(f"\nKwyre Air ready at http://{BIND_HOST}:{PORT}")
    print(f"  Model: {_gguf_basename} ({_gguf_size_mb:.0f} MB)")
    print(f"  Backend: llama.cpp (CPU-only, no GPU required)")
    print(f"  Context: {CTX_LENGTH} tokens | Threads: {N_THREADS or 'auto'}")
    print(f"  POST /v1/chat/completions  — inference (streaming supported)")
    print(f"  POST /v1/session/end       — wipe session from RAM")
    print(f"  GET  /health               — status + watchdog state")
    print(f"  GET  /audit                — metadata-only compliance log")
    print()
    print(f"  [L1] Network: localhost only")
    print(f"  [L5] Storage: RAM-only sessions, wiped on close")
    print(f"  [L6] Watchdog: intrusion detection active")
    print(f"\n  All inference runs 100% locally on CPU. No data leaves this machine.\n")
    server.serve_forever()
