"""
Kwyre Per-User Audit Log
========================
Thread-safe, RAM-only audit tracker for multi-user mode.
Tracks per-user metadata (never conversation content).
"""

import json  # JSON serialization for export formats
import threading  # Thread synchronization primitives
import time  # Timestamps for activity tracking
from collections import defaultdict  # Auto-initializing dictionary


class UserAuditLog:
    """
    Tracks per-user activity metadata. All data is RAM-only
    and wiped on server shutdown (consistent with Kwyre's
    zero-persistence security model).
    """

    def __init__(self):
        self._lock = threading.Lock()  # Mutex for thread-safe audit access
        self._stats: dict[str, dict] = {}  # Map user IDs to activity stats

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
        with self._lock:  # Acquire lock for thread-safe update
            self._ensure_user(user_id, username)  # Create user entry if needed
            s = self._stats[user_id]  # Get user's stats dict
            s["request_count"] += 1  # Increment total request counter
            s["token_count"] += tokens  # Add tokens to running total
            s["last_active"] = time.time()  # Update last activity timestamp
            if username:  # Update username if provided
                s["username"] = username

    def record_session_created(self, user_id: str, username: str = ""):
        with self._lock:  # Acquire lock for thread-safe update
            self._ensure_user(user_id, username)  # Create user entry if needed
            self._stats[user_id]["session_count"] += 1  # Increment session counter

    def record_rate_limit_hit(self, user_id: str, username: str = ""):
        with self._lock:  # Acquire lock for thread-safe update
            self._ensure_user(user_id, username)  # Create user entry if needed
            self._stats[user_id]["rate_limit_hits"] += 1  # Increment rate limit hit counter
            self._stats[user_id]["last_active"] = time.time()  # Update last activity timestamp

    def record_failed_auth(self, source_ip: str):
        """Track failed auth by IP (no user_id available for failed attempts)."""
        with self._lock:  # Acquire lock for thread-safe update
            key = f"ip:{source_ip}"  # Namespace by IP since no user ID exists
            self._ensure_user(key, f"unknown@{source_ip}")  # Create IP-based entry
            self._stats[key]["failed_auth_attempts"] += 1  # Increment failed auth counter
            self._add_security_event(key, "failed_auth", f"from {source_ip}")  # Log security event

    def record_security_event(self, user_id: str, event_type: str, detail: str = ""):
        with self._lock:  # Acquire lock for thread-safe update
            self._ensure_user(user_id)  # Create user entry if needed
            self._add_security_event(user_id, event_type, detail)  # Append event to user's log

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
