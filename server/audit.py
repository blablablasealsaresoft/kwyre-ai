"""
Kwyre Per-User Audit Log
========================
Thread-safe, RAM-only audit tracker for multi-user mode.
Tracks per-user metadata (never conversation content).
"""

import threading
import time
from collections import defaultdict


class UserAuditLog:
    """
    Tracks per-user activity metadata. All data is RAM-only
    and wiped on server shutdown (consistent with Kwyre's
    zero-persistence security model).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stats: dict[str, dict] = {}

    def _ensure_user(self, user_id: str, username: str = ""):
        if user_id not in self._stats:
            self._stats[user_id] = {
                "username": username,
                "request_count": 0,
                "token_count": 0,
                "session_count": 0,
                "last_active": None,
                "rate_limit_hits": 0,
                "failed_auth_attempts": 0,
                "security_events": [],
            }

    def record_request(self, user_id: str, username: str = "", tokens: int = 0):
        with self._lock:
            self._ensure_user(user_id, username)
            s = self._stats[user_id]
            s["request_count"] += 1
            s["token_count"] += tokens
            s["last_active"] = time.time()
            if username:
                s["username"] = username

    def record_session_created(self, user_id: str, username: str = ""):
        with self._lock:
            self._ensure_user(user_id, username)
            self._stats[user_id]["session_count"] += 1

    def record_rate_limit_hit(self, user_id: str, username: str = ""):
        with self._lock:
            self._ensure_user(user_id, username)
            self._stats[user_id]["rate_limit_hits"] += 1
            self._stats[user_id]["last_active"] = time.time()

    def record_failed_auth(self, source_ip: str):
        """Track failed auth by IP (no user_id available for failed attempts)."""
        with self._lock:
            key = f"ip:{source_ip}"
            self._ensure_user(key, f"unknown@{source_ip}")
            self._stats[key]["failed_auth_attempts"] += 1
            self._add_security_event(key, "failed_auth", f"from {source_ip}")

    def record_security_event(self, user_id: str, event_type: str, detail: str = ""):
        with self._lock:
            self._ensure_user(user_id)
            self._add_security_event(user_id, event_type, detail)

    def _add_security_event(self, user_id: str, event_type: str, detail: str):
        events = self._stats[user_id]["security_events"]
        events.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event_type,
            "detail": detail,
        })
        if len(events) > 100:
            self._stats[user_id]["security_events"] = events[-100:]

    def get_user_stats(self, user_id: str) -> dict | None:
        with self._lock:
            if user_id in self._stats:
                return dict(self._stats[user_id])
        return None

    def get_all_stats(self) -> dict:
        with self._lock:
            return {
                uid: dict(s) for uid, s in self._stats.items()
                if not uid.startswith("ip:")
            }

    def get_summary(self) -> dict:
        """Aggregate summary across all users."""
        with self._lock:
            total_requests = 0
            total_tokens = 0
            total_rate_hits = 0
            total_failed_auth = 0
            user_count = 0

            for uid, s in self._stats.items():
                if uid.startswith("ip:"):
                    total_failed_auth += s["failed_auth_attempts"]
                    continue
                user_count += 1
                total_requests += s["request_count"]
                total_tokens += s["token_count"]
                total_rate_hits += s["rate_limit_hits"]

            return {
                "active_users": user_count,
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_rate_limit_hits": total_rate_hits,
                "total_failed_auth_attempts": total_failed_auth,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
