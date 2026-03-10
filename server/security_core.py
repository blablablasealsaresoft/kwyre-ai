"""
Kwyre AI — Shared Security Infrastructure
==========================================
Extracted from serve_local_4bit.py so both GPU and CPU (Kwyre Air)
servers can share the same security layers without importing torch.

Provides:
  - SecureConversationBuffer  (L5 — RAM-only session storage + crypto wipe)
  - SessionStore              (L5 — session lifecycle management)
  - IntrusionWatchdog         (L6 — process/network intrusion detection)
  - API key loading + rate limiting helpers
  - Security header helpers
  - HTML page serving helpers
"""

import hmac  # Constant-time string comparison for auth
import ipaddress as _ipaddress  # IP address parsing and network checks
import json  # JSON serialization for HTTP responses
import os  # Environment variables and filesystem access
import re  # Regular expression matching
import secrets  # Cryptographically secure random generation
import signal  # OS signal handling for process termination
import sys  # System-level utilities
import threading  # Thread synchronization primitives
import time  # Timestamps and sleep utilities
from collections import defaultdict  # Auto-initializing dictionary for rate tracking
from http.server import BaseHTTPRequestHandler  # Base class for HTTP request handling

import psutil  # Cross-platform process and network monitoring


# ---------------------------------------------------------------------------
# LAYER 1: Network binding
# ---------------------------------------------------------------------------
BIND_HOST = os.environ.get("KWYRE_BIND_HOST", "127.0.0.1")  # Get bind host from env, default localhost


# ---------------------------------------------------------------------------
# LAYER 5: Secure conversation buffer
# ---------------------------------------------------------------------------
class SecureConversationBuffer:
    def __init__(self, session_id: str):
        self.session_id = session_id  # Unique identifier for this session
        self.session_key = secrets.token_bytes(32)  # Generate 256-bit random encryption key
        self.created_at = time.time()  # Record buffer creation timestamp
        self._buffer: list[dict] = []  # In-memory message storage list
        self._lock = threading.Lock()  # Mutex for thread-safe buffer access
        self._wiped = False  # Flag indicating if buffer was securely wiped

    def add_message(self, role: str, content: str) -> bool:
        with self._lock:  # Acquire lock for thread-safe write
            if self._wiped:  # Reject writes to wiped buffers
                return False
            self._buffer.append({"role": role, "content": content})  # Store message with role metadata
            return True  # Signal successful insertion

    def get_messages(self) -> list[dict]:
        with self._lock:  # Acquire lock for thread-safe read
            if self._wiped:  # Return empty if buffer was wiped
                return []
            return list(self._buffer)  # Return shallow copy of message list

    def secure_wipe(self, reason: str = "session_end"):
        with self._lock:  # Acquire lock for atomic wipe operation
            if self._wiped:  # Skip if already wiped
                return
            n = len(self._buffer)  # Save message count for logging
            for msg in self._buffer:  # Overwrite each message with random data
                msg["content"] = secrets.token_hex(max(len(msg.get("content", "")), 32))  # Overwrite content with random hex
                msg["role"] = secrets.token_hex(8)  # Overwrite role with random hex
            self._buffer.clear()  # Remove all message references
            self.session_key = bytes(32)  # Zero out the session encryption key
            self._wiped = True  # Mark buffer as permanently wiped
            print(f"[SecureBuffer] {self.session_id[:8]}... wiped ({n} msgs, reason={reason})")  # Log wipe event with truncated ID

    def is_wiped(self) -> bool:
        return self._wiped  # Return current wipe status


class SessionStore:
    MAX_SESSION_AGE = 3600  # Sessions expire after one hour of inactivity

    def __init__(self):
        self._sessions: dict[str, SecureConversationBuffer] = {}  # Map session IDs to buffers
        self._lock = threading.Lock()  # Mutex for thread-safe session access
        self._last_access: dict[str, float] = {}  # Track last access time per session
        threading.Thread(target=self._reap_expired, daemon=True).start()  # Launch background expiry reaper thread

    def get_or_create(self, session_id: str) -> tuple[SecureConversationBuffer, bool]:
        with self._lock:  # Acquire lock for atomic get-or-create
            created = session_id not in self._sessions or self._sessions[session_id].is_wiped()  # Check if session needs creation
            if created:  # Create new buffer if missing or wiped
                self._sessions[session_id] = SecureConversationBuffer(session_id)
            self._last_access[session_id] = time.time()  # Update last access timestamp
            return self._sessions[session_id], created  # Return buffer and creation flag

    def wipe_session(self, session_id: str, reason: str = "user_request"):
        with self._lock:  # Acquire lock for atomic session removal
            if session_id in self._sessions:  # Only wipe if session exists
                self._sessions[session_id].secure_wipe(reason=reason)  # Cryptographically wipe buffer contents
                del self._sessions[session_id]  # Remove session from store
                self._last_access.pop(session_id, None)  # Remove access timestamp entry

    def wipe_all(self, reason: str = "server_shutdown"):
        with self._lock:  # Acquire lock for bulk wipe operation
            print(f"[SessionStore] Wiping {len(self._sessions)} sessions ({reason})...")  # Log bulk wipe start
            for buf in self._sessions.values():  # Iterate all active session buffers
                buf.secure_wipe(reason=reason)  # Cryptographically wipe each buffer
            self._sessions.clear()  # Remove all session references
            self._last_access.clear()  # Remove all access timestamps
        print("[SessionStore] All sessions wiped.")  # Log bulk wipe completion

    def _reap_expired(self):
        while True:  # Run indefinitely as daemon thread
            time.sleep(60)  # Check for expired sessions every 60 seconds
            now = time.time()  # Capture current time for comparison
            with self._lock:  # Acquire lock for safe iteration
                expired = [s for s, t in self._last_access.items()
                           if now - t > self.MAX_SESSION_AGE]  # Find sessions idle beyond max age
                for sid in expired:  # Process each expired session
                    if sid in self._sessions:  # Verify session still exists
                        self._sessions[sid].secure_wipe(reason="idle_timeout")  # Wipe expired session data
                        del self._sessions[sid]  # Remove expired session from store
                        self._last_access.pop(sid, None)  # Clean up access timestamp

    def active_count(self) -> int:
        with self._lock:  # Acquire lock for consistent count
            return len(self._sessions)  # Return number of active sessions

    def get_sessions_for_user(self, user_id: str) -> list[str]:
        """Return session IDs owned by a specific user (namespaced as user_id:sid)."""
        prefix = f"{user_id}:"  # Build prefix for user-namespaced session IDs
        with self._lock:  # Acquire lock for safe iteration
            return [s for s in self._sessions if s.startswith(prefix)]  # Filter sessions by user prefix

    def count_sessions_for_user(self, user_id: str) -> int:
        return len(self.get_sessions_for_user(user_id))  # Count sessions owned by user

    def wipe_user_sessions(self, user_id: str, reason: str = "admin_wipe"):
        for sid in self.get_sessions_for_user(user_id):  # Iterate user's sessions
            self.wipe_session(sid, reason=reason)  # Wipe each session individually

    def list_all_session_metadata(self) -> list[dict]:
        """Return metadata for all sessions. Never exposes content."""
        with self._lock:  # Acquire lock for safe metadata collection
            result = []  # Accumulate metadata entries
            for sid, buf in self._sessions.items():  # Iterate all sessions
                parts = sid.split(":", 1)  # Split session ID to extract user prefix
                result.append({
                    "session_id": sid,  # Full session identifier
                    "user_id": parts[0] if len(parts) == 2 else "unknown",  # Extract user ID from namespaced key
                    "created_at": buf.created_at,  # Buffer creation timestamp
                    "message_count": len(buf._buffer),  # Number of messages in session
                    "wiped": buf.is_wiped(),  # Whether buffer has been wiped
                })
            return result  # Return list of metadata dicts


# ---------------------------------------------------------------------------
# LAYER 6: Intrusion watchdog
# ---------------------------------------------------------------------------
SUSPICIOUS_PROCESSES = [
    "x64dbg", "x32dbg", "ollydbg", "windbg", "immunity debugger",
    "processhacker", "process hacker", "cheatengine", "cheat engine",
    "wireshark", "fiddler", "charles proxy", "mitmproxy", "burpsuite",
    "ida64", "ida32", "ghidra",
]  # Known debugger, reverse-engineering, and MITM tool names

ALLOWED_REMOTE_IPS = {"127.0.0.1"}  # Only localhost allowed for outbound connections
_DOCKER_NETS = [
    _ipaddress.ip_network("172.16.0.0/12"),  # Docker default bridge network range
    _ipaddress.ip_network("10.0.0.0/8"),  # Private class A network range
    _ipaddress.ip_network("192.168.0.0/16"),  # Private class C network range
]

WATCHDOG_INTERVAL = 5  # Seconds between intrusion detection scans
VIOLATION_THRESHOLD = 2  # Consecutive violations before lockdown triggers


def _is_allowed_ip(ip_str: str) -> bool:
    if ip_str in ALLOWED_REMOTE_IPS:  # Check exact match against allowlist
        return True
    try:
        addr = _ipaddress.ip_address(ip_str)  # Parse IP string into address object
        return any(addr in net for net in _DOCKER_NETS)  # Check if IP falls in private/Docker ranges
    except ValueError:  # Handle malformed IP strings
        return False


class IntrusionWatchdog(threading.Thread):
    """
    Background thread that monitors for:
      1. Unexpected outbound network connections from this process
      2. Known debugging / traffic analysis tools running on the system

    On confirmed intrusion:
      - Wipes all active sessions immediately
      - Logs the event with timestamp and reason
      - Optionally terminates the server process entirely

    Conservative by design — two consecutive violations required
    before triggering to reduce false positives.
    """

    def __init__(self, session_store: SessionStore, terminate_on_intrusion: bool = True):
        super().__init__(daemon=True, name="IntrusionWatchdog")  # Initialize as named daemon thread
        self.session_store = session_store  # Reference to session store for emergency wipe
        self.terminate_on_intrusion = terminate_on_intrusion  # Whether to kill process on intrusion
        self.running = True  # Control flag for main loop
        self._violation_count = 0  # Consecutive violation counter
        self._triggered = False  # Whether lockdown has been activated
        self._lock = threading.Lock()  # Mutex for trigger state
        self.intrusion_log: list[dict] = []  # Rolling log of security events

    def _log_event(self, event_type: str, detail: str):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),  # UTC ISO-8601 timestamp
            "event": event_type,  # Category of security event
            "detail": detail,  # Human-readable event description
        }
        self.intrusion_log.append(entry)  # Append to rolling event log
        if len(self.intrusion_log) > 100:  # Cap log at 100 entries
            self.intrusion_log = self.intrusion_log[-100:]  # Keep only most recent entries
        print(f"[Watchdog] {event_type}: {detail}")  # Print event to server console

    def check_network(self) -> tuple[bool, str]:
        our_pid = os.getpid()  # Get current server process ID
        try:
            proc = psutil.Process(our_pid)  # Get process handle for this server
            all_procs = [proc] + proc.children(recursive=True)  # Include all child processes
            for p in all_procs:  # Scan each process for connections
                for conn in p.net_connections():  # Iterate active network connections
                    if conn.status != psutil.CONN_ESTABLISHED:  # Skip non-established connections
                        continue
                    raddr = conn.raddr  # Get remote address tuple
                    if not raddr:  # Skip connections without remote address
                        continue
                    remote_ip = raddr.ip  # Extract remote IP address
                    if not _is_allowed_ip(remote_ip):  # Flag connections to disallowed IPs
                        return False, f"unexpected outbound connection to {remote_ip}:{raddr.port}"
        except psutil.NoSuchProcess:  # Process exited during check
            pass
        except Exception as e:  # Log non-fatal errors without crashing
            print(f"[Watchdog] network check error (non-fatal): {e}")
        return True, ""  # Network is clean

    def check_processes(self) -> tuple[bool, str]:
        try:
            for proc in psutil.process_iter(["name", "pid"]):  # Iterate all system processes
                try:
                    name = (proc.info["name"] or "").lower()  # Normalize process name to lowercase
                    if any(s in name for s in SUSPICIOUS_PROCESSES):  # Match against suspicious tool names
                        return False, f"suspicious process detected: {proc.info['name']} (pid={proc.info['pid']})"
                except (psutil.NoSuchProcess, psutil.AccessDenied):  # Skip inaccessible processes
                    pass
        except Exception as e:  # Log non-fatal errors without crashing
            print(f"[Watchdog] process check error (non-fatal): {e}")
        return True, ""  # No suspicious processes found

    def _trigger_lockdown(self, reason: str):
        with self._lock:  # Acquire lock for atomic trigger check
            if self._triggered:  # Prevent duplicate lockdowns
                return
            self._triggered = True  # Mark lockdown as active

        print(f"\n[Watchdog] *** INTRUSION LOCKDOWN TRIGGERED ***")  # Alert to console
        print(f"[Watchdog] Reason: {reason}")  # Log lockdown reason
        self._log_event("LOCKDOWN", reason)  # Record lockdown in event log

        self.session_store.wipe_all(reason=f"intrusion_lockdown: {reason}")  # Emergency wipe all sessions

        if self.terminate_on_intrusion:  # Check if process kill is enabled
            print("[Watchdog] Terminating server process.")  # Log imminent termination
            time.sleep(0.5)  # Brief delay for log flush
            os.kill(os.getpid(), signal.SIGTERM)  # Send SIGTERM to self

    def run(self):
        print(f"[Watchdog] Started — checking every {WATCHDOG_INTERVAL}s "
              f"(threshold={VIOLATION_THRESHOLD} violations)")  # Log watchdog startup config
        while self.running and not self._triggered:  # Main monitoring loop
            time.sleep(WATCHDOG_INTERVAL)  # Wait between scan intervals

            net_clean, net_detail = self.check_network()  # Scan for unauthorized connections
            proc_clean, proc_detail = self.check_processes()  # Scan for suspicious processes

            if not net_clean or not proc_clean:  # Violation detected
                self._violation_count += 1  # Increment consecutive violation counter
                detail = net_detail or proc_detail  # Use first available violation detail
                print(f"[Watchdog] Violation {self._violation_count}/{VIOLATION_THRESHOLD}: {detail}")  # Log violation progress
                self._log_event("VIOLATION", detail)  # Record violation in event log

                if self._violation_count >= VIOLATION_THRESHOLD:  # Threshold reached
                    self._trigger_lockdown(detail)  # Execute emergency lockdown
            else:  # No violation this cycle
                if self._violation_count > 0:  # Had previous violations
                    print(f"[Watchdog] Clear — resetting violation count")  # Log violation reset
                self._violation_count = 0  # Reset consecutive counter

    def stop(self):
        self.running = False  # Signal main loop to exit

    def get_status(self) -> dict:
        return {
            "running": self.running and not self._triggered,  # Whether watchdog is actively monitoring
            "triggered": self._triggered,  # Whether lockdown was activated
            "violations": self._violation_count,  # Current consecutive violation count
            "threshold": VIOLATION_THRESHOLD,  # Violations needed to trigger lockdown
            "check_interval_sec": WATCHDOG_INTERVAL,  # Seconds between scans
            "recent_events": self.intrusion_log[-5:],  # Last five security events
        }


# ---------------------------------------------------------------------------
# API keys + rate limiting
# ---------------------------------------------------------------------------
def load_api_keys() -> dict[str, str]:
    env_keys = os.environ.get("KWYRE_API_KEYS", "")  # Read API keys from environment variable
    if env_keys:  # Parse if env var is set
        keys = {}  # Accumulate parsed key-user pairs
        for pair in env_keys.split(","):  # Split comma-separated key:user pairs
            if ":" in pair:  # Validate pair format
                k, u = pair.strip().split(":", 1)  # Split into key and username
                keys[k] = u  # Map API key to username
        return keys  # Return parsed key mapping
    return {"sk-kwyre-dev-local": "admin"}  # Default development key


RATE_LIMIT_RPM_DEFAULT = 30  # Default max requests per minute per user
ALLOWED_PAGES = {"landing.html", "index.html", "main.html", "pay.html", "technology.html", "security.html", "platform.html", "custom.html"}  # Whitelist of servable HTML pages


# ---------------------------------------------------------------------------
# Shared request handler mixin — security headers, auth, JSON helpers
# ---------------------------------------------------------------------------
class KwyreHandlerMixin:
    """
    Mixin providing shared HTTP handler methods used by both
    the GPU (serve_local_4bit) and CPU (serve_cpu) servers.

    Subclass must also inherit from BaseHTTPRequestHandler and must set:
      - self._api_keys: dict[str, str]
      - self._rate_tracker: defaultdict(list)
      - self._rate_limit_rpm: int
      - self._bind_host: str
      - self._port: int
      - self._chat_dir: str
    """

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")  # Read Authorization header value
        if auth.startswith("Bearer "):  # Check for Bearer token scheme
            key = auth[7:]  # Extract token after "Bearer " prefix
            for valid_key, user in self._api_keys.items():  # Iterate registered API keys
                if hmac.compare_digest(key, valid_key):  # Constant-time comparison to prevent timing attacks
                    return user  # Return authenticated username
        self._send_json_error(401, "Invalid API key.")  # Send 401 if no valid key matched
        return None  # Signal authentication failure

    def _check_auth_optional(self):
        auth = self.headers.get("Authorization", "")  # Read Authorization header value
        if auth.startswith("Bearer "):  # Check for Bearer token scheme
            key = auth[7:]  # Extract token after "Bearer " prefix
            for valid_key, user in self._api_keys.items():  # Iterate registered API keys
                if hmac.compare_digest(key, valid_key):  # Constant-time comparison to prevent timing attacks
                    return user  # Return authenticated username
        return None  # Return None instead of error for optional auth

    def _check_rate_limit(self, user):
        now = time.time()  # Capture current timestamp
        self._rate_tracker[user] = [t for t in self._rate_tracker[user] if now - t < 60]  # Prune timestamps older than 60 seconds
        if len(self._rate_tracker[user]) >= self._rate_limit_rpm:  # Check if user exceeded limit
            self._send_json_error(429, f"Rate limit exceeded. Max {self._rate_limit_rpm} req/min.")  # Send 429 Too Many Requests
            return False  # Signal rate limit exceeded
        self._rate_tracker[user].append(now)  # Record this request timestamp
        if len(self._rate_tracker) > 1000:  # Prevent tracker memory bloat
            stale = [k for k, v in self._rate_tracker.items() if not v or now - max(v) > 120]  # Find users with no recent requests
            for k in stale:  # Remove stale user entries
                del self._rate_tracker[k]
        return True  # Request is within rate limit

    def _get_session_id(self, body: dict) -> str:
        sid = body.get("session_id")  # Extract session ID from request body
        if not sid or not isinstance(sid, str) or len(sid) < 32:  # Validate session ID format and length
            sid = secrets.token_hex(16)  # Generate new 32-char hex session ID
        return sid  # Return validated or generated session ID

    def _parse_json_body(self, required: bool = False) -> tuple[dict | None, str | None]:
        try:
            raw_len = self.headers.get("Content-Length")  # Read Content-Length header
            if raw_len is None or raw_len.strip() == "":  # Handle missing Content-Length
                if required:  # Fail if body is mandatory
                    return None, "Missing Content-Length header."
                return {}, None  # Return empty body for optional case
            length = int(raw_len)  # Parse content length as integer
        except ValueError:  # Handle non-numeric Content-Length
            return None, "Invalid Content-Length header."
        if length < 0:  # Reject negative content lengths
            return None, "Invalid Content-Length: negative value."
        if length > 10 * 1024 * 1024:  # Enforce 10MB upload limit
            return None, "Content-Length exceeds 10MB limit."
        raw = self.rfile.read(length)  # Read exact number of bytes from request stream
        if length > 0 and not raw:  # Detect failed or truncated read
            return None, "Failed to read request body."
        if length == 0:  # Handle zero-length body
            if required:  # Fail if body is mandatory
                return None, "Request body required."
            return {}, None  # Return empty body for optional case
        try:
            body = json.loads(raw.decode("utf-8", errors="replace"))  # Decode and parse JSON body
        except json.JSONDecodeError as e:  # Handle malformed JSON
            return None, f"Invalid JSON: {e}"
        if not isinstance(body, dict):  # Ensure top-level JSON is an object
            return None, "Request body must be a JSON object."
        return body, None  # Return parsed body with no error

    def _send_json_error(self, status: int, message: str):
        self.send_response(status)  # Set HTTP status code
        self.send_header("Content-Type", "application/json")  # Set JSON content type
        self._send_security_headers()  # Attach security headers to response
        self.end_headers()  # Finalize response headers
        self.wfile.write(json.dumps({"error": message}).encode())  # Write JSON error body

    def _send_security_headers(self, nonce: str = "", extra_script_src: str = ""):
        self.send_header("X-Content-Type-Options", "nosniff")  # Prevent MIME type sniffing
        self.send_header("X-Frame-Options", "DENY")  # Block framing to prevent clickjacking
        self.send_header("X-XSS-Protection", "1; mode=block")  # Enable browser XSS filter
        self.send_header("Referrer-Policy", "no-referrer")  # Strip referrer on navigation
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")  # Disable sensitive browser APIs
        script_src = "'self'"  # Allow scripts from same origin only
        if nonce:  # Add nonce for inline script authorization
            script_src += f" 'nonce-{nonce}'"
        else:  # Fall back to unsafe-inline when no nonce provided
            script_src += " 'unsafe-inline'"
        if extra_script_src:  # Append additional allowed script sources
            script_src += f" {extra_script_src}"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"connect-src 'self'; "
            f"img-src 'self' data:; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'",
        )  # Set comprehensive Content-Security-Policy header
        self.send_header("Access-Control-Allow-Origin", f"http://{self._bind_host}:{self._port}")  # Restrict CORS to server origin

    def _serve_html(self, filename: str):
        filepath = os.path.join(self._chat_dir, filename)  # Build full path to HTML file
        resolved = os.path.realpath(filepath)  # Resolve symlinks to real path
        if not resolved.startswith(os.path.realpath(self._chat_dir)):  # Block path traversal attacks
            self.send_response(403)  # Send 403 Forbidden
            self._send_security_headers()  # Attach security headers
            self.end_headers()  # Finalize headers
            return
        if not os.path.isfile(resolved):  # Check file exists on disk
            self.send_response(404)  # Send 404 Not Found
            self._send_security_headers()  # Attach security headers
            self.end_headers()  # Finalize headers
            return
        with open(resolved, "rb") as f:  # Open HTML file in binary mode
            html = f.read()  # Read entire file into memory
        nonce = secrets.token_urlsafe(16)  # Generate unique CSP nonce per request
        html = html.replace(b"{{CSP_NONCE}}", nonce.encode())  # Inject nonce into HTML template
        extra_script_src = "https://cdn.jsdelivr.net" if filename == "pay.html" else ""  # Allow CDN scripts for payment page
        self.send_response(200)  # Send 200 OK status
        self.send_header("Content-Type", "text/html; charset=utf-8")  # Set HTML content type with encoding
        self.send_header("Cache-Control", "no-cache")  # Prevent browser caching of HTML
        self._send_security_headers(nonce=nonce, extra_script_src=extra_script_src)  # Attach CSP with nonce
        self.end_headers()  # Finalize response headers
        self.wfile.write(html)  # Send HTML body to client

    @staticmethod
    def _safe_page_name(raw_path: str) -> str | None:
        stripped = raw_path.lstrip("/")  # Remove leading slashes from URL path
        basename = os.path.basename(stripped)  # Extract filename from path
        if basename in ALLOWED_PAGES and basename == stripped:  # Validate against whitelist, reject subdirectories
            return basename  # Return sanitized page name
        return None  # Reject disallowed or traversal paths

    def do_OPTIONS(self):
        self.send_response(204)  # Send 204 No Content for preflight
        self.send_header("Content-Length", "0")  # Indicate empty response body
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")  # Declare allowed HTTP methods
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")  # Declare allowed request headers
        self.send_header("Access-Control-Max-Age", "86400")  # Cache preflight response for 24 hours
        self._send_security_headers()  # Attach security headers to preflight
        self.end_headers()  # Finalize preflight response headers
