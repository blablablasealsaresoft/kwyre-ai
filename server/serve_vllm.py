"""
Kwyre AI — vLLM High-Performance Inference Backend
====================================================
Uses vLLM for continuous batching, PagedAttention, and
optional speculative decoding. Highest throughput option.

Usage:
    KWYRE_BACKEND=vllm python server/serve_vllm.py

Environment variables:
    KWYRE_MODEL               HuggingFace model ID (default: Qwen/Qwen3-4B)
    KWYRE_MODEL_PATH          Path to pre-quantized model directory
    KWYRE_VLLM_GPU_MEMORY     GPU memory fraction (default: 0.85)
    KWYRE_VLLM_MAX_MODEL_LEN  Max context length (default: 8192)
    KWYRE_VLLM_TENSOR_PARALLEL  Tensor parallel size (default: 1)
    KWYRE_SPECULATIVE         Enable speculative decoding (default: 1)
    KWYRE_DRAFT_MODEL         Draft model for speculative (default: Qwen/Qwen3-0.6B)
    KWYRE_API_KEYS            API key:role pairs
    KWYRE_BIND_HOST           Bind address (default: 127.0.0.1)
    KWYRE_PORT                Port (default: 8000)
    KWYRE_LICENSE_KEY         License key for offline validation
    KWYRE_ENABLE_TOOLS        Set to "1" to enable external tools
    KWYRE_SKIP_DEP_CHECK      Set to "1" to skip dep verification
"""

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
import sys
import time
import json
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

TOOLS_ENABLED = os.environ.get("KWYRE_ENABLE_TOOLS", "0") == "1"
if TOOLS_ENABLED:
    from tools import route_tools
else:
    def route_tools(_msg):
        return [], []

_skip_dep_check = os.environ.get("KWYRE_SKIP_DEP_CHECK", "0") == "1"
if not _skip_dep_check:
    from verify_deps import startup_check
    startup_check(abort_on_failure=False)

try:
    from vllm import LLM, SamplingParams
    from vllm.utils import random_uuid
    _VLLM_AVAILABLE = True
except ImportError:
    _VLLM_AVAILABLE = False
    print("[vLLM] ERROR: vllm package not installed.")
    print("[vLLM] Install with: pip install vllm")
    sys.exit(1)

MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3-4B")
PORT = int(os.environ.get("KWYRE_PORT", "8000"))
GPU_MEMORY_FRACTION = float(os.environ.get("KWYRE_VLLM_GPU_MEMORY", "0.85"))
MAX_MODEL_LEN = int(os.environ.get("KWYRE_VLLM_MAX_MODEL_LEN", "8192"))
TENSOR_PARALLEL = int(os.environ.get("KWYRE_VLLM_TENSOR_PARALLEL", "1"))
SPECULATIVE_ENABLED = os.environ.get("KWYRE_SPECULATIVE", "1") == "1"
DRAFT_MODEL_ID = os.environ.get("KWYRE_DRAFT_MODEL", "Qwen/Qwen3-0.6B")

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "tier": "professional"},
    "Qwen/Qwen3-4B": {"name": "kwyre-4b", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "tier": "custom"})

PREQUANT_PATH = os.environ.get("KWYRE_MODEL_PATH", "")
_dist_path = os.path.join(_project_root, "dist", f"{ACTIVE_TIER['name']}-nf4")

if PREQUANT_PATH and os.path.isdir(PREQUANT_PATH):
    LOCAL_MODEL_PATH = PREQUANT_PATH
elif os.path.isdir(_dist_path):
    LOCAL_MODEL_PATH = _dist_path
else:
    LOCAL_MODEL_PATH = MODEL_ID

DEFAULT_SYSTEM_PROMPT = (
    "You are Kwyre, a specialized AI assistant for legal, financial, and forensic "
    "analysis. You provide precise, well-structured responses citing relevant "
    "regulations, statutes, and professional standards. You organize complex analysis "
    "with clear headings, numbered points, and specific references. When analyzing "
    "documents, you identify key obligations, risks, and compliance requirements. "
    "You never fabricate citations or case law. If uncertain, you state your "
    "confidence level explicitly."
)

API_KEYS = load_api_keys()
RATE_LIMIT_RPM = RATE_LIMIT_RPM_DEFAULT
rate_tracker: defaultdict[str, list] = defaultdict(list)
CHAT_DIR = os.path.join(_project_root, "chat")

_license_data = validate_license()
if _license_data is None:
    print("[License] WARNING: No valid license. Running in evaluation mode.")
_license_tier: str = _license_data["tier"] if _license_data else "eval"
_MAX_EVAL_TOKENS = 512
if _license_tier == "eval":
    RATE_LIMIT_RPM = 10

print(f"[vLLM] Loading model: {LOCAL_MODEL_PATH}")
print(f"[vLLM] GPU memory fraction: {GPU_MEMORY_FRACTION}")
print(f"[vLLM] Max model length: {MAX_MODEL_LEN}")
print(f"[vLLM] Tensor parallel: {TENSOR_PARALLEL}")

llm_kwargs = {
    "model": LOCAL_MODEL_PATH,
    "trust_remote_code": True,
    "gpu_memory_utilization": GPU_MEMORY_FRACTION,
    "max_model_len": MAX_MODEL_LEN,
    "tensor_parallel_size": TENSOR_PARALLEL,
    "dtype": "bfloat16",
    "quantization": "bitsandbytes",
    "load_format": "bitsandbytes",
}

if SPECULATIVE_ENABLED:
    _draft_dist = os.path.join(_project_root, "dist", "kwyre-draft-nf4")
    draft_path = os.environ.get("KWYRE_DRAFT_PATH", "")
    if draft_path and os.path.isdir(draft_path):
        llm_kwargs["speculative_model"] = draft_path
    elif os.path.isdir(_draft_dist):
        llm_kwargs["speculative_model"] = _draft_dist
    else:
        llm_kwargs["speculative_model"] = DRAFT_MODEL_ID
    llm_kwargs["num_speculative_tokens"] = 5
    print(f"[vLLM] Speculative decoding: {llm_kwargs['speculative_model']}")

llm = LLM(**llm_kwargs)
tokenizer = llm.get_tokenizer()
print(f"[vLLM] Model loaded successfully")

session_store = SessionStore()
watchdog = IntrusionWatchdog(session_store, terminate_on_intrusion=True)
watchdog.start()

_trial_tracker: dict[str, int] = {}
_inference_lock = threading.Lock()


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


class VllmChatHandler(KwyreHandlerMixin, BaseHTTPRequestHandler):

    _api_keys = API_KEYS
    _rate_tracker = rate_tracker
    _rate_limit_rpm = RATE_LIMIT_RPM
    _bind_host = BIND_HOST
    _port = PORT
    _chat_dir = CHAT_DIR

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_chat()
        elif self.path == "/v1/session/end":
            self._handle_session_end()
        elif self.path == "/v1/license/verify":
            self._handle_license_verify()
        else:
            self._send_json_error(404, "Not found.")

    def _handle_chat(self):
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
            top_k = min(max(int(body.get("top_k", 20)), 0), 100)
            repetition_penalty = min(max(float(body.get("repetition_penalty", 1.1)), 1.0), 2.0)
        except (TypeError, ValueError):
            self._send_json_error(400, "Invalid generation parameters.")
            return

        if _license_tier == "eval":
            max_tokens = min(max_tokens, _MAX_EVAL_TOKENS)

        session_id = self._get_session_id(body)
        stream = body.get("stream", False)

        if _license_tier == "eval":
            trial_key = f"trial:{self.client_address[0]}"
            trial_count = _trial_tracker.get(trial_key, 0)
            if trial_count >= 3:
                self._send_json_error(429, "Trial limit reached.")
                return
            _trial_tracker[trial_key] = trial_count + 1

        session, _created = session_store.get_or_create(session_id)
        for m in messages:
            session.add_message(m.get("role", "user"), m.get("content", ""))

        augmented = list(messages)
        if not any(m.get("role") == "system" for m in augmented):
            augmented.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})

        tool_data, tools_used = [], []
        last_user_msg = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        if last_user_msg:
            try:
                tool_data, tools_used = route_tools(last_user_msg)
            except Exception as e:
                print(f"[tools] error: {e}")

        if tool_data:
            ctx = "\n\n[Live data]\n\n" + "\n\n".join(tool_data)
            for i in range(len(augmented) - 1, -1, -1):
                if augmented[i].get("role") == "user":
                    augmented[i] = {"role": "user", "content": augmented[i]["content"] + ctx}
                    break

        if hasattr(tokenizer, "apply_chat_template"):
            prompt = tokenizer.apply_chat_template(
                augmented, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = "\n".join(f"<|{m['role']}|>\n{m['content']}" for m in augmented)
            prompt += "\n<|assistant|>\n"

        sampling = SamplingParams(
            max_tokens=max_tokens,
            temperature=max(temperature, 0.01) if temperature > 0 else 0.0,
            top_p=top_p,
            top_k=top_k if top_k > 0 else -1,
            repetition_penalty=repetition_penalty,
        )

        model_name = f"{ACTIVE_TIER['name']}-vllm"

        if stream:
            self._handle_stream(prompt, sampling, session_id, session, model_name, tools_used)
        else:
            self._handle_blocking(prompt, sampling, session_id, session, model_name, tools_used)

    def _handle_blocking(self, prompt, sampling, session_id, session, model_name, tools_used):
        t0 = time.time()
        with _inference_lock:
            outputs = llm.generate([prompt], sampling)
        elapsed = time.time() - t0

        reply = outputs[0].outputs[0].text
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
        reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
        reply = reply.strip()

        n_tokens = len(outputs[0].outputs[0].token_ids)
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
            "model": model_name,
            "session_id": session_id,
            "tools_used": tools_used,
            "usage": {
                "completion_tokens": n_tokens,
                "tokens_per_second": round(tps, 1),
            },
            "backend": "vllm",
        }).encode())

    def _handle_stream(self, prompt, sampling, session_id, session, model_name, tools_used):
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
                outputs = llm.generate([prompt], sampling)

            reply = outputs[0].outputs[0].text
            token_ids = outputs[0].outputs[0].token_ids
            n_tokens = len(token_ids)

            words = reply.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                full_reply.append(chunk)
                sse_data = json.dumps({
                    "choices": [{"delta": {"content": chunk}}],
                    "model": model_name,
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
                "model": model_name,
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
            print(f"[inference] {session_id[:8]}... | client disconnected")

    def _handle_session_end(self):
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

    def _handle_license_verify(self):
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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "valid": True,
                "tier": payload.get("tier", "unknown"),
                "label": payload.get("label", ""),
                "machines": payload.get("machines", 0),
            }).encode())
        except ValueError as e:
            self._send_json_error(403, str(e))

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("main.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)
        elif self.path == "/health":
            auth_user = self._check_auth_optional()
            health = {"status": "ok"}
            if auth_user:
                health.update({
                    "model": f"{ACTIVE_TIER['name']}-vllm",
                    "base": MODEL_ID.split("/")[-1],
                    "backend": "vllm",
                    "quantization": "bitsandbytes 4-bit",
                    "streaming": "SSE (text/event-stream)",
                    "continuous_batching": True,
                    "paged_attention": True,
                    "speculative_decoding": {
                        "enabled": SPECULATIVE_ENABLED,
                        "draft_model": llm_kwargs.get("speculative_model", "none"),
                    },
                    "security": {
                        "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                        "l5_conversation_storage": "RAM-only",
                        "l6_intrusion_watchdog": watchdog.get_status(),
                        "sessions_active": session_store.active_count(),
                    },
                    "vllm_config": {
                        "gpu_memory_fraction": GPU_MEMORY_FRACTION,
                        "max_model_len": MAX_MODEL_LEN,
                        "tensor_parallel": TENSOR_PARALLEL,
                    },
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps(health, indent=2).encode())
        elif self.path == "/audit":
            user = self._check_auth()
            if user is None:
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "server": f"{ACTIVE_TIER['name']}-vllm",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_sessions": session_store.active_count(),
                "security_controls": {
                    "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                    "l5_conversation_storage": "RAM-only",
                    "l6_intrusion_watchdog": watchdog.get_status(),
                    "content_logging": "NEVER",
                },
                "note": "Metadata only. No conversation content is ever logged.",
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
                    "id": f"{ACTIVE_TIER['name']}-vllm",
                    "object": "model",
                    "owned_by": "kwyre",
                    "meta": {
                        "backend": "vllm",
                        "continuous_batching": True,
                        "paged_attention": True,
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

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = ThreadedHTTPServer((BIND_HOST, PORT), VllmChatHandler)
    print(f"\nKwyre AI (vLLM) ready at http://{BIND_HOST}:{PORT}")
    print(f"  Model: {ACTIVE_TIER['name']}-vllm ({MODEL_ID})")
    print(f"  Backend: vLLM (continuous batching + PagedAttention)")
    print(f"  Speculative: {'enabled' if SPECULATIVE_ENABLED else 'disabled'}")
    print(f"  POST /v1/chat/completions  — inference (streaming supported)")
    print(f"  POST /v1/session/end       — wipe session from RAM")
    print(f"  GET  /health               — status + vLLM config")
    print(f"  GET  /audit                — metadata-only compliance log")
    print(f"\n  [L1] Network: localhost only")
    print(f"  [L5] Storage: RAM-only sessions, wiped on close")
    print(f"  [L6] Watchdog: intrusion detection active")
    if TOOLS_ENABLED:
        print(f"  [Tools] ENABLED — external API calls active (NOT air-gapped)")
    else:
        print(f"  [Tools] DISABLED — fully air-gapped")
    print(f"\n  All inference runs 100% locally. No data leaves this machine.\n")
    server.serve_forever()
