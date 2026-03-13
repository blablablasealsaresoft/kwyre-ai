"""
Kwyre AI — Platform GPU Abstraction
=====================================
Unified GPU detection and configuration for AMD ROCm (Linux)
and NVIDIA CUDA (Windows). The rest of the codebase should import
from this module instead of hard-coding platform checks.
"""

import logging
import subprocess
import sys

logger = logging.getLogger("kwyre.platform.gpu")

IS_WINDOWS: bool = sys.platform == "win32"
IS_LINUX: bool = sys.platform.startswith("linux")

GPU_RUNTIME: str = "cuda" if IS_WINDOWS else "rocm"


def detect_gpu() -> dict:
    """Return GPU info dict with keys: name, vram_mb, driver_version, runtime.

    Falls back to torch if the CLI tool is unavailable.
    """
    if IS_WINDOWS:
        return _detect_nvidia()
    return _detect_rocm()


def _detect_nvidia() -> dict:
    info = {"name": "unknown", "vram_mb": 0, "driver_version": "unknown", "runtime": "cuda"}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            text=True, timeout=10,
        ).strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 3:
            info["name"] = parts[0]
            info["vram_mb"] = int(float(parts[1]))
            info["driver_version"] = parts[2]
    except FileNotFoundError:
        logger.warning("nvidia-smi not found — falling back to torch for GPU info")
        info = _detect_via_torch(info)
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.warning("nvidia-smi failed (%s) — falling back to torch", exc)
        info = _detect_via_torch(info)
    return info


def _detect_rocm() -> dict:
    info = {"name": "unknown", "vram_mb": 0, "driver_version": "unknown", "runtime": "rocm"}
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--csv"],
            text=True, timeout=10,
        ).strip()
        for line in out.splitlines():
            lower = line.lower()
            if "card" in lower and "name" not in lower:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    info["name"] = parts[1]
            if "total" in lower and "vram" in lower:
                parts = [p.strip() for p in line.split(",")]
                for p in parts:
                    try:
                        mb = int(float(p))
                        if mb > 0:
                            info["vram_mb"] = mb
                            break
                    except ValueError:
                        continue
    except FileNotFoundError:
        try:
            out = subprocess.check_output(["rocminfo"], text=True, timeout=10)
            for line in out.splitlines():
                if "Marketing Name" in line:
                    info["name"] = line.split(":")[-1].strip()
                    break
        except (FileNotFoundError, subprocess.SubprocessError):
            logger.warning("Neither rocm-smi nor rocminfo found — falling back to torch")
            info = _detect_via_torch(info)
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.warning("rocm-smi failed (%s) — falling back to torch", exc)
        info = _detect_via_torch(info)

    try:
        ver_out = subprocess.check_output(
            ["cat", "/opt/rocm/.info/version"], text=True, timeout=5,
        ).strip()
        if ver_out:
            info["driver_version"] = ver_out
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return info


def _detect_via_torch(info: dict) -> dict:
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info["name"] = props.name
            info["vram_mb"] = props.total_memory // (1024 * 1024)
    except Exception as exc:
        logger.warning("torch GPU detection failed: %s", exc)
    return info


def get_gpu_env_var() -> str:
    return "CUDA_VISIBLE_DEVICES" if IS_WINDOWS else "HIP_VISIBLE_DEVICES"


def get_device_string() -> str:
    return "cuda"


def get_gpu_memory_mb() -> int:
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info(0)
            return free // (1024 * 1024)
    except Exception as exc:
        logger.warning("Could not query GPU memory: %s", exc)
    return 0


def check_gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available() and torch.cuda.device_count() > 0
    except ImportError:
        return False


def get_torch_dtype():
    import torch
    return torch.bfloat16


def get_quantization_config():
    import torch
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
