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
import secrets
import sys
import json
import time
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_server_dir)
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_project_root, "security"))

TOOLS_ENABLED = os.environ.get("KWYRE_ENABLE_TOOLS", "0") == "1"
if TOOLS_ENABLED:
    sys.path.insert(0, _server_dir)
    from tools import route_tools
else:
    def route_tools(_msg):
        return [], []

from security_core import (
    BIND_HOST,
    SessionStore,
    IntrusionWatchdog,
    load_api_keys,
    RATE_LIMIT_RPM_DEFAULT,
    KwyreHandlerMixin,
)

from license import startup_validate as validate_license
from audit import UserAuditLog

audit_log = UserAuditLog()

from rag import SecureRAGStore, DocumentParser, encode_texts

rag_store = SecureRAGStore()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are Kwyre Air, a local AI assistant optimized for lightweight CPU inference. "
    "You provide clear, concise answers. Keep responses focused and well-organized. "
    "When analyzing documents or regulations, use numbered points and specific references. "
    "You never fabricate citations. If uncertain, say so."
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

_gguf_base = os.path.splitext(os.path.basename(GGUF_PATH))[0]
MODEL_NAME = os.environ.get("KWYRE_MODEL_NAME", f"{_gguf_base}-air" if _gguf_base else "kwyre-air")

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
    print("\n[Shutdown] Wiping all sessions and documents before exit...")
    watchdog.stop()
    rag_store.wipe_all(reason="server_shutdown")
    session_store.wipe_all(reason="server_shutdown")
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

print(f"[Security] Bound to {BIND_HOST}:{PORT} — localhost only")
print("[Security] Intrusion watchdog active")
print("[Security] Session store active — RAM only, wiped on close")


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
            self._current_user = user
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
                top_k = min(max(int(body.get("top_k", 40)), 0), 100)
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

            tool_data, tools_used = [], []
            last_user_msg = next(
                (m.get("content", "") for m in reversed(inference_msgs) if m.get("role") == "user"), ""
            )
            if last_user_msg:
                try:
                    tool_data, tools_used = route_tools(last_user_msg)
                except Exception as e:
                    print(f"[tools] error: {e}")

            rag_chunks = []
            if rag_store.has_documents(session_id):
                try:
                    query_emb = encode_texts([last_user_msg])
                    if query_emb is not None:
                        rag_chunks = rag_store.retrieve(session_id, query_emb[0])
                except Exception as e:
                    print(f"[RAG] retrieval error: {e}")

            ctx_parts = []
            if tool_data:
                ctx_parts.append("[Live data]\n\n" + "\n\n".join(tool_data))
            if rag_chunks:
                ctx_parts.append("[Retrieved document context]\n\n" + "\n\n---\n\n".join(rag_chunks))
            if ctx_parts:
                ctx = "\n\n" + "\n\n".join(ctx_parts)
                for i in range(len(inference_msgs) - 1, -1, -1):
                    if inference_msgs[i].get("role") == "user":
                        inference_msgs[i] = {"role": "user", "content": inference_msgs[i]["content"] + ctx}
                        break

            if stream:
                self._handle_stream(inference_msgs, max_tokens, temperature, top_p, repeat_penalty, top_k, session_id, session, tools_used)
            else:
                self._handle_blocking(inference_msgs, max_tokens, temperature, top_p, repeat_penalty, top_k, session_id, session, tools_used)

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

        elif self.path == "/v1/analytics/predict":
            user = self._check_auth()
            if user is None:
                return
            body, err = self._parse_json_body(required=True)
            if err is not None:
                self._send_json_error(400, err)
                return
            try:
                from analytics import route_analytics
                result = route_analytics("predict", body)
                self._send_json(200, result)
            except Exception as e:
                self._send_json_error(500, f"Analytics error: {e}")

        elif self.path == "/v1/analytics/risk":
            user = self._check_auth()
            if user is None:
                return
            body, err = self._parse_json_body(required=True)
            if err is not None:
                self._send_json_error(400, err)
                return
            try:
                from analytics import route_analytics
                result = route_analytics("risk", body)
                self._send_json(200, result)
            except Exception as e:
                self._send_json_error(500, f"Analytics error: {e}")

        elif self.path == "/v1/documents/upload":
            user = self._check_auth()
            if user is None:
                return
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json_error(400, "Content-Type must be multipart/form-data")
                return
            boundary = content_type.split("boundary=")[-1].strip()
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 50 * 1024 * 1024:
                self._send_json_error(400, "File size exceeds 50MB limit")
                return
            body = self.rfile.read(content_length)
            parts = body.split(f"--{boundary}".encode())
            session_id = None
            files = []
            for part in parts:
                if b"Content-Disposition" not in part:
                    continue
                header_end = part.find(b"\r\n\r\n")
                if header_end == -1:
                    continue
                headers_raw = part[:header_end].decode("utf-8", errors="replace")
                file_data = part[header_end + 4:]
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                if 'name="session_id"' in headers_raw:
                    session_id = file_data.decode("utf-8", errors="replace").strip()
                elif 'name="file"' in headers_raw or "filename=" in headers_raw:
                    fname_match = re.search(r'filename="([^"]+)"', headers_raw)
                    if fname_match:
                        files.append((fname_match.group(1), file_data))
            if not session_id or len(session_id) < 32:
                session_id = secrets.token_hex(16)
            if not files:
                self._send_json_error(400, "No files provided")
                return
            total_chunks = 0
            filenames = []
            for fname, fdata in files:
                try:
                    chunks = DocumentParser.parse(fname, fdata)
                    if chunks:
                        embeddings = encode_texts(chunks)
                        if embeddings is not None:
                            rag_store.add_documents(session_id, chunks, embeddings, {"filename": fname})
                            total_chunks += len(chunks)
                            filenames.append(fname)
                except Exception as e:
                    print(f"[RAG] Error processing {fname}: {e}")
            self._send_json(200, {
                "status": "indexed",
                "session_id": session_id,
                "files": filenames,
                "chunks": total_chunks,
                "message": f"Indexed {total_chunks} chunks from {len(filenames)} file(s). Data stored in RAM only."
            })

        elif self.path == "/v1/adapter/load":
            self._send_json_error(501, "Adapter hot-swap is not supported on the CPU (llama.cpp) backend. Use the GPU backend for adapter support.")

        elif self.path == "/v1/adapter/unload":
            self._send_json_error(501, "Adapter hot-swap is not supported on the CPU (llama.cpp) backend.")

        elif self.path == "/v1/adapter/stack":
            self._send_json_error(501, "Adapter stacking is not supported on the CPU (llama.cpp) backend.")

        else:
            self._send_json_error(404, "Not found.")

    def _handle_blocking(self, messages, max_tokens, temperature, top_p, repeat_penalty, top_k, session_id, session, tools_used):
        t0 = time.time()
        with _inference_lock:
            result = llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=max(temperature, 0.01),
                top_p=top_p,
                top_k=top_k,
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
        audit_log.record_request(self._current_user, self._current_user, tokens=n_tokens)
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
            "tools_used": tools_used,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": n_tokens,
                "tokens_per_second": round(tps, 1),
            },
        }).encode())

    def _handle_stream(self, messages, max_tokens, temperature, top_p, repeat_penalty, top_k, session_id, session, tools_used):
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
                    top_k=top_k,
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
            audit_log.record_request(self._current_user, self._current_user, tokens=n_tokens)

            done_data = json.dumps({
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "model": MODEL_NAME,
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

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("main.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)

        elif self.path == "/health":
            auth_user = self._check_auth_optional()
            health_data: dict = {"status": "ok"}
            if auth_user:
                health_data["model"] = MODEL_NAME
                health_data["product"] = "Kwyre Air"
                health_data["description"] = "CPU-only inference — no GPU required"
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
                        "product": "Kwyre Air",
                        "capabilities": ["streaming", "session_wipe", "crypto_wipe", "tools"],
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

        elif self.path == "/v1/adapter/list":
            user = self._check_auth()
            if user is None:
                return
            try:
                manifest_path = os.path.join(_project_root, "chat", "adapters", "manifest.json")
                with open(manifest_path) as f:
                    manifest = json.load(f)
                self._send_json(200, {"adapters": manifest, "active_adapter": None, "backend": "cpu"})
            except Exception:
                self._send_json(200, {"adapters": {}, "active_adapter": None, "backend": "cpu"})

        elif self.path == "/v1/adapter/status":
            self._send_json(200, {"active_adapter": None, "backend": "cpu", "adapter_swap_enabled": False})

        elif self.path == "/v1/adapter/check-update":
            self._send_json(200, {"updates_available": {}, "up_to_date": True, "backend": "cpu"})

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
    print(f"\n{'='*60}")
    print("  KWYRE AIR — CPU-Only Inference")
    print("  No GPU required. Runs on any hardware.")
    print(f"{'='*60}")
    print(f"  Model:   {_gguf_basename} ({_gguf_size_mb:.0f} MB)")
    print(f"  Backend: llama.cpp | Context: {CTX_LENGTH} | Threads: {N_THREADS or 'auto'}")
    print(f"  URL:     http://{BIND_HOST}:{PORT}")
    print()
    print("  Endpoints:")
    print("    POST /v1/chat/completions  — inference (streaming supported)")
    print("    POST /v1/session/end       — cryptographic session wipe")
    print("    POST /v1/analytics/predict    — time series forecasting")
    print("    POST /v1/analytics/risk       — VaR/CVaR risk analysis")
    print("    GET  /health               — system status")
    print("    GET  /audit                — compliance log")
    print()
    print("  Security:")
    print("    [L1] Network: localhost only")
    print("    [L5] Storage: RAM-only, crypto-wiped on close")
    print("    [L6] Watchdog: intrusion detection active")
    if TOOLS_ENABLED:
        print("    [Tools] ENABLED (NOT air-gapped)")
    else:
        print("    [Tools] DISABLED — fully air-gapped")
    print("\n  All inference runs 100% on CPU. No data leaves this machine.\n")
    server.serve_forever()
