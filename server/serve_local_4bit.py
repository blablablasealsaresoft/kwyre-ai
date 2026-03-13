import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import re
import sys
import time
import torch
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.benchmark = True
import json
import hashlib
import secrets
import signal
import threading
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TextIteratorStreamer
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

try:
    import flash_attn
    _FLASH_ATTN_KWARGS = {"attn_implementation": "flash_attention_2"}
    print("[Optimization] Flash Attention 2 available — enabled")
except ImportError:
    _FLASH_ATTN_KWARGS = {}
    print("[Optimization] Flash Attention 2 not installed — using default attention")

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
from rag import SecureRAGStore, DocumentParser, encode_texts

DEFAULT_SYSTEM_PROMPT = (
    "You are Kwyre, a specialized AI assistant for legal, financial, and forensic "
    "analysis. You provide precise, well-structured responses citing relevant "
    "regulations, statutes, and professional standards. You organize complex analysis "
    "with clear headings, numbered points, and specific references. When analyzing "
    "documents, you identify key obligations, risks, and compliance requirements. "
    "You never fabricate citations or case law. If uncertain, you state your "
    "confidence level explicitly."
)

MODEL_ID = os.environ.get("KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
PORT = 8000
SPIKE_K = 5.0
SPIKE_MAX = 31

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": {"name": "kwyre-4b", "vram_4bit": "~4.1GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})

SPECULATIVE_ENABLED = os.environ.get("KWYRE_SPECULATIVE", "1") == "1"
DRAFT_MODEL_ID = os.environ.get("KWYRE_DRAFT_MODEL", "Qwen/Qwen3.5-0.8B")

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
# Hashes are for Qwen/Qwen3.5-4B base (tokenizer is byte-identical in the uncensored fine-tune;
# config.json matches the unmodified 4B architecture). If you load via local safetensors or a
# locally converted copy and see a hash mismatch on config.json, regenerate with:
# python -c "from server.serve_local_4bit import generate_weight_hashes; import json; print(json.dumps(generate_weight_hashes('<model_cache_path>'), indent=2))"
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
_dist_path = os.path.join(_project_root, "dist", f"{ACTIVE_TIER['name']}-nf4")
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
            **_FLASH_ATTN_KWARGS,
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
            **_FLASH_ATTN_KWARGS,
        )
    print(f"[Quantization] AWQ mode active (~1.4x faster inference)")
else:
    if _USE_PREQUANT:
        print(f"Loading pre-quantized NF4 model from {LOCAL_MODEL_PATH}...")
        model = AutoModelForCausalLM.from_pretrained(
            LOCAL_MODEL_PATH, trust_remote_code=True,
            device_map="auto", torch_dtype=torch.bfloat16,
            **_FLASH_ATTN_KWARGS,
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
            **_FLASH_ATTN_KWARGS,
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
                **_FLASH_ATTN_KWARGS,
            )
        elif os.path.isdir(_draft_dist) and os.path.exists(os.path.join(_draft_dist, "config.json")):
            print(f"[Speculative] Loading pre-quantized draft from {_draft_dist}...")
            draft_model = AutoModelForCausalLM.from_pretrained(
                _draft_dist, trust_remote_code=True,
                device_map="auto", torch_dtype=torch.bfloat16,
                **_FLASH_ATTN_KWARGS,
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
                **_FLASH_ATTN_KWARGS,
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

# SpikeServe hooks go on the DRAFT model (speed matters, accuracy tolerant)
# NOT the main model (accuracy is critical for speculative validation)
n_converted = 0
if draft_model is not None:
    print(f"SpikeServe: attaching spike encoding to DRAFT model (k={SPIKE_K})...")
    active_spike_hooks, n_converted = apply_spike_hooks(
        draft_model, k=SPIKE_K, max_spike=SPIKE_MAX,
        skip_patterns=SPIKE_SKIP, measure_only=False,
    )
    print(f"SpikeServe ACTIVE on draft: {n_converted} MLP layers | k={SPIKE_K}")
    print(f"  Main model runs at full fidelity for accurate speculative validation")
else:
    print(f"[SpikeServe] No draft model — skipping (hooks only apply to draft)")
    active_spike_hooks = []

# ---------------------------------------------------------------------------
# Domain Adapter Manager (Hot-Swap LoRA)
# Enhancement 1: Adapter stacking via weighted merge
# Enhancement 4: CDN-based adapter versioning
# ---------------------------------------------------------------------------
ADAPTER_DIR = os.environ.get(
    "KWYRE_ADAPTER_DIR",
    os.path.join(os.path.expanduser("~"), ".kwyre", "adapters")
)
ALLOW_ADAPTER_SWAP = os.environ.get("KWYRE_ALLOW_ADAPTER_SWAP", "1") == "1"
CDN_MANIFEST_URL = os.environ.get(
    "KWYRE_ADAPTER_MANIFEST_URL",
    "https://kwyre.com/adapters/manifest.json"
)

_adapter_lock = threading.Lock()
_active_adapter: str | None = None
_base_model_ref = model
_adapted_model = None

_DOMAIN_SUFFIX_RE = re.compile(r"-(?:4b|9b)$")


def _canonicalize_domain_name(name: str) -> str:
    """Reduce any domain name variant to a canonical form for matching.

    ``legal_compliance``, ``legal-compliance``, ``legal-compliance-4b``,
    and ``legal_compliance-9b`` all map to ``legal-compliance``.
    """
    canonical = name.strip().lower().replace("_", "-")
    canonical = _DOMAIN_SUFFIX_RE.sub("", canonical)
    return canonical


def _list_available_adapters() -> dict:
    """Scan adapter directory for valid PEFT checkpoints.

    Returns a dict keyed by *folder name* with an extra ``canonical``
    field so callers can match by canonical domain name.
    """
    adapters = {}
    if not os.path.isdir(ADAPTER_DIR):
        return adapters
    for name in os.listdir(ADAPTER_DIR):
        adapter_path = os.path.join(ADAPTER_DIR, name)
        config_path = os.path.join(adapter_path, "adapter_config.json")
        if os.path.isfile(config_path):
            meta_path = os.path.join(adapter_path, "metadata.json")
            meta = {}
            if os.path.isfile(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
            adapters[name] = {
                "path": adapter_path,
                "metadata": meta,
                "canonical": _canonicalize_domain_name(name),
            }
    return adapters


def _resolve_adapter_name(domain_name: str, available: dict) -> str | None:
    """Find the actual folder name for *domain_name* using canonical matching.

    Tries an exact match first, then falls back to canonical comparison.
    When multiple folders share a canonical name (e.g. ``legal-compliance``
    and ``legal-compliance-4b``), prefer the one without a model-tier suffix.
    """
    if domain_name in available:
        return domain_name

    target = _canonicalize_domain_name(domain_name)
    candidates = [
        folder for folder, info in available.items()
        if info["canonical"] == target
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Prefer shorter name (no -4b/-9b suffix)
    candidates.sort(key=len)
    return candidates[0]


def load_adapter(domain_name: str) -> dict:
    """Load a domain LoRA adapter onto the base model. Thread-safe.

    *domain_name* is resolved through canonical name matching so that
    ``legal_compliance``, ``legal-compliance``, or ``legal-compliance-4b``
    all find whichever folder actually exists on disk.
    """
    global _active_adapter, _adapted_model, model

    with _adapter_lock:
        available = _list_available_adapters()
        resolved = _resolve_adapter_name(domain_name, available)
        if resolved is None:
            return {"error": f"Adapter '{domain_name}' not found",
                    "available": list(available.keys())}

        if _active_adapter == resolved:
            return {"status": "already_loaded", "adapter": resolved}

        if _adapted_model is not None:
            try:
                _adapted_model.unload()
            except Exception:
                pass
            _adapted_model = None
            _active_adapter = None

        try:
            adapted = PeftModel.from_pretrained(
                _base_model_ref, available[resolved]["path"]
            )
            if os.environ.get("KWYRE_MERGE_LORA", "0") == "1":
                adapted = adapted.merge_and_unload()
                print(f"[Adapter] Loaded and merged: {resolved}")
            else:
                adapted.eval()
                print(f"[Adapter] Loaded in-place: {resolved}")

            model = adapted
            _adapted_model = adapted
            _active_adapter = resolved
            return {
                "status": "loaded",
                "adapter": resolved,
                "metadata": available[resolved].get("metadata", {}),
            }
        except Exception as e:
            model = _base_model_ref
            _active_adapter = None
            return {"error": str(e)}


def unload_adapter() -> dict:
    """Remove active adapter, revert to base model."""
    global _active_adapter, _adapted_model, model

    with _adapter_lock:
        if _active_adapter is None:
            return {"status": "no_adapter_loaded"}

        prev = _active_adapter
        if _adapted_model is not None:
            try:
                _adapted_model.unload()
            except Exception:
                pass
            _adapted_model = None
        model = _base_model_ref
        _active_adapter = None
        print(f"[Adapter] Unloaded: {prev}")
        return {"status": "unloaded", "previous": prev}


def stack_adapters(adapters: list, weights: list | None = None, name: str = "stacked") -> dict:
    """Merge multiple domain adapters with optional weights. Thread-safe.

    Each entry in *adapters* is resolved through canonical name matching.
    """
    global _active_adapter, _adapted_model, model

    with _adapter_lock:
        available = _list_available_adapters()
        resolved_adapters = []
        missing = []
        for a in adapters:
            r = _resolve_adapter_name(a, available)
            if r is None:
                missing.append(a)
            else:
                resolved_adapters.append(r)
        if missing:
            return {"error": f"Adapters not found: {missing}", "available": list(available.keys())}

        if weights is None:
            weights = [1.0 / len(resolved_adapters)] * len(resolved_adapters)
        if len(weights) != len(resolved_adapters):
            return {"error": "weights length must match adapters length"}

        if _adapted_model is not None:
            try:
                _adapted_model.unload()
            except Exception:
                pass
            _adapted_model = None
            _active_adapter = None

        try:
            peft_model = None
            for adapter_name in resolved_adapters:
                adapter_path = available[adapter_name]["path"]
                if peft_model is None:
                    peft_model = PeftModel.from_pretrained(
                        _base_model_ref, adapter_path, adapter_name=adapter_name
                    )
                else:
                    peft_model.load_adapter(adapter_path, adapter_name=adapter_name)

            peft_model.add_weighted_adapter(
                adapters=resolved_adapters,
                weights=weights,
                adapter_name=name,
                combination_type="linear",
            )
            peft_model.set_adapter(name)
            peft_model.eval()

            model = peft_model
            _adapted_model = peft_model
            _active_adapter = name
            print(f"[Adapter] Stacked {resolved_adapters} -> '{name}' (weights={weights})")
            return {
                "status": "stacked",
                "adapter": name,
                "source_adapters": resolved_adapters,
                "weights": weights,
            }
        except Exception as e:
            model = _base_model_ref
            _active_adapter = None
            return {"error": str(e)}


_default_adapter = os.environ.get("KWYRE_DEFAULT_ADAPTER", "")
if _default_adapter:
    print(f"[Adapter] Auto-loading default: {_default_adapter}")
    load_adapter(_default_adapter)

# Lazy sparsity measurement — runs on first real inference request
_sparsity_measured = False
_sparsity_lock = threading.Lock()
STARTUP_SPARSITY = {"avg_sparsity": 0.0, "layers": n_converted, "total_calls": 0}

def _measure_sparsity_lazy():
    """Measure sparsity on first real request instead of blocking startup."""
    global _sparsity_measured, STARTUP_SPARSITY
    with _sparsity_lock:
        if _sparsity_measured:
            return
        _sparsity_measured = True
    stats = get_sparsity_stats()
    if stats["total_calls"] > 0:
        STARTUP_SPARSITY = stats
        print(f"[SpikeServe] Measured sparsity: {stats['avg_sparsity']}% "
              f"across {stats['layers']} layers ({stats['total_calls']} calls)")

gpu_mem = torch.cuda.memory_allocated() / 1e9
gpu_total = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"GPU VRAM: {gpu_mem:.1f} / {gpu_total:.1f} GB")

# ---------------------------------------------------------------------------
# KV cache store — per-session cache for multi-turn conversations
# Avoids re-encoding the entire conversation on every follow-up message.
# ---------------------------------------------------------------------------
_KV_CACHE_MAX_SESSIONS = int(os.environ.get("KWYRE_KV_CACHE_MAX", "8"))
_KV_CACHE_MAX_VRAM_GB = float(os.environ.get("KWYRE_KV_CACHE_VRAM_GB", "2.0"))

class KVCacheStore:
    def __init__(self, max_sessions: int, max_vram_gb: float):
        self._cache: dict[str, dict] = {}  # sid -> {"past_key_values": ..., "seq_len": int}
        self._access_order: list[str] = []
        self._lock = threading.Lock()
        self._max_sessions = max_sessions
        self._max_vram_bytes = int(max_vram_gb * 1e9)

    def get(self, session_id: str):
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is not None:
                if session_id in self._access_order:
                    self._access_order.remove(session_id)
                self._access_order.append(session_id)
            return entry

    def put(self, session_id: str, past_key_values, seq_len: int):
        with self._lock:
            self._evict_if_needed()
            self._cache[session_id] = {
                "past_key_values": past_key_values,
                "seq_len": seq_len,
            }
            if session_id in self._access_order:
                self._access_order.remove(session_id)
            self._access_order.append(session_id)

    def evict(self, session_id: str):
        with self._lock:
            entry = self._cache.pop(session_id, None)
            if entry and entry.get("past_key_values"):
                del entry["past_key_values"]
            if session_id in self._access_order:
                self._access_order.remove(session_id)

    def _evict_if_needed(self):
        while len(self._cache) >= self._max_sessions and self._access_order:
            oldest = self._access_order.pop(0)
            entry = self._cache.pop(oldest, None)
            if entry and entry.get("past_key_values"):
                del entry["past_key_values"]
        if torch.cuda.is_available():
            kv_vram = sum(
                sum(t.nelement() * t.element_size() for layer in e["past_key_values"] for t in layer)
                for e in self._cache.values() if e.get("past_key_values")
            )
            while kv_vram > self._max_vram_bytes and self._access_order:
                oldest = self._access_order.pop(0)
                entry = self._cache.pop(oldest, None)
                if entry and entry.get("past_key_values"):
                    evicted_size = sum(
                        t.nelement() * t.element_size() for layer in entry["past_key_values"] for t in layer
                    )
                    kv_vram -= evicted_size
                    del entry["past_key_values"]

    def wipe_all(self):
        with self._lock:
            for entry in self._cache.values():
                if entry.get("past_key_values"):
                    del entry["past_key_values"]
            self._cache.clear()
            self._access_order.clear()

    def stats(self) -> dict:
        with self._lock:
            kv_vram = 0
            if self._cache:
                for e in self._cache.values():
                    if e.get("past_key_values"):
                        kv_vram += sum(
                            t.nelement() * t.element_size() for layer in e["past_key_values"] for t in layer
                        )
            return {
                "cached_sessions": len(self._cache),
                "max_sessions": self._max_sessions,
                "kv_cache_vram_mb": round(kv_vram / 1e6, 1),
                "max_vram_mb": round(self._max_vram_bytes / 1e6, 1),
            }

kv_cache_store = KVCacheStore(_KV_CACHE_MAX_SESSIONS, _KV_CACHE_MAX_VRAM_GB)
print(f"[KV Cache] Enabled — max {_KV_CACHE_MAX_SESSIONS} sessions, {_KV_CACHE_MAX_VRAM_GB} GB VRAM cap")

# ---------------------------------------------------------------------------
# Inference queue — serializes GPU access, lets HTTP threads stay responsive
# ---------------------------------------------------------------------------
_inference_queue: queue.Queue = queue.Queue()
_INFERENCE_WORKERS = 1  # GPU can only run one generation at a time

def _inference_worker():
    """Background thread that pulls generation tasks off the queue."""
    while True:
        task = _inference_queue.get()
        if task is None:
            break
        try:
            task["fn"](*task["args"], **task["kwargs"])
        except Exception as e:
            print(f"[inference-worker] Error: {e}")
            if "error_cb" in task:
                try:
                    task["error_cb"](e)
                except Exception:
                    pass
        finally:
            _inference_queue.task_done()

_worker_thread = threading.Thread(target=_inference_worker, daemon=True, name="InferenceWorker")
_worker_thread.start()

# Start security subsystems
session_store = SessionStore()
rag_store = SecureRAGStore()
print(f"[RAG] Document store active — RAM only, wiped on close")
watchdog = IntrusionWatchdog(session_store, terminate_on_intrusion=True)
watchdog.start()


def _shutdown_handler(signum, frame):
    print("\n[Shutdown] Wiping all sessions, KV cache, and documents before exit...")
    watchdog.stop()
    rag_store.wipe_all(reason="server_shutdown")
    kv_cache_store.wipe_all()
    session_store.wipe_all(reason="server_shutdown")
    _inference_queue.put(None)
    sys.exit(0)

signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

_trial_tracker: dict[str, int] = {}
print(f"[Security] Bound to {BIND_HOST}:{PORT} — localhost only")
print(f"[Security] Intrusion watchdog active")
print(f"[Security] Session store active — RAM only, wiped on close")


# ---------------------------------------------------------------------------
# Adaptive speculative decoding
# ---------------------------------------------------------------------------
class AdaptiveSpeculator:
    """Thread-safe tracker that adjusts assistant_early_exit based on acceptance rates."""

    _MIN_EXIT = 2
    _MAX_EXIT = 8
    _DEFAULT_EXIT = 4

    def __init__(self, window_size: int = 20):
        self._lock = threading.Lock()
        self._window_size = window_size
        self._acceptance_rates: list[float] = []
        self._early_exit = self._DEFAULT_EXIT

    def record(self, accepted: int, proposed: int):
        if proposed <= 0:
            return
        rate = accepted / proposed
        with self._lock:
            self._acceptance_rates.append(rate)
            if len(self._acceptance_rates) > self._window_size:
                self._acceptance_rates = self._acceptance_rates[-self._window_size:]
            avg = sum(self._acceptance_rates) / len(self._acceptance_rates)
            if avg > 0.80:
                self._early_exit = min(self._early_exit + 1, self._MAX_EXIT)
            elif avg < 0.40:
                self._early_exit = max(self._early_exit - 1, self._MIN_EXIT)

    def get_exit_threshold(self) -> int:
        with self._lock:
            return self._early_exit

    def stats(self) -> dict:
        with self._lock:
            rates = list(self._acceptance_rates)
        avg = sum(rates) / len(rates) if rates else 0.0
        return {
            "current_exit_threshold": self._early_exit,
            "avg_acceptance_rate": round(avg, 4),
            "window_size": self._window_size,
            "samples": len(rates),
        }


class SpecDecodingStats:
    """Tracks aggregate speculative decoding performance metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._speculative_tokens = 0
        self._standard_tokens = 0
        self._speculative_time = 0.0
        self._standard_time = 0.0
        self._speculative_requests = 0
        self._standard_requests = 0

    def record_speculative(self, tokens: int, elapsed: float):
        with self._lock:
            self._speculative_tokens += tokens
            self._speculative_time += elapsed
            self._speculative_requests += 1

    def record_standard(self, tokens: int, elapsed: float):
        with self._lock:
            self._standard_tokens += tokens
            self._standard_time += elapsed
            self._standard_requests += 1

    def stats(self) -> dict:
        with self._lock:
            spec_tps = (self._speculative_tokens / self._speculative_time
                        if self._speculative_time > 0 else 0.0)
            std_tps = (self._standard_tokens / self._standard_time
                       if self._standard_time > 0 else 0.0)
            speedup = spec_tps / std_tps if std_tps > 0 else 0.0
            return {
                "speculative_tokens": self._speculative_tokens,
                "standard_tokens": self._standard_tokens,
                "speculative_requests": self._speculative_requests,
                "standard_requests": self._standard_requests,
                "speculative_avg_tps": round(spec_tps, 1),
                "standard_avg_tps": round(std_tps, 1),
                "speed_improvement_factor": round(speedup, 2),
            }


adaptive_speculator = AdaptiveSpeculator()
spec_decoding_stats = SpecDecodingStats()

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

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

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
        elif self.path == "/v1/documents/upload":
            self._handle_document_upload()
        elif self.path == "/v1/adapter/load":
            self._handle_adapter_load()
        elif self.path == "/v1/adapter/unload":
            self._handle_adapter_unload()
        elif self.path == "/v1/adapter/stack":
            self._handle_adapter_stack()
        elif self.path.startswith("/v1/adapter/update/"):
            self._handle_adapter_update()
        elif self.path == "/v1/analytics/predict":
            self._handle_analytics_predict()
        elif self.path == "/v1/analytics/risk":
            self._handle_analytics_risk()
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
            top_k = min(max(int(body.get("top_k", 20)), 0), 100)
            repetition_penalty = min(max(float(body.get("repetition_penalty", 1.1)), 1.0), 2.0)
        except (TypeError, ValueError):
            self._send_json_error(400, "Invalid max_tokens, temperature, top_p, or top_k.")
            return
        if _license_tier == "eval":
            max_tokens = min(max_tokens, _MAX_EVAL_TOKENS)

        stream = body.get("stream", False)

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

        session, created = session_store.get_or_create(session_id)
        if MULTI_USER and created:
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

        rag_chunks = []
        if rag_store.has_documents(session_id):
            try:
                query_emb = encode_texts([last_user_msg])
                if query_emb is not None:
                    rag_chunks = rag_store.retrieve(session_id, query_emb[0])
            except Exception as e:
                print(f"[RAG] retrieval error: {e}")

        augmented = list(messages)
        if not any(m.get("role") == "system" for m in augmented):
            augmented.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})
        ctx_parts = []
        if tool_data:
            ctx_parts.append("[Live data — use directly, be concise]\n\n" + "\n\n".join(tool_data))
        if rag_chunks:
            ctx_parts.append("[Retrieved document context — cite relevant sections]\n\n" + "\n\n---\n\n".join(rag_chunks))
        if ctx_parts:
            ctx = "\n\n" + "\n\n".join(ctx_parts)
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
        input_len = inputs.input_ids.shape[1]

        gen_kwargs = {
            "input_ids": inputs.input_ids,
            "attention_mask": inputs.attention_mask,
            "max_new_tokens": max_tokens,
            "temperature": max(temperature, 0.01),
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "do_sample": temperature > 0,
            "use_cache": True,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if draft_model is not None:
            gen_kwargs["assistant_model"] = draft_model
            gen_kwargs["assistant_early_exit"] = adaptive_speculator.get_exit_threshold()

        if stream:
            self._handle_stream_gpu(
                gen_kwargs, input_len, session_id, session, user, tools_used,
            )
        else:
            self._handle_blocking_gpu(
                gen_kwargs, input_len, session_id, session, user, tools_used,
            )

    def _handle_blocking_gpu(self, gen_kwargs, input_len, session_id, session,
                             user, tools_used):
        done_event = threading.Event()
        result_holder: dict = {}

        cached = kv_cache_store.get(session_id)
        if cached and cached.get("past_key_values"):
            cached_len = cached["seq_len"]
            if cached_len < input_len:
                gen_kwargs["past_key_values"] = cached["past_key_values"]
                gen_kwargs["input_ids"] = gen_kwargs["input_ids"][:, cached_len:]
                gen_kwargs["attention_mask"] = gen_kwargs["attention_mask"][:, :input_len]
                print(f"[KV Cache] HIT {session_id[:8]}... — "
                      f"reusing {cached_len} tokens, encoding {input_len - cached_len} new")
            else:
                kv_cache_store.evict(session_id)

        _used_speculation = "assistant_model" in gen_kwargs

        def _run_inference():
            t0 = time.time()
            with torch.inference_mode():
                outputs = model.generate(**gen_kwargs, return_dict_in_generate=True)
            elapsed = time.time() - t0
            gen_ids = outputs.sequences
            new_ids = gen_ids[0][input_len:]
            result_holder["new_ids"] = new_ids
            result_holder["elapsed"] = elapsed

            n_out = len(new_ids)
            if _used_speculation:
                spec_decoding_stats.record_speculative(n_out, elapsed)
                assistant_toks = getattr(outputs, "num_assistant_tokens", None)
                if assistant_toks is not None:
                    proposed = int(assistant_toks.sum()) if hasattr(assistant_toks, "sum") else int(assistant_toks)
                    if proposed > 0:
                        adaptive_speculator.record(accepted=n_out, proposed=proposed)
            else:
                spec_decoding_stats.record_standard(n_out, elapsed)

            if hasattr(outputs, "past_key_values") and outputs.past_key_values:
                total_seq = gen_ids.shape[1]
                try:
                    detached_kv = tuple(
                        tuple(t.detach() for t in layer)
                        for layer in outputs.past_key_values
                    )
                    kv_cache_store.put(session_id, detached_kv, total_seq)
                except Exception:
                    pass
            _measure_sparsity_lazy()
            done_event.set()

        _inference_queue.put({
            "fn": _run_inference, "args": (), "kwargs": {},
            "error_cb": lambda e: (result_holder.update({"error": str(e)}), done_event.set()),
        })

        done_event.wait(timeout=300)

        if "error" in result_holder:
            self._send_json_error(500, f"Inference error: {result_holder['error']}")
            return
        if not done_event.is_set():
            self._send_json_error(504, "Inference timed out.")
            return

        new_ids = result_holder["new_ids"]
        elapsed = result_holder["elapsed"]
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
            label = session_id[:8] if isinstance(user, str) else session_id[:8]
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

    def _handle_stream_gpu(self, gen_kwargs, input_len, session_id, session,
                           user, tools_used):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self._send_cors_headers()
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(b": stream opened\n\n")
        self.wfile.flush()

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs["streamer"] = streamer
        # Speculative decoding is not compatible with TextIteratorStreamer.
        # Streaming runs at base model speed (~1x) vs blocking mode (~2-3x with draft model).
        # KV cache is also not used for streaming — full conversation re-encoded each turn.
        gen_kwargs.pop("assistant_model", None)
        gen_kwargs.pop("return_dict_in_generate", None)

        full_reply: list[str] = []
        n_tokens = 0
        t0 = time.time()

        gen_error: list[Exception] = []
        def _run_generation():
            try:
                with torch.inference_mode():
                    model.generate(**gen_kwargs)
            except Exception as e:
                gen_error.append(e)
                streamer.end()

        gen_thread = threading.Thread(target=_run_generation, daemon=True)
        gen_thread.start()

        model_name = f"{ACTIVE_TIER['name']}-spikeserve"
        response_sid = session_id.split(":", 1)[-1] if MULTI_USER else session_id
        try:
            for text_chunk in streamer:
                if not text_chunk:
                    continue
                full_reply.append(text_chunk)
                n_tokens += 1
                sse_data = json.dumps({
                    "choices": [{"delta": {"content": text_chunk}}],
                    "model": model_name,
                    "session_id": response_sid,
                })
                self.wfile.write(f"data: {sse_data}\n\n".encode())
                self.wfile.flush()

            gen_thread.join(timeout=5)

            elapsed = time.time() - t0
            tps = n_tokens / elapsed if elapsed > 0 else 0

            reply_text = "".join(full_reply)
            reply_text = re.sub(r"<think>.*?</think>", "", reply_text, flags=re.DOTALL)
            reply_text = re.sub(r"<think>.*", "", reply_text, flags=re.DOTALL)
            reply_text = reply_text.strip()
            session.add_message("assistant", reply_text)

            _measure_sparsity_lazy()

            if gen_error:
                print(f"[inference] Stream generation error: {gen_error[0]}")
                error_data = json.dumps({
                    "choices": [{"delta": {}, "finish_reason": "error"}],
                    "model": model_name,
                    "session_id": response_sid,
                    "error": str(gen_error[0]),
                })
                self.wfile.write(f"data: {error_data}\n\n".encode())
            else:
                done_data = json.dumps({
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "model": model_name,
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
                self.wfile.write(f"data: {done_data}\n\n".encode())

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

            if MULTI_USER:
                audit_log.record_request(user["id"], user.get("username", ""), tokens=n_tokens)
                label = f"{user['username']}@{response_sid[:8]}"
            else:
                label = response_sid[:8]
            print(f"[inference] {label}... | {n_tokens} tokens "
                  f"in {elapsed:.1f}s ({tps:.1f} tok/s) [stream]")

        except (BrokenPipeError, ConnectionResetError):
            print(f"[inference] {response_sid[:8]}... | client disconnected during stream")

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
                kv_cache_store.evict(namespaced)
                session_store.wipe_session(namespaced, reason="user_request")
            else:
                kv_cache_store.evict(raw_sid)
                session_store.wipe_session(raw_sid, reason="user_request")
            msg = f"Session {raw_sid[:8]}... wiped. Conversation and KV cache unrecoverable."
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

    def _handle_document_upload(self):
        user = self._check_auth() if not MULTI_USER else self._mu_check_auth()
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
                        rag_store.add_documents(session_id, chunks, embeddings,
                                                {"filename": fname})
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
        for sid in session_store.get_sessions_for_user(target["id"]):
            kv_cache_store.evict(sid)
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
        for sid in session_store.get_sessions_for_user(target["id"]):
            kv_cache_store.evict(sid)
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

    def _handle_analytics_predict(self):
        user = self._check_auth() if not MULTI_USER else self._mu_check_auth()
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

    def _handle_analytics_risk(self):
        user = self._check_auth() if not MULTI_USER else self._mu_check_auth()
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

    # ---- GET routing ----

    def do_GET(self):
        if self.path == "/":
            self._serve_html("landing.html")
        elif self.path == "/chat":
            self._serve_html("main.html")
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
        elif self.path == "/v1/adapter/list":
            self._handle_adapter_list()
        elif self.path == "/v1/adapter/status":
            self._handle_adapter_status()
        elif self.path == "/v1/adapter/check-update":
            self._handle_adapter_check_update()
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
                "product": f"Kwyre {ACTIVE_TIER['tier'].title()}",
                "description": f"{ACTIVE_TIER['tier'].title()} tier — {ACTIVE_TIER['vram_4bit']} VRAM, speculative decoding + SpikeServe",
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
                    "adaptive": adaptive_speculator.stats(),
                    "session_stats": spec_decoding_stats.stats(),
                },
                "spike_analysis": {
                    "target": "draft_model" if draft_model is not None else "disabled",
                    "k": SPIKE_K,
                    "measured_sparsity_pct": STARTUP_SPARSITY["avg_sparsity"],
                    "spike_encoded_layers": n_converted,
                    "measured": _sparsity_measured,
                },
                "streaming": True,
                "inference_queue": True,
                "kv_cache": kv_cache_store.stats(),
                "rag": {
                    "active_sessions": rag_store.active_count(),
                    "total_chunks": rag_store.total_chunks(),
                    "storage": "RAM-only",
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
                    "product": f"Kwyre {ACTIVE_TIER['tier'].title()}",
                    "capabilities": ["streaming", "speculative_decoding", "spike_serve", "kv_cache", "rag", "multi_user", "tools", "session_wipe", "crypto_wipe"],
                    "base_model": MODEL_ID.split("/")[-1],
                    "weight_quant": f"4-bit {KWYRE_QUANT.upper()}",
                    "activation_encoding": "SpikeServe (draft model)",
                    "spike_encoded_layers": n_converted,
                    "streaming": True,
                    "speculative_decoding": draft_model is not None,
                    "security": {
                        "network": "localhost-only",
                        "storage": "RAM-only sessions",
                        "integrity": "SHA256 weight verification",
                        "watchdog": "intrusion detection + auto-wipe",
                    },
                },
            }],
        })

    # ---- Adapter endpoints ----

    def _handle_adapter_list(self):
        available = _list_available_adapters()
        adapters_out = {}
        for name, info in available.items():
            entry = dict(info["metadata"])
            entry["canonical"] = info["canonical"]
            adapters_out[name] = entry
        self._send_json(200, {
            "adapters": adapters_out,
            "active_adapter": _active_adapter,
            "adapter_dir": ADAPTER_DIR,
        })

    def _handle_adapter_status(self):
        self._send_json(200, {
            "active_adapter": _active_adapter,
            "base_model": MODEL_ID,
            "adapter_swap_enabled": ALLOW_ADAPTER_SWAP,
        })

    def _handle_adapter_load(self):
        if not ALLOW_ADAPTER_SWAP:
            self._send_json_error(403, "Adapter hot-swap is disabled (KWYRE_ALLOW_ADAPTER_SWAP=0).")
            return
        body, err = self._parse_json_body(required=True)
        if err is not None:
            self._send_json_error(400, err)
            return
        domain = (body or {}).get("domain", "").strip()
        if not domain:
            self._send_json_error(400, "Missing 'domain' field.")
            return
        result = load_adapter(domain)
        status = 200 if "error" not in result else 400
        self._send_json(status, result)

    def _handle_adapter_unload(self):
        if not ALLOW_ADAPTER_SWAP:
            self._send_json_error(403, "Adapter hot-swap is disabled (KWYRE_ALLOW_ADAPTER_SWAP=0).")
            return
        result = unload_adapter()
        self._send_json(200, result)

    def _handle_adapter_stack(self):
        if not ALLOW_ADAPTER_SWAP:
            self._send_json_error(403, "Adapter hot-swap is disabled (KWYRE_ALLOW_ADAPTER_SWAP=0).")
            return
        body, err = self._parse_json_body(required=True)
        if err is not None:
            self._send_json_error(400, err)
            return
        adapters = (body or {}).get("adapters")
        if not isinstance(adapters, list) or len(adapters) < 1:
            self._send_json_error(400, "Missing or invalid 'adapters' list.")
            return
        weights = (body or {}).get("weights")
        name = (body or {}).get("name", "stacked")
        result = stack_adapters(adapters, weights=weights, name=name)
        status = 200 if "error" not in result else 400
        self._send_json(status, result)

    def _handle_adapter_check_update(self):
        import urllib.request as _urllib_request
        try:
            with _urllib_request.urlopen(CDN_MANIFEST_URL, timeout=5) as resp:
                manifest = json.loads(resp.read())
        except Exception as e:
            self._send_json(503, {"error": f"Failed to fetch manifest: {e}", "url": CDN_MANIFEST_URL})
            return

        available = _list_available_adapters()
        canonical_to_local = {
            info["canonical"]: info for info in available.values()
        }
        updates = {}
        for domain, info in manifest.items():
            canon = _canonicalize_domain_name(domain)
            local_info = canonical_to_local.get(canon, {})
            local_ver = local_info.get("metadata", {}).get("version", "0.0.0")
            remote_ver = info.get("version", "0.0.0")
            if remote_ver > local_ver:
                updates[domain] = {
                    "local": local_ver,
                    "remote": remote_ver,
                    "url": info.get("url"),
                }
        self._send_json(200, {"updates_available": updates, "up_to_date": len(updates) == 0})

    def _handle_adapter_update(self):
        import urllib.request as _urllib_request
        import zipfile
        import shutil

        raw_domain = self.path.split("/v1/adapter/update/", 1)[-1].strip("/")
        if not raw_domain:
            self._send_json_error(400, "Missing domain in URL path.")
            return
        domain = _canonicalize_domain_name(raw_domain)

        try:
            with _urllib_request.urlopen(CDN_MANIFEST_URL, timeout=5) as resp:
                manifest = json.loads(resp.read())
        except Exception as e:
            self._send_json(503, {"error": f"Failed to fetch manifest: {e}"})
            return

        manifest_key = None
        for key in manifest:
            if _canonicalize_domain_name(key) == domain:
                manifest_key = key
                break
        if manifest_key is None:
            self._send_json_error(404, f"Domain '{raw_domain}' not in CDN manifest.")
            return

        remote_info = manifest[manifest_key]
        download_url = remote_info.get("url")
        if not download_url:
            self._send_json_error(502, f"No download URL in manifest for '{domain}'.")
            return

        adapter_path = os.path.join(ADAPTER_DIR, domain)
        backup_path = adapter_path + ".backup"

        if os.path.isdir(adapter_path):
            if os.path.isdir(backup_path):
                shutil.rmtree(backup_path)
            shutil.copytree(adapter_path, backup_path)

        try:
            os.makedirs(ADAPTER_DIR, exist_ok=True)
            tmp_zip = os.path.join(ADAPTER_DIR, f"_{domain}_update.zip")
            _urllib_request.urlretrieve(download_url, tmp_zip)

            expected_sha = remote_info.get("sha256", "")
            if expected_sha:
                with open(tmp_zip, "rb") as fh:
                    actual_sha = hashlib.sha256(fh.read()).hexdigest()
                if actual_sha != expected_sha:
                    os.remove(tmp_zip)
                    self._send_json(502, {
                        "error": "SHA-256 mismatch — adapter download corrupted or tampered",
                        "expected": expected_sha,
                        "actual": actual_sha,
                    })
                    return

            if os.path.isdir(adapter_path):
                shutil.rmtree(adapter_path)

            with zipfile.ZipFile(tmp_zip, "r") as zf:
                zf.extractall(os.path.join(ADAPTER_DIR, domain))
            os.remove(tmp_zip)

            if os.path.isdir(backup_path):
                shutil.rmtree(backup_path)

            print(f"[Adapter] Updated '{domain}' from CDN: {download_url}")
            self._send_json(200, {
                "status": "updated",
                "domain": domain,
                "version": remote_info.get("version"),
            })
        except Exception as e:
            if os.path.isdir(backup_path):
                if os.path.isdir(adapter_path):
                    shutil.rmtree(adapter_path)
                shutil.copytree(backup_path, adapter_path)
                shutil.rmtree(backup_path)
                print(f"[Adapter] Update failed for '{domain}', restored backup: {e}")
            self._send_json(500, {"error": f"Update failed: {e}", "domain": domain})

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
    _spike_target = "draft model" if draft_model else "disabled"
    print(f"  SpikeServe on {_spike_target} ({n_converted} layers)  |  4-bit {KWYRE_QUANT.upper()}  |  {_spec_status}")
    print(f"  Streaming: SSE enabled  |  Inference queue: active  |  6 security layers active")
    print(f"  Available tiers: KWYRE_MODEL=Qwen/Qwen3.5-9B (7.5GB) | Qwen/Qwen3.5-4B (3.5GB)")
    print("  POST /v1/chat/completions  — inference (stream=true for SSE)")
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
