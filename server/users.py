#!/usr/bin/env python3
"""
Kwyre Multi-User Management
============================
Manages user accounts for multi-user air-gapped server mode.

Users are stored in a JSON file encrypted at rest with Fernet symmetric
encryption (from the `cryptography` package, already a dependency).

CLI usage:
  python server/users.py add --username alice --role analyst
  python server/users.py list
  python server/users.py remove --username alice
  python server/users.py reset-key --username alice
  python server/users.py init   # create default admin + generate master key
"""

import argparse
import json
import os
import secrets
import sys
import time
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROLES = {
    "admin": {
        "description": "Full access — inference, all sessions, user management, audit",
        "can_inference": True,
        "can_admin": True,
        "can_audit": True,
    },
    "analyst": {
        "description": "Inference + own sessions only",
        "can_inference": True,
        "can_admin": False,
        "can_audit": False,
    },
    "viewer": {
        "description": "Read-only health and audit endpoints",
        "can_inference": False,
        "can_admin": False,
        "can_audit": True,
    },
}

DEFAULT_MAX_SESSIONS = int(os.environ.get("KWYRE_MAX_SESSIONS_PER_USER", "5"))
DEFAULT_RPM = int(os.environ.get("KWYRE_DEFAULT_RPM", "30"))


def _generate_api_key() -> str:
    return f"sk-kwyre-{secrets.token_hex(24)}"


def _get_master_key() -> bytes:
    """
    Retrieve the Fernet master key from KWYRE_MASTER_KEY env var.
    The value must be a URL-safe base64-encoded 32-byte key (Fernet format).
    """
    raw = os.environ.get("KWYRE_MASTER_KEY", "")
    if not raw:
        raise EnvironmentError(
            "KWYRE_MASTER_KEY not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "Or run: python server/users.py init"
        )
    return raw.encode()


def _get_users_file() -> str:
    return os.environ.get(
        "KWYRE_USERS_FILE",
        os.path.join(_project_root, "users.json"),
    )


class UserManager:
    """
    Thread-safe user management with Fernet-encrypted storage.
    All mutations are immediately flushed to the encrypted file.
    """

    def __init__(self, users_file: str = None, master_key: bytes = None):
        self._file = users_file or _get_users_file()
        self._key = master_key or _get_master_key()
        self._fernet = Fernet(self._key)
        self._lock = threading.Lock()
        self._users: dict[str, dict] = {}
        self._key_index: dict[str, str] = {}  # api_key -> user_id
        self._load()

    def _load(self):
        if not os.path.exists(self._file):
            self._users = {}
            self._key_index = {}
            return
        with open(self._file, "rb") as f:
            encrypted = f.read()
        try:
            decrypted = self._fernet.decrypt(encrypted)
            self._users = json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            raise ValueError(
                f"Failed to decrypt {self._file} — wrong KWYRE_MASTER_KEY or corrupted file."
            )
        self._rebuild_index()

    def _rebuild_index(self):
        self._key_index = {}
        for uid, u in self._users.items():
            self._key_index[u["api_key"]] = uid

    def _save(self):
        raw = json.dumps(self._users, indent=2).encode("utf-8")
        encrypted = self._fernet.encrypt(raw)
        tmp = self._file + ".tmp"
        with open(tmp, "wb") as f:
            f.write(encrypted)
        os.replace(tmp, self._file)

    def authenticate(self, api_key: str) -> dict | None:
        """
        Constant-time lookup by API key.
        Returns user dict (with 'id' field) or None.
        """
        with self._lock:
            import hmac
            for stored_key, uid in self._key_index.items():
                if hmac.compare_digest(api_key, stored_key):
                    user = dict(self._users[uid])
                    user["id"] = uid
                    return user
        return None

    def update_last_active(self, user_id: str):
        with self._lock:
            if user_id in self._users:
                self._users[user_id]["last_active"] = time.time()
                self._save()

    def add_user(
        self,
        username: str,
        role: str = "analyst",
        max_sessions: int = None,
        rate_limit_rpm: int = None,
    ) -> tuple[dict, str]:
        """
        Create a new user. Returns (user_dict, api_key).
        The api_key is only returned at creation time.
        """
        if role not in ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of: {list(ROLES.keys())}")

        with self._lock:
            for u in self._users.values():
                if u["username"] == username:
                    raise ValueError(f"User '{username}' already exists.")

            uid = secrets.token_hex(8)
            api_key = _generate_api_key()

            user = {
                "username": username,
                "role": role,
                "api_key": api_key,
                "created_at": time.time(),
                "last_active": None,
                "max_sessions": max_sessions or DEFAULT_MAX_SESSIONS,
                "rate_limit_rpm": rate_limit_rpm or DEFAULT_RPM,
            }
            self._users[uid] = user
            self._key_index[api_key] = uid
            self._save()

            result = dict(user)
            result["id"] = uid
            return result, api_key

    def remove_user(self, username: str) -> str | None:
        """Remove a user by username. Returns user_id if found."""
        with self._lock:
            for uid, u in self._users.items():
                if u["username"] == username:
                    self._key_index.pop(u["api_key"], None)
                    del self._users[uid]
                    self._save()
                    return uid
        return None

    def reset_api_key(self, username: str) -> str | None:
        """Generate a new API key for a user. Returns the new key."""
        with self._lock:
            for uid, u in self._users.items():
                if u["username"] == username:
                    self._key_index.pop(u["api_key"], None)
                    new_key = _generate_api_key()
                    u["api_key"] = new_key
                    self._key_index[new_key] = uid
                    self._save()
                    return new_key
        return None

    def get_user(self, username: str) -> dict | None:
        with self._lock:
            for uid, u in self._users.items():
                if u["username"] == username:
                    result = dict(u)
                    result["id"] = uid
                    return result
        return None

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._lock:
            if user_id in self._users:
                result = dict(self._users[user_id])
                result["id"] = user_id
                return result
        return None

    def list_users(self, include_keys: bool = False) -> list[dict]:
        """List all users. API keys are excluded unless include_keys=True."""
        with self._lock:
            result = []
            for uid, u in self._users.items():
                entry = {
                    "id": uid,
                    "username": u["username"],
                    "role": u["role"],
                    "created_at": u["created_at"],
                    "last_active": u["last_active"],
                    "max_sessions": u["max_sessions"],
                    "rate_limit_rpm": u["rate_limit_rpm"],
                }
                if include_keys:
                    entry["api_key"] = u["api_key"]
                result.append(entry)
            return result

    def user_count(self) -> int:
        with self._lock:
            return len(self._users)

    def has_users(self) -> bool:
        with self._lock:
            return len(self._users) > 0


def init_command():
    """Initialize multi-user mode: generate master key and create default admin."""
    master_key_env = os.environ.get("KWYRE_MASTER_KEY", "")
    if not master_key_env:
        new_key = Fernet.generate_key().decode()
        print(f"Generated KWYRE_MASTER_KEY (save this securely):\n")
        print(f"  {new_key}\n")
        print("Set it as an environment variable before starting the server:")
        if sys.platform == "win32":
            print(f'  set KWYRE_MASTER_KEY={new_key}')
        else:
            print(f"  export KWYRE_MASTER_KEY={new_key}")
        print()
        os.environ["KWYRE_MASTER_KEY"] = new_key

    mgr = UserManager()
    if mgr.has_users():
        print("Users file already contains users. Skipping default admin creation.")
        return

    user, api_key = mgr.add_user("admin", role="admin")
    print(f"Default admin user created:")
    print(f"  Username: admin")
    print(f"  Role:     admin")
    print(f"  API Key:  {api_key}")
    print(f"\nStore the API key securely — it cannot be retrieved later.")
    print(f"Users file: {mgr._file} (encrypted)")


def main():
    parser = argparse.ArgumentParser(description="Kwyre Multi-User Management")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize: generate master key + default admin")

    add_p = sub.add_parser("add", help="Add a new user")
    add_p.add_argument("--username", required=True)
    add_p.add_argument("--role", default="analyst", choices=list(ROLES.keys()))
    add_p.add_argument("--max-sessions", type=int, default=None)
    add_p.add_argument("--rpm", type=int, default=None, help="Rate limit (requests/minute)")

    sub.add_parser("list", help="List all users")

    rm_p = sub.add_parser("remove", help="Remove a user")
    rm_p.add_argument("--username", required=True)

    rk_p = sub.add_parser("reset-key", help="Generate new API key for a user")
    rk_p.add_argument("--username", required=True)

    args = parser.parse_args()

    if args.command == "init":
        init_command()
    elif args.command == "add":
        mgr = UserManager()
        try:
            user, api_key = mgr.add_user(
                args.username, role=args.role,
                max_sessions=args.max_sessions,
                rate_limit_rpm=args.rpm,
            )
            print(f"User created:")
            print(f"  Username: {user['username']}")
            print(f"  Role:     {user['role']}")
            print(f"  API Key:  {api_key}")
            print(f"\nStore the API key securely — it cannot be retrieved later.")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif args.command == "list":
        mgr = UserManager()
        users = mgr.list_users()
        if not users:
            print("No users found.")
            return
        print(f"{'Username':<20} {'Role':<10} {'Sessions':<10} {'RPM':<6} {'Last Active'}")
        print("-" * 70)
        for u in users:
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["last_active"])) if u["last_active"] else "never"
            print(f"{u['username']:<20} {u['role']:<10} {u['max_sessions']:<10} {u['rate_limit_rpm']:<6} {last}")
    elif args.command == "remove":
        mgr = UserManager()
        uid = mgr.remove_user(args.username)
        if uid:
            print(f"User '{args.username}' removed (id={uid}).")
        else:
            print(f"User '{args.username}' not found.")
            sys.exit(1)
    elif args.command == "reset-key":
        mgr = UserManager()
        new_key = mgr.reset_api_key(args.username)
        if new_key:
            print(f"New API key for '{args.username}':")
            print(f"  {new_key}")
        else:
            print(f"User '{args.username}' not found.")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
