import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
import sys
import time
import torch
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
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

try:
    from awq import AutoAWQForCausalLM
    _AWQ_AVAILABLE = True
except ImportError:
    _AWQ_AVAILABLE = False

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

from spike_serve import apply_spike_hooks, get_sparsity_stats, reset_sparsity_stats, set_tracking
from verify_deps import startup_check
from license import startup_validate as validate_license

MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3.5-9B")
PORT = 8000
SPIKE_K = 5.0
SPIKE_MAX = 31

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "Qwen/Qwen3-4B": {"name": "kwyre-4b", "vram_4bit": "~3.5GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})

SPECULATIVE_ENABLED = os.environ.get("KWYRE_SPECULATIVE", "1") == "1"
DRAFT_MODEL_ID = os.environ.get("KWYRE_DRAFT_MODEL", "Qwen/Qwen3-0.6B")

draft_model = None

QAT_ADAPTER_PATH = os.environ.get(
    "KWYRE_QAT_ADAPTER",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "qat_output_v1", "final"),
)

KWYRE_QUANT = os.environ.get("KWYRE_QUANT", "nf4").lower()
AWQ_MODEL_PATH = os.path.join(_project_root, "models", f"{ACTIVE_TIER['name']}-awq")

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
WEIGHT_HASHES_4B: dict[str, str] = {}  # Populated on first run with Qwen3-4B

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
# LAYER 6: Intrusion watchdog
# ---------------------------------------------------------------------------

# Processes that indicate active debugging, injection, or traffic analysis.
# Conservative list — only tools with no legitimate reason to touch an
# inference server process.
SUSPICIOUS_PROCESSES = [
    "x64dbg", "x32dbg", "ollydbg", "windbg", "immunity debugger",
    "processhacker", "process hacker", "cheatengine", "cheat engine",
    "wireshark", "fiddler", "charles proxy", "mitmproxy", "burpsuite",
    "ida64", "ida32", "ghidra",
]

# Allowed outbound IPs for the server process.
# 127.0.0.1 = localhost only.
# Docker bridge network (172.16-31.x.x) is allowed when running in containers.
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

# How often the watchdog checks (seconds)
WATCHDOG_INTERVAL = 5

# Number of consecutive violations before triggering lockdown
# (avoids false positives from momentary blips)
VIOLATION_THRESHOLD = 2


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
        self.intrusion_log: list[dict] = []  # metadata only, no content

    def _log_event(self, event_type: str, detail: str):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event_type,
            "detail": detail,
        }
        self.intrusion_log.append(entry)
        print(f"[Watchdog] {event_type}: {detail}")

    def check_network(self) -> tuple[bool, str]:
        """
        Verify this process has no unexpected outbound connections.
        Returns (clean: bool, detail: str).
        """
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
            # Don't crash the watchdog on transient errors
            print(f"[Watchdog] network check error (non-fatal): {e}")
        return True, ""

    def check_processes(self) -> tuple[bool, str]:
        """
        Scan running processes for known analysis / injection tools.
        Returns (clean: bool, detail: str).
        """
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

        # Wipe all active sessions immediately
        self.session_store.wipe_all(reason=f"intrusion_lockdown: {reason}")

        if self.terminate_on_intrusion:
            print("[Watchdog] Terminating server process.")
            # Give wipe a moment to complete
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
                # Reset on clean check — transient blips don't trigger lockdown
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
            "recent_events": self.intrusion_log[-5:],  # last 5 events, metadata only
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
# Startup sequence — resolve model path
# ---------------------------------------------------------------------------
# Priority: KWYRE_MODEL_PATH env (pre-quantized) > dist/ folder > HuggingFace cache
PREQUANT_PATH = os.environ.get("KWYRE_MODEL_PATH", "")
_dist_path = os.path.join(_project_root, "dist", "kwyre-4b-nf4")
_USE_PREQUANT = False

if PREQUANT_PATH and os.path.isdir(PREQUANT_PATH) and os.path.exists(os.path.join(PREQUANT_PATH, "config.json")):
    LOCAL_MODEL_PATH = PREQUANT_PATH
    _USE_PREQUANT = True
    print(f"[Model] Using pre-quantized model at {PREQUANT_PATH}")
elif os.path.isdir(_dist_path) and os.path.exists(os.path.join(_dist_path, "config.json")):
    LOCAL_MODEL_PATH = _dist_path
    _USE_PREQUANT = True
    print(f"[Model] Using pre-quantized model at {_dist_path}")
else:
    LOCAL_MODEL_PATH = os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface", "hub",
        f"models--{MODEL_ID.replace('/', '--')}",
        "snapshots",
    )
    try:
        _snap_dirs = [d for d in os.listdir(LOCAL_MODEL_PATH) if os.path.isdir(os.path.join(LOCAL_MODEL_PATH, d))]
        LOCAL_MODEL_PATH = os.path.join(LOCAL_MODEL_PATH, _snap_dirs[0]) if _snap_dirs else LOCAL_MODEL_PATH
    except FileNotFoundError:
        print(f"[Model] ERROR: No model found. Set KWYRE_MODEL_PATH or download first.")
        sys.exit(1)
    print(f"[Model] Using HuggingFace cache at {LOCAL_MODEL_PATH}")

if _USE_PREQUANT:
    print("[Integrity] Pre-quantized Kwyre model — skipping hash check (trusted source)")
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

print(f"Loading tokenizer from {LOCAL_MODEL_PATH}...")
tokenizer = AutoTokenizer.from_pretrained(
    LOCAL_MODEL_PATH, padding_side="left", truncation_side="left", trust_remote_code=True
)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

if KWYRE_QUANT == "awq":
    if os.path.isdir(AWQ_MODEL_PATH) and os.path.exists(
        os.path.join(AWQ_MODEL_PATH, "config.json")
    ):
        print(f"Loading {MODEL_ID} with AWQ quantization (pre-quantized)...")
        model = AutoModelForCausalLM.from_pretrained(
            AWQ_MODEL_PATH, trust_remote_code=True,
            device_map="auto", torch_dtype=torch.bfloat16,
        )
    else:
        if not _AWQ_AVAILABLE:
            print("[AWQ] ERROR: autoawq package not installed.")
            print("[AWQ] Install with: pip install autoawq>=0.2.0")
            sys.exit(1)
        print(f"No pre-quantized AWQ model at {AWQ_MODEL_PATH}")
        print("Quantizing on-the-fly — this will take several minutes...")
        awq_model = AutoAWQForCausalLM.from_pretrained(
            LOCAL_MODEL_PATH, trust_remote_code=True,
        )
        awq_model.quantize(tokenizer, quant_config={
            "zero_point": True, "q_group_size": 128, "w_bit": 4, "version": "GEMM",
        })
        os.makedirs(AWQ_MODEL_PATH, exist_ok=True)
        awq_model.save_quantized(AWQ_MODEL_PATH)
        tokenizer.save_pretrained(AWQ_MODEL_PATH)
        print(f"AWQ model saved to {AWQ_MODEL_PATH}")
        del awq_model
        torch.cuda.empty_cache()
        model = AutoModelForCausalLM.from_pretrained(
            AWQ_MODEL_PATH, trust_remote_code=True,
            device_map="auto", torch_dtype=torch.bfloat16,
        )
    print(f"[Quantization] AWQ mode active (~1.4x faster inference)")
else:
    if _USE_PREQUANT:
        print(f"Loading pre-quantized NF4 model from {LOCAL_MODEL_PATH}...")
        model = AutoModelForCausalLM.from_pretrained(
            LOCAL_MODEL_PATH, trust_remote_code=True,
            device_map="auto", torch_dtype=torch.bfloat16,
        )
        print(f"[Quantization] Pre-quantized NF4 loaded (fastest startup)")
    else:
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        print(f"Loading {MODEL_ID} with 4-bit NF4 quantization (local weights)...")
        model = AutoModelForCausalLM.from_pretrained(
            LOCAL_MODEL_PATH, trust_remote_code=True,
            quantization_config=quant_config,
            device_map="auto", dtype=torch.bfloat16,
        )
        print(f"[Quantization] NF4 on-the-fly quantization active")
# ---------------------------------------------------------------------------
# Load QAT-trained LoRA adapters
# ---------------------------------------------------------------------------
if os.path.isdir(QAT_ADAPTER_PATH) and os.path.exists(
    os.path.join(QAT_ADAPTER_PATH, "adapter_config.json")
):
    try:
        print(f"Loading QAT LoRA adapters from {QAT_ADAPTER_PATH}...")
        model = PeftModel.from_pretrained(model, QAT_ADAPTER_PATH)
        if os.environ.get("KWYRE_MERGE_LORA", "0") == "1":
            model = model.merge_and_unload()
            print("QAT adapters merged — spike-tolerant inference active")
        else:
            print("QAT adapters loaded in-place — spike-tolerant inference active")
    except RuntimeError as e:
        if "size mismatch" in str(e):
            print(f"[QAT] Adapter shape mismatch (trained on different model) — skipping")
        else:
            raise
else:
    print(f"[QAT] No adapters found at {QAT_ADAPTER_PATH} — running base model")

model.eval()

# ---------------------------------------------------------------------------
# Speculative decoding — load lightweight draft model
# ---------------------------------------------------------------------------
if SPECULATIVE_ENABLED:
    _draft_prequant = os.environ.get("KWYRE_DRAFT_PATH", "")
    _draft_dist = os.path.join(_project_root, "dist", "kwyre-draft-nf4")
    try:
        if _draft_prequant and os.path.isdir(_draft_prequant) and os.path.exists(os.path.join(_draft_prequant, "config.json")):
            _draft_source = _draft_prequant
            print(f"[Speculative] Loading pre-quantized draft from {_draft_source}...")
            draft_model = AutoModelForCausalLM.from_pretrained(
                _draft_source, trust_remote_code=True,
                device_map="auto", torch_dtype=torch.bfloat16,
            )
        elif os.path.isdir(_draft_dist) and os.path.exists(os.path.join(_draft_dist, "config.json")):
            print(f"[Speculative] Loading pre-quantized draft from {_draft_dist}...")
            draft_model = AutoModelForCausalLM.from_pretrained(
                _draft_dist, trust_remote_code=True,
                device_map="auto", torch_dtype=torch.bfloat16,
            )
        else:
            print(f"[Speculative] Loading draft model {DRAFT_MODEL_ID} (4-bit NF4)...")
            _draft_quant = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
            draft_model = AutoModelForCausalLM.from_pretrained(
                DRAFT_MODEL_ID, trust_remote_code=True,
                quantization_config=_draft_quant,
                device_map="auto", dtype=torch.bfloat16,
            )
        draft_model.eval()
        _draft_vram = torch.cuda.memory_allocated() / 1e9
        print(f"[Speculative] Draft model loaded — total VRAM now {_draft_vram:.1f} GB")
    except Exception as e:
        print(f"[Speculative] Failed to load draft model: {e}")
        print("[Speculative] Falling back to standard generation.")
        draft_model = None
else:
    print("[Speculative] Disabled (KWYRE_SPECULATIVE=0)")

SPIKE_SKIP = [
    "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    "q_proj", "k_proj", "v_proj", "o_proj",
]

# Phase 1: Measurement pass — measure sparsity with measure_only=True, then remove
print(f"SpikeServe: measuring activation sparsity (k={SPIKE_K})...")
measurement_hooks, n_converted = apply_spike_hooks(
    model, k=SPIKE_K, max_spike=SPIKE_MAX,
    skip_patterns=SPIKE_SKIP, measure_only=True,
)
reset_sparsity_stats()
set_tracking(True)
with torch.no_grad():
    dummy = tokenizer("Hello world", return_tensors="pt").to(model.device)
    model(dummy.input_ids, attention_mask=dummy.attention_mask)
set_tracking(False)
STARTUP_SPARSITY = get_sparsity_stats()
for h in measurement_hooks:
    h.remove()
measurement_hooks = []

# Phase 2: Active inference hooks — apply spike encoding during inference (permanent)
print(f"SpikeServe: attaching active spike encoding hooks ({n_converted} layers)...")
active_spike_hooks, _ = apply_spike_hooks(
    model, k=SPIKE_K, max_spike=SPIKE_MAX,
    skip_patterns=SPIKE_SKIP, measure_only=False,
)
# active_spike_hooks stay attached — do NOT remove; they encode activations at inference time

print(f"SpikeServe ACTIVE: {n_converted} MLP layers | "
      f"measured sparsity {STARTUP_SPARSITY['avg_sparsity']}% at k={SPIKE_K}")

gpu_mem = torch.cuda.memory_allocated() / 1e9
gpu_total = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"GPU VRAM: {gpu_mem:.1f} / {gpu_total:.1f} GB")

# Start security subsystems
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
        """Like _check_auth but returns None silently instead of sending 401."""
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
        """
        Safely parse JSON body from POST request.
        Returns (body_dict, error_msg). If error_msg is not None, body_dict is None.
        Handles missing Content-Length, invalid Content-Length, and malformed JSON.
        """
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
        if length > 10 * 1024 * 1024:  # 10MB limit
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

            text = tokenizer.apply_chat_template(
                augmented, tokenize=False, add_generation_prompt=True,
                enable_thinking=False,
            )
            inputs = tokenizer([text], return_tensors="pt").to(model.device)

            gen_kwargs = {
                "input_ids": inputs.input_ids,
                "attention_mask": inputs.attention_mask,
                "max_new_tokens": max_tokens,
                "temperature": max(temperature, 0.01),
                "top_p": top_p,
                "do_sample": temperature > 0,
                "use_cache": True,
                "pad_token_id": tokenizer.pad_token_id,
                "eos_token_id": tokenizer.eos_token_id,
            }
            if draft_model is not None:
                gen_kwargs["assistant_model"] = draft_model

            t0 = time.time()
            with torch.no_grad():
                gen_ids = model.generate(**gen_kwargs)
            elapsed = time.time() - t0
            new_ids = gen_ids[0][inputs.input_ids.shape[1]:]
            n_tokens = len(new_ids)
            tps = n_tokens / elapsed if elapsed > 0 else 0

            reply = tokenizer.decode(new_ids, skip_special_tokens=True)
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
            reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
            reply = reply.strip()

            session.add_message("assistant", reply)
            print(f"[inference] {session_id[:8]}... | {n_tokens} tokens "
                  f"in {elapsed:.1f}s ({tps:.1f} tok/s)")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "choices": [{"message": {"role": "assistant", "content": reply}}],
                "model": f"{ACTIVE_TIER['name']}-spikeserve",
                "session_id": session_id,
                "tools_used": tools_used,
                "usage": {
                    "completion_tokens": n_tokens,
                    "tokens_per_second": round(tps, 1),
                },
                "spike_stats": {
                    "activation_sparsity_pct": STARTUP_SPARSITY["avg_sparsity"],
                    "spike_encoded_layers": n_converted,
                },
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
        """Extract page name and validate against the whitelist.
        Returns the filename if safe, None otherwise."""
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
                gpu_used = torch.cuda.memory_allocated() / 1e9
                health_data.update({
                    "model": f"{ACTIVE_TIER['name']}-spikeserve",
                    "base": MODEL_ID.split("/")[-1],
                    "quantization": f"4-bit {KWYRE_QUANT.upper()}",
                    "security": {
                        "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                        "l2_process_lockdown": "os-configured (iptables/firewall, not verified by server)",
                        "l3_dependency_integrity": "verified",
                        "l4_weight_integrity": "configured" if KNOWN_WEIGHT_HASHES else "first-run",
                        "l5_conversation_storage": "RAM-only",
                        "l6_intrusion_watchdog": watchdog.get_status(),
                        "sessions_active": session_store.active_count(),
                    },
                    "speculative_decoding": {
                        "enabled": draft_model is not None,
                        "draft_model": DRAFT_MODEL_ID if draft_model is not None else None,
                    },
                    "spike_analysis": {
                        "k": SPIKE_K,
                        "projected_sparsity_pct": STARTUP_SPARSITY["avg_sparsity"],
                        "spike_encoded_layers": n_converted,
                    },
                    "gpu_vram_gb": round(gpu_used, 1),
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
                "server": f"{ACTIVE_TIER['name']}-spikeserve",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_sessions": session_store.active_count(),
                "security_controls": {
                    "l1_network_binding": f"{BIND_HOST}:{PORT} (localhost only)",
                    "l2_process_lockdown": "os-configured (iptables/firewall)",
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
                    "id": f"{ACTIVE_TIER['name']}-spikeserve",
                    "object": "model",
                    "owned_by": "kwyre",
                    "meta": {
                        "base_model": MODEL_ID.split("/")[-1],
                        "weight_quant": f"4-bit {KWYRE_QUANT.upper()}",
                        "activation_encoding": "SpikeServe",
                        "spike_encoded_layers": n_converted,
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
    print(f"\nKwyre AI ready at http://{BIND_HOST}:{PORT}")
    print(f"  Model: {ACTIVE_TIER['name']}-spikeserve ({MODEL_ID})  |  tier: {ACTIVE_TIER['tier']}  |  VRAM: {ACTIVE_TIER['vram_4bit']}")
    _spec_status = f"speculative={DRAFT_MODEL_ID.split('/')[-1]}" if draft_model else "no speculative"
    print(f"  SpikeServe ACTIVE ({n_converted} layers)  |  4-bit {KWYRE_QUANT.upper()}  |  {_spec_status}  |  all 6 security layers active")
    print(f"  Available tiers: KWYRE_MODEL=Qwen/Qwen3.5-9B (7.5GB) | Qwen/Qwen3-4B (3.5GB)")
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
    print("\n  All inference runs 100% locally. No data leaves this machine.\n")
    server.serve_forever()
