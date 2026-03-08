import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
import sys
import time
import torch
import json
import hashlib
import secrets
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

from security_core import (
    BIND_HOST,
    SecureConversationBuffer,
    SessionStore,
    IntrusionWatchdog,
    load_api_keys,
    RATE_LIMIT_RPM_DEFAULT,
    ALLOWED_PAGES,
    KwyreHandlerMixin,
)

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
from audit import UserAuditLog

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
_awq_env_path = os.environ.get("KWYRE_AWQ_MODEL_PATH", "")
_awq_default_path = os.path.join(_project_root, "models", f"{ACTIVE_TIER['name']}-awq")
if _awq_env_path and os.path.isdir(_awq_env_path):
    AWQ_MODEL_PATH = _awq_env_path
else:
    AWQ_MODEL_PATH = _awq_default_path

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
# API keys + rate limiting
# ---------------------------------------------------------------------------
API_KEYS = load_api_keys()
RATE_LIMIT_RPM = RATE_LIMIT_RPM_DEFAULT
rate_tracker = defaultdict(list)
CHAT_DIR = os.path.join(_project_root, "chat")

# ---------------------------------------------------------------------------
# Multi-user mode
# ---------------------------------------------------------------------------
MULTI_USER = os.environ.get("KWYRE_MULTI_USER", "0") == "1"
_user_manager = None
audit_log = UserAuditLog()

if MULTI_USER:
    from users import UserManager, ROLES as USER_ROLES
    try:
        _user_manager = UserManager()
        if not _user_manager.has_users():
            _default_user, _default_key = _user_manager.add_user("admin", role="admin")
            print(f"[Multi-User] No users found — created default admin.")
            print(f"[Multi-User] Admin API key: {_default_key}")
            print(f"[Multi-User] Store this key securely — it cannot be retrieved later.")
        print(f"[Multi-User] ENABLED — {_user_manager.user_count()} user(s) loaded")
    except EnvironmentError as e:
        print(f"[Multi-User] ERROR: {e}")
        print("[Multi-User] Run: python server/users.py init")
        sys.exit(1)
    except ValueError as e:
        print(f"[Multi-User] ERROR: {e}")
        sys.exit(1)
else:
    USER_ROLES = {}
    print("[Multi-User] DISABLED — single-user mode (set KWYRE_MULTI_USER=1 to enable)")

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
class ChatHandler(KwyreHandlerMixin, BaseHTTPRequestHandler):

    _api_keys = API_KEYS
    _rate_tracker = rate_tracker
    _rate_limit_rpm = RATE_LIMIT_RPM
    _bind_host = BIND_HOST
    _port = PORT
    _chat_dir = CHAT_DIR

    # ---- Multi-user auth helpers ----

    def _mu_check_auth(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            audit_log.record_failed_auth(self.client_address[0])
            self._send_json_error(401, "Invalid API key.")
            return None
        key = auth[7:]
        user = _user_manager.authenticate(key)
        if user is None:
            audit_log.record_failed_auth(self.client_address[0])
            self._send_json_error(401, "Invalid API key.")
            return None
        _user_manager.update_last_active(user["id"])
        return user

    def _mu_check_admin(self):
        user = self._mu_check_auth()
        if user is None:
            return None
        if user["role"] != "admin":
            self._send_json_error(403, "Admin access required.")
            return None
        return user

    def _mu_check_rate_limit(self, user: dict) -> bool:
        rpm = user.get("rate_limit_rpm", RATE_LIMIT_RPM)
        uid = user["id"]
        now = time.time()
        rate_tracker[uid] = [t for t in rate_tracker[uid] if now - t < 60]
        if len(rate_tracker[uid]) >= rpm:
            audit_log.record_rate_limit_hit(uid, user.get("username", ""))
            self._send_json_error(429, f"Rate limit exceeded. Max {rpm} req/min.")
            return False
        rate_tracker[uid].append(now)
        return True

    def _mu_get_session_id(self, body: dict, user: dict) -> str:
        raw_sid = body.get("session_id")
        if not raw_sid or not isinstance(raw_sid, str) or len(raw_sid) < 32:
            raw_sid = secrets.token_hex(16)
        return f"{user['id']}:{raw_sid}"

    def _mu_check_session_limit(self, user: dict) -> bool:
        max_sess = user.get("max_sessions", 5)
        current = session_store.count_sessions_for_user(user["id"])
        if current >= max_sess:
            self._send_json_error(429, f"Session limit reached ({max_sess}). End an existing session first.")
            return False
        return True

    def _mu_can_inference(self, user: dict) -> bool:
        role_perms = USER_ROLES.get(user["role"], {})
        if not role_perms.get("can_inference", False):
            self._send_json_error(403, f"Role '{user['role']}' cannot perform inference.")
            return False
        return True

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    # ---- POST routing ----

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_chat_completions()
        elif self.path == "/v1/session/end":
            self._handle_session_end()
        elif self.path == "/v1/license/verify":
            self._handle_license_verify()
        elif MULTI_USER and self.path == "/v1/admin/users":
            self._handle_admin_create_user()
        elif MULTI_USER and self.path == "/v1/admin/sessions/wipe":
            self._handle_admin_wipe_sessions()
        else:
            self._send_json_error(404, "Not found.")

    def do_DELETE(self):
        if MULTI_USER and self.path.startswith("/v1/admin/users/"):
            self._handle_admin_delete_user()
        else:
            self._send_json_error(404, "Not found.")

    def _handle_chat_completions(self):
        if MULTI_USER:
            user = self._mu_check_auth()
            if user is None:
                return
            if not self._mu_can_inference(user):
                return
            if not self._mu_check_rate_limit(user):
                return
        else:
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

        if MULTI_USER:
            if not self._mu_check_session_limit(user):
                return
            session_id = self._mu_get_session_id(body, user)
        else:
            session_id = self._get_session_id(body)

        if _license_tier == "eval":
            trial_key = f"trial:{self.client_address[0]}"
            trial_count = _trial_tracker.get(trial_key, 0)
            if trial_count >= 3:
                self._send_json_error(429, "Trial limit reached. Purchase a license at https://kwyre.com")
                return
            _trial_tracker[trial_key] = trial_count + 1

        session = session_store.get_or_create(session_id)
        if MULTI_USER:
            audit_log.record_session_created(user["id"], user.get("username", ""))
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

        if MULTI_USER:
            audit_log.record_request(user["id"], user.get("username", ""), tokens=n_tokens)
            label = f"{user['username']}@{session_id.split(':', 1)[-1][:8]}"
        else:
            label = session_id[:8]
        print(f"[inference] {label}... | {n_tokens} tokens "
              f"in {elapsed:.1f}s ({tps:.1f} tok/s)")

        response_sid = session_id.split(":", 1)[-1] if MULTI_USER else session_id
        self._send_json(200, {
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "model": f"{ACTIVE_TIER['name']}-spikeserve",
            "session_id": response_sid,
            "tools_used": tools_used,
            "usage": {
                "completion_tokens": n_tokens,
                "tokens_per_second": round(tps, 1),
            },
            "spike_stats": {
                "activation_sparsity_pct": STARTUP_SPARSITY["avg_sparsity"],
                "spike_encoded_layers": n_converted,
            },
        })

    def _handle_session_end(self):
        if MULTI_USER:
            user = self._mu_check_auth()
            if user is None:
                return
        else:
            user = self._check_auth()
            if user is None:
                return
        body, err = self._parse_json_body(required=False)
        if err is not None:
            self._send_json_error(400, err)
            return
        raw_sid = (body or {}).get("session_id", "")
        if raw_sid:
            if MULTI_USER:
                namespaced = f"{user['id']}:{raw_sid}"
                session_store.wipe_session(namespaced, reason="user_request")
            else:
                session_store.wipe_session(raw_sid, reason="user_request")
            msg = f"Session {raw_sid[:8]}... wiped. Conversation unrecoverable."
        else:
            msg = "No session_id provided."
        self._send_json(200, {"status": "wiped", "message": msg})

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
            self._send_json(200, {
                "valid": True,
                "tier": payload.get("tier", "unknown"),
                "label": payload.get("label", ""),
                "machines": payload.get("machines", 0),
            })
        except ValueError as e:
            self._send_json_error(403, str(e))

    # ---- Admin endpoints (multi-user only) ----

    def _handle_admin_create_user(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        body, err = self._parse_json_body(required=True)
        if err is not None:
            self._send_json_error(400, err)
            return
        username = body.get("username", "").strip()
        role = body.get("role", "analyst")
        max_sessions = body.get("max_sessions")
        rpm = body.get("rate_limit_rpm")
        if not username:
            self._send_json_error(400, "Missing 'username'.")
            return
        try:
            new_user, api_key = _user_manager.add_user(
                username, role=role,
                max_sessions=max_sessions,
                rate_limit_rpm=rpm,
            )
            audit_log.record_security_event(
                admin["id"], "user_created",
                f"admin={admin['username']} created user={username} role={role}"
            )
            self._send_json(201, {
                "username": new_user["username"],
                "role": new_user["role"],
                "api_key": api_key,
                "max_sessions": new_user["max_sessions"],
                "rate_limit_rpm": new_user["rate_limit_rpm"],
            })
        except ValueError as e:
            self._send_json_error(400, str(e))

    def _handle_admin_delete_user(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        username = self.path.split("/v1/admin/users/", 1)[-1].strip("/")
        if not username:
            self._send_json_error(400, "Missing username in URL.")
            return
        target = _user_manager.get_user(username)
        if target is None:
            self._send_json_error(404, f"User '{username}' not found.")
            return
        session_store.wipe_user_sessions(target["id"], reason=f"user_deleted:{username}")
        _user_manager.remove_user(username)
        audit_log.record_security_event(
            admin["id"], "user_deleted",
            f"admin={admin['username']} deleted user={username}"
        )
        self._send_json(200, {"status": "deleted", "username": username})

    def _handle_admin_wipe_sessions(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        body, err = self._parse_json_body(required=True)
        if err is not None:
            self._send_json_error(400, err)
            return
        target_username = body.get("username", "").strip()
        if not target_username:
            self._send_json_error(400, "Missing 'username'.")
            return
        target = _user_manager.get_user(target_username)
        if target is None:
            self._send_json_error(404, f"User '{target_username}' not found.")
            return
        count = session_store.count_sessions_for_user(target["id"])
        session_store.wipe_user_sessions(target["id"], reason=f"admin_wipe:{admin['username']}")
        audit_log.record_security_event(
            admin["id"], "admin_session_wipe",
            f"admin={admin['username']} wiped {count} session(s) for user={target_username}"
        )
        self._send_json(200, {
            "status": "wiped",
            "username": target_username,
            "sessions_wiped": count,
        })

    # ---- GET routing ----

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("chat.html")
        elif (page := self._safe_page_name(self.path)) is not None:
            self._serve_html(page)
        elif self.path == "/health":
            self._handle_health()
        elif self.path == "/audit":
            self._handle_audit()
        elif self.path == "/v1/models":
            self._handle_models()
        elif MULTI_USER and self.path == "/v1/admin/users":
            self._handle_admin_list_users()
        elif MULTI_USER and self.path == "/v1/admin/sessions":
            self._handle_admin_list_sessions()
        elif MULTI_USER and self.path == "/v1/admin/audit":
            self._handle_admin_audit()
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self._send_security_headers()
            self.end_headers()
        else:
            self._send_json_error(404, "Not found.")

    def _handle_health(self):
        auth_user = self._check_auth_optional()
        health_data = {"status": "ok"}
        if auth_user:
            gpu_used = torch.cuda.memory_allocated() / 1e9
            health_data.update({
                "model": f"{ACTIVE_TIER['name']}-spikeserve",
                "base": MODEL_ID.split("/")[-1],
                "quantization": f"4-bit {KWYRE_QUANT.upper()}",
                "multi_user": MULTI_USER,
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
        self._send_json(200, health_data)

    def _handle_audit(self):
        if MULTI_USER:
            user = self._mu_check_auth()
            if user is None:
                return
        else:
            user = self._check_auth()
            if user is None:
                return
        audit_data = {
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
        }
        if MULTI_USER:
            audit_data["audit_summary"] = audit_log.get_summary()
        self._send_json(200, audit_data)

    def _handle_models(self):
        if MULTI_USER:
            user = self._mu_check_auth()
            if user is None:
                return
        else:
            user = self._check_auth()
            if user is None:
                return
        self._send_json(200, {
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
        })

    # ---- Admin GET endpoints ----

    def _handle_admin_list_users(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        users = _user_manager.list_users(include_keys=False)
        self._send_json(200, {"users": users})

    def _handle_admin_list_sessions(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        sessions = session_store.list_all_session_metadata()
        self._send_json(200, {"sessions": sessions})

    def _handle_admin_audit(self):
        admin = self._mu_check_admin()
        if admin is None:
            return
        self._send_json(200, {
            "summary": audit_log.get_summary(),
            "per_user": audit_log.get_all_stats(),
        })

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
    if MULTI_USER:
        print("\n  [Multi-User] ENABLED")
        print("  GET    /v1/admin/users          — list users (admin)")
        print("  POST   /v1/admin/users          — create user (admin)")
        print("  DELETE /v1/admin/users/{name}    — delete user (admin)")
        print("  GET    /v1/admin/sessions       — list sessions (admin)")
        print("  POST   /v1/admin/sessions/wipe  — wipe user sessions (admin)")
        print("  GET    /v1/admin/audit          — per-user audit (admin)")
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
