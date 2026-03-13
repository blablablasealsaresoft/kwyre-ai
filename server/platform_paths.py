"""
Kwyre AI — Platform Path Abstraction
======================================
Provides platform-aware default paths for Windows, Linux, macOS,
FreeBSD, and generic Unix. All path functions return pathlib.Path objects.
"""

import os
import sys
from pathlib import Path

_IS_WINDOWS: bool = sys.platform == "win32"
_IS_MACOS: bool = sys.platform == "darwin"
_IS_FREEBSD: bool = sys.platform.startswith("freebsd")


def get_install_dir() -> Path:
    if _IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Kwyre"
    if _IS_FREEBSD:
        return Path("/usr/local/kwyre")
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
    if _IS_MACOS:
        return "com.kwyre.ai.server"
    if _IS_FREEBSD:
        return "kwyre"
    return "kwyre.service"


def get_firewall_name() -> str:
    if _IS_WINDOWS:
        return "Windows Firewall"
    if _IS_MACOS or _IS_FREEBSD:
        return "PF firewall"
    return "iptables"


def ensure_dirs() -> None:
    for d in (get_data_dir(), get_adapter_dir(), get_log_dir(),
              get_cache_dir(), get_license_dir()):
        d.mkdir(parents=True, exist_ok=True)
