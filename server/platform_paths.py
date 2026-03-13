"""
Kwyre AI — Platform Path Abstraction
======================================
Provides platform-aware default paths for Linux and Windows.
All path functions return pathlib.Path objects.
"""

import os
import sys
from pathlib import Path

_IS_WINDOWS: bool = sys.platform == "win32"


def get_install_dir() -> Path:
    if _IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Kwyre"
    return Path("/opt/kwyre")


def get_data_dir() -> Path:
    return Path.home() / ".kwyre"


def get_adapter_dir() -> Path:
    return get_data_dir() / "adapters"


def get_log_dir() -> Path:
    return get_data_dir() / "logs"


def get_cache_dir() -> Path:
    hf_cache = os.environ.get("HF_HOME") or os.environ.get("HF_CACHE")
    if hf_cache:
        return Path(hf_cache)
    return Path.home() / ".cache" / "huggingface"


def get_license_dir() -> Path:
    return get_data_dir() / "license"


def get_venv_python() -> str:
    if _IS_WINDOWS:
        return r"venv\Scripts\python.exe"
    return "venv/bin/python"


def get_venv_pip() -> str:
    if _IS_WINDOWS:
        return r"venv\Scripts\pip.exe"
    return "venv/bin/pip"


def get_null_device() -> str:
    if _IS_WINDOWS:
        return "NUL"
    return "/dev/null"


def get_service_name() -> str:
    if _IS_WINDOWS:
        return "KwyreAI"
    return "kwyre.service"


def ensure_dirs() -> None:
    for d in (get_data_dir(), get_adapter_dir(), get_log_dir(),
              get_cache_dir(), get_license_dir()):
        d.mkdir(parents=True, exist_ok=True)
