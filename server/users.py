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

import argparse  # CLI argument parsing for user management commands
import json  # JSON serialization for user data
import os  # Environment variables and filesystem operations
import secrets  # Cryptographically secure token generation
import sys  # System exit and platform detection
import time  # Timestamps for user activity tracking
import threading  # Thread synchronization primitives
from pathlib import Path  # Object-oriented filesystem paths

from cryptography.fernet import Fernet, InvalidToken  # Symmetric encryption for user file

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Resolve project root directory

ROLES = {
    "admin": {
        "description": "Full access — inference, all sessions, user management, audit",
        "can_inference": True,  # Allowed to run model inference
        "can_admin": True,  # Allowed to manage users and sessions
        "can_audit": True,  # Allowed to view audit logs
    },
    "analyst": {
        "description": "Inference + own sessions only",
        "can_inference": True,  # Allowed to run model inference
        "can_admin": False,  # Cannot manage other users
        "can_audit": False,  # Cannot view audit logs
    },
    "viewer": {
        "description": "Read-only health and audit endpoints",
        "can_inference": False,  # Cannot run model inference
        "can_admin": False,  # Cannot manage users
        "can_audit": True,  # Allowed to view audit logs
    },
}

DEFAULT_MAX_SESSIONS = int(os.environ.get("KWYRE_MAX_SESSIONS_PER_USER", "5"))  # Max concurrent sessions per user
DEFAULT_RPM = int(os.environ.get("KWYRE_DEFAULT_RPM", "30"))  # Default requests per minute limit


def _generate_api_key() -> str:
    return f"sk-kwyre-{secrets.token_hex(24)}"  # Generate prefixed 48-char hex API key


def _get_master_key() -> bytes:
    """
    Retrieve the Fernet master key from KWYRE_MASTER_KEY env var.
    The value must be a URL-safe base64-encoded 32-byte key (Fernet format).
    """
    raw = os.environ.get("KWYRE_MASTER_KEY", "")  # Read master key from environment
    if not raw:  # Fail if master key not configured
        raise EnvironmentError(
            "KWYRE_MASTER_KEY not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "Or run: python server/users.py init"
        )
    return raw.encode()  # Convert string to bytes for Fernet


def _get_users_file() -> str:
    return os.environ.get(
        "KWYRE_USERS_FILE",
        os.path.join(_project_root, "users.json"),
    )  # Get users file path from env or default location


class UserManager:
    """
    Thread-safe user management with Fernet-encrypted storage.
    All mutations are immediately flushed to the encrypted file.
    """

    def __init__(self, users_file: str = None, master_key: bytes = None):
        self._file = users_file or _get_users_file()  # Set users file path
        self._key = master_key or _get_master_key()  # Set encryption master key
        self._fernet = Fernet(self._key)  # Initialize Fernet cipher with master key
        self._lock = threading.Lock()  # Mutex for thread-safe user operations
        self._users: dict[str, dict] = {}  # In-memory user store keyed by user ID
        self._key_index: dict[str, str] = {}  # Reverse index: api_key -> user_id
        self._load()  # Load and decrypt users from disk

    def _load(self):
        if not os.path.exists(self._file):  # No file means fresh install
            self._users = {}  # Start with empty user store
            self._key_index = {}  # Start with empty key index
            return
        with open(self._file, "rb") as f:  # Open encrypted file in binary mode
            encrypted = f.read()  # Read encrypted blob
        try:
            decrypted = self._fernet.decrypt(encrypted)  # Decrypt with master key
            self._users = json.loads(decrypted.decode("utf-8"))  # Parse decrypted JSON into user dict
        except InvalidToken:  # Decryption failed due to wrong key or corruption
            raise ValueError(
                f"Failed to decrypt {self._file} — wrong KWYRE_MASTER_KEY or corrupted file."
            )
        self._rebuild_index()  # Rebuild API key reverse lookup index

    def _rebuild_index(self):
        self._key_index = {}  # Reset reverse index
        for uid, u in self._users.items():  # Iterate all users
            self._key_index[u["api_key"]] = uid  # Map each API key to its user ID

    def _save(self):
        raw = json.dumps(self._users, indent=2).encode("utf-8")  # Serialize users to formatted JSON bytes
        encrypted = self._fernet.encrypt(raw)  # Encrypt with Fernet master key
        tmp = self._file + ".tmp"  # Write to temp file for atomic replace
        with open(tmp, "wb") as f:  # Open temp file in binary mode
            f.write(encrypted)  # Write encrypted data
        os.replace(tmp, self._file)  # Atomically replace old file with new

    def authenticate(self, api_key: str) -> dict | None:
        """
        Constant-time lookup by API key.
        Returns user dict (with 'id' field) or None.
        """
        with self._lock:  # Acquire lock for thread-safe lookup
            import hmac  # Import for constant-time comparison
            for stored_key, uid in self._key_index.items():  # Iterate all stored keys
                if hmac.compare_digest(api_key, stored_key):  # Constant-time compare to prevent timing attacks
                    user = dict(self._users[uid])  # Copy user data dict
                    user["id"] = uid  # Attach user ID to result
                    return user  # Return authenticated user
        return None  # No matching key found

    def update_last_active(self, user_id: str):
        with self._lock:  # Acquire lock for thread-safe update
            if user_id in self._users:  # Check user exists
                self._users[user_id]["last_active"] = time.time()  # Set last active to now
                self._save()  # Persist change to encrypted file

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
        if role not in ROLES:  # Validate role against defined roles
            raise ValueError(f"Invalid role '{role}'. Must be one of: {list(ROLES.keys())}")

        with self._lock:  # Acquire lock for atomic user creation
            for u in self._users.values():  # Check for duplicate username
                if u["username"] == username:  # Reject if username already taken
                    raise ValueError(f"User '{username}' already exists.")

            uid = secrets.token_hex(8)  # Generate random 16-char hex user ID
            api_key = _generate_api_key()  # Generate unique API key

            user = {
                "username": username,  # Store display username
                "role": role,  # Assign permission role
                "api_key": api_key,  # Store generated API key
                "created_at": time.time(),  # Record creation timestamp
                "last_active": None,  # No activity yet
                "max_sessions": max_sessions or DEFAULT_MAX_SESSIONS,  # Set session limit
                "rate_limit_rpm": rate_limit_rpm or DEFAULT_RPM,  # Set rate limit
            }
            self._users[uid] = user  # Add user to in-memory store
            self._key_index[api_key] = uid  # Update API key reverse index
            self._save()  # Persist to encrypted file

            result = dict(user)  # Copy user dict for return
            result["id"] = uid  # Attach user ID
            return result, api_key  # Return user data and API key

    def remove_user(self, username: str) -> str | None:
        """Remove a user by username. Returns user_id if found."""
        with self._lock:  # Acquire lock for atomic removal
            for uid, u in self._users.items():  # Search by username
                if u["username"] == username:  # Found matching user
                    self._key_index.pop(u["api_key"], None)  # Remove from key index
                    del self._users[uid]  # Remove from user store
                    self._save()  # Persist removal to encrypted file
                    return uid  # Return removed user's ID
        return None  # User not found

    def reset_api_key(self, username: str) -> str | None:
        """Generate a new API key for a user. Returns the new key."""
        with self._lock:  # Acquire lock for atomic key rotation
            for uid, u in self._users.items():  # Search by username
                if u["username"] == username:  # Found matching user
                    self._key_index.pop(u["api_key"], None)  # Remove old key from index
                    new_key = _generate_api_key()  # Generate fresh API key
                    u["api_key"] = new_key  # Update user's API key
                    self._key_index[new_key] = uid  # Index new key
                    self._save()  # Persist to encrypted file
                    return new_key  # Return the new API key
        return None  # User not found

    def get_user(self, username: str) -> dict | None:
        with self._lock:  # Acquire lock for thread-safe lookup
            for uid, u in self._users.items():  # Search by username
                if u["username"] == username:  # Found matching user
                    result = dict(u)  # Copy user dict
                    result["id"] = uid  # Attach user ID
                    return result  # Return user data
        return None  # User not found

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._lock:  # Acquire lock for thread-safe lookup
            if user_id in self._users:  # Check if user ID exists
                result = dict(self._users[user_id])  # Copy user dict
                result["id"] = user_id  # Attach user ID
                return result  # Return user data
        return None  # User not found

    def list_users(self, include_keys: bool = False) -> list[dict]:
        """List all users. API keys are excluded unless include_keys=True."""
        with self._lock:  # Acquire lock for consistent snapshot
            result = []  # Accumulate user entries
            for uid, u in self._users.items():  # Iterate all users
                entry = {
                    "id": uid,  # User identifier
                    "username": u["username"],  # Display name
                    "role": u["role"],  # Permission role
                    "created_at": u["created_at"],  # Account creation time
                    "last_active": u["last_active"],  # Last activity timestamp
                    "max_sessions": u["max_sessions"],  # Session limit
                    "rate_limit_rpm": u["rate_limit_rpm"],  # Rate limit setting
                }
                if include_keys:  # Only include API key if explicitly requested
                    entry["api_key"] = u["api_key"]
                result.append(entry)  # Add entry to result list
            return result  # Return list of user summaries

    def user_count(self) -> int:
        with self._lock:  # Acquire lock for consistent count
            return len(self._users)  # Return total user count

    def has_users(self) -> bool:
        with self._lock:  # Acquire lock for consistent check
            return len(self._users) > 0  # True if any users exist


def init_command():
    """Initialize multi-user mode: generate master key and create default admin."""
    master_key_env = os.environ.get("KWYRE_MASTER_KEY", "")  # Check for existing master key
    if not master_key_env:  # Generate new key if not set
        new_key = Fernet.generate_key().decode()  # Generate Fernet-compatible master key
        print(f"Generated KWYRE_MASTER_KEY (save this securely):\n")
        print(f"  {new_key}\n")
        print("Set it as an environment variable before starting the server:")
        if sys.platform == "win32":  # Windows-specific env var syntax
            print(f'  set KWYRE_MASTER_KEY={new_key}')
        else:  # Unix/Mac env var syntax
            print(f"  export KWYRE_MASTER_KEY={new_key}")
        print()
        os.environ["KWYRE_MASTER_KEY"] = new_key  # Set for current process

    mgr = UserManager()  # Initialize user manager with master key
    if mgr.has_users():  # Skip creation if users already exist
        print("Users file already contains users. Skipping default admin creation.")
        return

    user, api_key = mgr.add_user("admin", role="admin")  # Create default admin account
    print(f"Default admin user created:")
    print(f"  Username: admin")
    print(f"  Role:     admin")
    print(f"  API Key:  {api_key}")
    print(f"\nStore the API key securely — it cannot be retrieved later.")
    print(f"Users file: {mgr._file} (encrypted)")


def main():
    parser = argparse.ArgumentParser(description="Kwyre Multi-User Management")  # Create CLI argument parser
    sub = parser.add_subparsers(dest="command")  # Add subcommand support

    sub.add_parser("init", help="Initialize: generate master key + default admin")  # Register init subcommand

    add_p = sub.add_parser("add", help="Add a new user")  # Register add subcommand
    add_p.add_argument("--username", required=True)  # Username is required for add
    add_p.add_argument("--role", default="analyst", choices=list(ROLES.keys()))  # Role with validation
    add_p.add_argument("--max-sessions", type=int, default=None)  # Optional session limit override
    add_p.add_argument("--rpm", type=int, default=None, help="Rate limit (requests/minute)")  # Optional rate limit override

    sub.add_parser("list", help="List all users")  # Register list subcommand

    rm_p = sub.add_parser("remove", help="Remove a user")  # Register remove subcommand
    rm_p.add_argument("--username", required=True)  # Username is required for remove

    rk_p = sub.add_parser("reset-key", help="Generate new API key for a user")  # Register reset-key subcommand
    rk_p.add_argument("--username", required=True)  # Username is required for key reset

    args = parser.parse_args()  # Parse CLI arguments

    if args.command == "init":  # Handle init command
        init_command()
    elif args.command == "add":  # Handle add user command
        mgr = UserManager()  # Initialize user manager
        try:
            user, api_key = mgr.add_user(
                args.username, role=args.role,
                max_sessions=args.max_sessions,
                rate_limit_rpm=args.rpm,
            )  # Create new user with provided options
            print(f"User created:")
            print(f"  Username: {user['username']}")
            print(f"  Role:     {user['role']}")
            print(f"  API Key:  {api_key}")
            print(f"\nStore the API key securely — it cannot be retrieved later.")
        except ValueError as e:  # Handle duplicate username or invalid role
            print(f"Error: {e}")
            sys.exit(1)  # Exit with error code
    elif args.command == "list":  # Handle list users command
        mgr = UserManager()  # Initialize user manager
        users = mgr.list_users()  # Fetch all user summaries
        if not users:  # Handle empty user list
            print("No users found.")
            return
        print(f"{'Username':<20} {'Role':<10} {'Sessions':<10} {'RPM':<6} {'Last Active'}")  # Print table header
        print("-" * 70)  # Print header separator
        for u in users:  # Print each user row
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["last_active"])) if u["last_active"] else "never"  # Format last active time
            print(f"{u['username']:<20} {u['role']:<10} {u['max_sessions']:<10} {u['rate_limit_rpm']:<6} {last}")  # Print formatted user row
    elif args.command == "remove":  # Handle remove user command
        mgr = UserManager()  # Initialize user manager
        uid = mgr.remove_user(args.username)  # Attempt to remove user
        if uid:  # User was found and removed
            print(f"User '{args.username}' removed (id={uid}).")
        else:  # User not found
            print(f"User '{args.username}' not found.")
            sys.exit(1)  # Exit with error code
    elif args.command == "reset-key":  # Handle API key reset command
        mgr = UserManager()  # Initialize user manager
        new_key = mgr.reset_api_key(args.username)  # Generate and save new API key
        if new_key:  # Key was successfully rotated
            print(f"New API key for '{args.username}':")
            print(f"  {new_key}")
        else:  # User not found
            print(f"User '{args.username}' not found.")
            sys.exit(1)  # Exit with error code
    else:  # No valid subcommand provided
        parser.print_help()  # Show usage help


if __name__ == "__main__":
    main()  # Execute CLI when run directly
