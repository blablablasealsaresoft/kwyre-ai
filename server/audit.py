"""
Kwyre Per-User Audit Log
========================
Thread-safe audit tracker for multi-user mode.
Tracks per-user metadata (never conversation content).
Optionally persists usage stats to a JSON file for billing/metering.
"""

import json
import os
import threading
import time


AUDIT_PERSIST_PATH = os.environ.get(
    "KWYRE_AUDIT_FILE",
    os.path.join(os.path.expanduser("~"), ".kwyre", "audit_usage.json"),
)
AUDIT_FLUSH_INTERVAL = int(os.environ.get("KWYRE_AUDIT_FLUSH_SECS", "60"))


class UserAuditLog:
    """
    Tracks per-user activity metadata.
    Persists usage counters to disk periodically so token counts
    survive restarts. Security events are kept in-memory only.
    """

    def __init__(self, persist_path: str = AUDIT_PERSIST_PATH):
        self._lock = threading.Lock()
        self._stats: dict[str, dict] = {}
        self._persist_path = persist_path
        self._dirty = False
        self._load()
        self._start_flush_timer()

    def _load(self):
        """Load persisted usage counters from disk."""
        try:
            if os.path.isfile(self._persist_path):
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                for uid, s in data.items():
                    self._stats[uid] = {
                        "username": s.get("username", ""),
                        "request_count": s.get("request_count", 0),
                        "token_count": s.get("token_count", 0),
                        "session_count": s.get("session_count", 0),
                        "last_active": s.get("last_active"),
                        "rate_limit_hits": s.get("rate_limit_hits", 0),
                        "failed_auth_attempts": s.get("failed_auth_attempts", 0),
                        "security_events": [],
                    }
        except Exception:
            pass

    def _flush(self):
        """Write usage counters to disk (excludes security_events)."""
        with self._lock:
            if not self._dirty:
                return
            self._dirty = False
            snapshot = {}
            for uid, s in self._stats.items():
                snapshot[uid] = {
                    "username": s.get("username", ""),
                    "request_count": s["request_count"],
                    "token_count": s["token_count"],
                    "session_count": s["session_count"],
                    "last_active": s.get("last_active"),
                    "rate_limit_hits": s["rate_limit_hits"],
                    "failed_auth_attempts": s["failed_auth_attempts"],
                }
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            tmp = self._persist_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp, self._persist_path)
        except Exception:
            pass

    def _start_flush_timer(self):
        """Periodically flush stats to disk."""
        def _tick():
            self._flush()
            self._timer = threading.Timer(AUDIT_FLUSH_INTERVAL, _tick)
            self._timer.daemon = True
            self._timer.start()
        self._timer = threading.Timer(AUDIT_FLUSH_INTERVAL, _tick)
        self._timer.daemon = True
        self._timer.start()

    def _ensure_user(self, user_id: str, username: str = ""):
        if user_id not in self._stats:  # Initialize stats entry if first seen
            self._stats[user_id] = {
                "username": username,  # Human-readable user name
                "request_count": 0,  # Total API requests made
                "token_count": 0,  # Total tokens consumed
                "session_count": 0,  # Number of sessions created
                "last_active": None,  # Timestamp of last activity
                "rate_limit_hits": 0,  # Times user hit rate limit
                "failed_auth_attempts": 0,  # Failed authentication count
                "security_events": [],  # Rolling log of security events
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
            self._dirty = True

    def record_session_created(self, user_id: str, username: str = ""):
        with self._lock:
            self._ensure_user(user_id, username)
            self._stats[user_id]["session_count"] += 1
            self._dirty = True

    def record_rate_limit_hit(self, user_id: str, username: str = ""):
        with self._lock:
            self._ensure_user(user_id, username)
            self._stats[user_id]["rate_limit_hits"] += 1
            self._stats[user_id]["last_active"] = time.time()
            self._dirty = True

    def record_failed_auth(self, source_ip: str):
        """Track failed auth by IP (no user_id available for failed attempts)."""
        with self._lock:
            key = f"ip:{source_ip}"
            self._ensure_user(key, f"unknown@{source_ip}")
            self._stats[key]["failed_auth_attempts"] += 1
            self._add_security_event(key, "failed_auth", f"from {source_ip}")
            self._dirty = True

    def record_security_event(self, user_id: str, event_type: str, detail: str = ""):
        with self._lock:
            self._ensure_user(user_id)
            self._add_security_event(user_id, event_type, detail)

    def _add_security_event(self, user_id: str, event_type: str, detail: str):
        events = self._stats[user_id]["security_events"]  # Get user's event list
        events.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),  # UTC ISO-8601 timestamp
            "event": event_type,  # Category of security event
            "detail": detail,  # Human-readable event description
        })
        if len(events) > 100:  # Cap event log at 100 entries
            self._stats[user_id]["security_events"] = events[-100:]  # Keep most recent entries

    def get_user_stats(self, user_id: str) -> dict | None:
        with self._lock:  # Acquire lock for consistent read
            if user_id in self._stats:  # Check if user exists
                return dict(self._stats[user_id])  # Return shallow copy of stats
        return None  # User not found

    def get_all_stats(self) -> dict:
        with self._lock:  # Acquire lock for consistent read
            return {
                uid: dict(s) for uid, s in self._stats.items()
                if not uid.startswith("ip:")  # Exclude IP-based entries from user stats
            }

    def get_summary(self) -> dict:
        """Aggregate summary across all users."""
        with self._lock:  # Acquire lock for consistent aggregation
            total_requests = 0  # Accumulator for total requests
            total_tokens = 0  # Accumulator for total tokens
            total_rate_hits = 0  # Accumulator for rate limit hits
            total_failed_auth = 0  # Accumulator for failed auth attempts
            user_count = 0  # Counter for real users (not IPs)

            for uid, s in self._stats.items():  # Iterate all tracked entities
                if uid.startswith("ip:"):  # Separate IP-based failed auth tracking
                    total_failed_auth += s["failed_auth_attempts"]  # Sum IP-based auth failures
                    continue
                user_count += 1  # Count authenticated users
                total_requests += s["request_count"]  # Sum user requests
                total_tokens += s["token_count"]  # Sum user token usage
                total_rate_hits += s["rate_limit_hits"]  # Sum rate limit incidents

            return {
                "active_users": user_count,  # Total tracked user accounts
                "total_requests": total_requests,  # Aggregate request count
                "total_tokens": total_tokens,  # Aggregate token consumption
                "total_rate_limit_hits": total_rate_hits,  # Aggregate rate limit violations
                "total_failed_auth_attempts": total_failed_auth,  # Aggregate auth failures
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),  # UTC timestamp of summary
            }

    def export_jsonl(self) -> str:
        """Export all audit events as JSON Lines (one event per line) for SIEM ingestion."""
        with self._lock:  # Acquire lock for consistent export
            lines = []  # Accumulate output lines
            for uid, s in self._stats.items():  # Iterate all tracked users
                base = {
                    "user_id": uid,  # User identifier or IP key
                    "username": s.get("username", ""),  # Human-readable username
                    "request_count": s["request_count"],  # Total requests by user
                    "token_count": s["token_count"],  # Total tokens consumed
                    "session_count": s["session_count"],  # Sessions created by user
                    "rate_limit_hits": s["rate_limit_hits"],  # Times user hit rate limit
                    "failed_auth_attempts": s["failed_auth_attempts"],  # Failed auth count
                    "last_active": s.get("last_active"),  # Last activity timestamp
                }
                lines.append(json.dumps(base))  # Serialize user summary as JSON line
                for evt in s.get("security_events", []):  # Iterate user's security events
                    event_line = {
                        "user_id": uid,  # Associate event with user
                        "username": s.get("username", ""),  # Include username for context
                        "event_type": evt.get("event", ""),  # Security event category
                        "detail": evt.get("detail", ""),  # Event description
                        "timestamp": evt.get("timestamp", ""),  # When event occurred
                    }
                    lines.append(json.dumps(event_line))  # Serialize event as JSON line
            return "\n".join(lines)  # Join all lines with newlines

    def export_cef(self) -> str:
        """Export audit events in CEF (Common Event Format) for Splunk/QRadar."""
        with self._lock:  # Acquire lock for consistent export
            lines = []  # Accumulate CEF-formatted lines
            for uid, s in self._stats.items():  # Iterate all tracked users
                username = s.get("username", uid)  # Use username or fall back to uid
                ts = s.get("last_active")  # Get last activity timestamp
                ts_str = time.strftime("%b %d %Y %H:%M:%S", time.gmtime(ts)) if ts else "unknown"  # Format timestamp for CEF
                lines.append(
                    f"CEF:0|Kwyre|AI-Server|1.1|100|User Activity|3|"
                    f"duser={username} "
                    f"cn1={s['request_count']} cn1Label=RequestCount "
                    f"cn2={s['token_count']} cn2Label=TokenCount "
                    f"cn3={s['rate_limit_hits']} cn3Label=RateLimitHits "
                    f"rt={ts_str}"
                )  # Build CEF user activity record
                for evt in s.get("security_events", []):  # Iterate user's security events
                    severity = "7" if evt.get("event") == "failed_auth" else "5"  # High severity for auth failures
                    lines.append(
                        f"CEF:0|Kwyre|AI-Server|1.1|200|Security Event|{severity}|"
                        f"duser={username} "
                        f"act={evt.get('event', '')} "
                        f"msg={evt.get('detail', '')} "
                        f"rt={evt.get('timestamp', '')}"
                    )  # Build CEF security event record
            return "\n".join(lines)  # Join all lines with newlines
