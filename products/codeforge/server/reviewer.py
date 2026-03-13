from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ReviewIssue:
    severity: Severity
    category: str
    message: str
    line: int | None = None
    file: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
        }
        if self.line is not None:
            out["line"] = self.line
        if self.file is not None:
            out["file"] = self.file
        if self.suggestion is not None:
            out["suggestion"] = self.suggestion
        return out


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"""(?:api[_-]?key|apikey)\s*[:=]\s*["'][A-Za-z0-9_\-]{16,}["']""", re.IGNORECASE), "API key"),
    (re.compile(r"""(?:secret|token|password|passwd|pwd)\s*[:=]\s*["'][^"']{8,}["']""", re.IGNORECASE), "secret/password"),
    (re.compile(r"""(?:aws_access_key_id|aws_secret_access_key)\s*[:=]\s*["'][A-Za-z0-9/+=]{16,}["']""", re.IGNORECASE), "AWS credential"),
    (re.compile(r"""-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"""), "private key"),
    (re.compile(r"""ghp_[A-Za-z0-9]{36,}"""), "GitHub personal access token"),
    (re.compile(r"""sk-[A-Za-z0-9]{32,}"""), "OpenAI API key"),
    (re.compile(r"""Bearer\s+[A-Za-z0-9\-._~+/]+=*""", re.IGNORECASE), "bearer token"),
]

SQL_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"""f["'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s.*\{.*\}""", re.IGNORECASE),
    re.compile(r"""["'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s.*["']\s*%\s""", re.IGNORECASE),
    re.compile(r"""["'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s.*["']\s*\+\s""", re.IGNORECASE),
    re.compile(r"""\.format\(.*\).*(?:SELECT|INSERT|UPDATE|DELETE|DROP)""", re.IGNORECASE),
    re.compile(r"""(?:execute|query)\s*\(\s*f["']""", re.IGNORECASE),
]

UNUSED_IMPORT_PATTERN = re.compile(r"^[+](?:import\s+(\w+)|from\s+\S+\s+import\s+(.+))$", re.MULTILINE)

BARE_EXCEPT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\+\s*except\s*:", re.MULTILINE), "Bare except clause catches all exceptions including KeyboardInterrupt"),
    (re.compile(r"^\+\s*except\s+\w+.*:\s*$", re.MULTILINE), None),  # acceptable — just for context
    (re.compile(r"^\+\s*catch\s*\(\s*\)\s*\{?\s*$", re.MULTILINE), "Empty catch block swallows errors silently"),
    (re.compile(r"^\+\s*catch\s*\(.*\)\s*\{\s*\}", re.MULTILINE), "Empty catch block swallows errors silently"),
    (re.compile(r"^\+\s*rescue\s*$", re.MULTILINE), "Bare rescue catches all exceptions"),
]

TODO_PATTERN = re.compile(r"[+].*\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def _parse_diff_files(diff_text: str) -> list[tuple[str | None, str]]:
    """Split a unified diff into (filename, file_diff) pairs."""
    parts: list[tuple[str | None, str]] = []
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current_lines:
                parts.append((current_file, "".join(current_lines)))
            current_lines = [line]
            current_file = None
        elif line.startswith("+++ b/"):
            current_file = line[6:].strip()
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines:
        parts.append((current_file, "".join(current_lines)))
    return parts


def _added_lines(diff_text: str) -> list[tuple[int, str]]:
    """Extract added lines with approximate line numbers."""
    results: list[tuple[int, str]] = []
    current_line = 0
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            current_line = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            results.append((current_line, line))
            current_line += 1
        elif not line.startswith("-"):
            current_line += 1
    return results


class CodeReviewer:
    def analyze_diff(self, diff_text: str) -> dict:
        issues: list[ReviewIssue] = []
        file_parts = _parse_diff_files(diff_text)

        for fname, fdiff in file_parts:
            added = _added_lines(fdiff)
            issues.extend(self._check_secrets(added, fname))
            issues.extend(self._check_sql_injection(added, fname))
            issues.extend(self._check_error_handling(added, fname))
            issues.extend(self._check_todos(added, fname))
            issues.extend(self._check_complexity(added, fname))
            if fname and fname.endswith(".py"):
                issues.extend(self._check_unused_imports(fdiff, fname))
            issues.extend(self._check_file_size(fdiff, fname))

        summary = {"high": 0, "medium": 0, "low": 0, "info": 0}
        for iss in issues:
            summary[iss.severity.value] += 1

        return {
            "issues": [i.to_dict() for i in issues],
            "summary": summary,
            "total": len(issues),
        }

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_secrets(self, added: list[tuple[int, str]], fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for line_no, line in added:
            for pat, label in SECRET_PATTERNS:
                if pat.search(line):
                    issues.append(ReviewIssue(
                        severity=Severity.HIGH,
                        category="security",
                        message=f"Possible hardcoded {label} detected",
                        line=line_no,
                        file=fname,
                        suggestion="Move to environment variable or secrets manager",
                    ))
                    break  # one issue per line
        return issues

    def _check_sql_injection(self, added: list[tuple[int, str]], fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for line_no, line in added:
            for pat in SQL_INJECTION_PATTERNS:
                if pat.search(line):
                    issues.append(ReviewIssue(
                        severity=Severity.HIGH,
                        category="security",
                        message="Possible SQL injection — string interpolation in query",
                        line=line_no,
                        file=fname,
                        suggestion="Use parameterized queries instead of string formatting",
                    ))
                    break
        return issues

    def _check_error_handling(self, added: list[tuple[int, str]], fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for line_no, line in added:
            for pat, msg in BARE_EXCEPT_PATTERNS:
                if msg and pat.search(line):
                    issues.append(ReviewIssue(
                        severity=Severity.MEDIUM,
                        category="error_handling",
                        message=msg,
                        line=line_no,
                        file=fname,
                        suggestion="Catch specific exception types and handle them appropriately",
                    ))
                    break
        return issues

    def _check_todos(self, added: list[tuple[int, str]], fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for line_no, line in added:
            m = TODO_PATTERN.search(line)
            if m:
                issues.append(ReviewIssue(
                    severity=Severity.INFO,
                    category="maintainability",
                    message=f"{m.group(1).upper()} comment found",
                    line=line_no,
                    file=fname,
                    suggestion="Track in issue tracker instead of code comments",
                ))
        return issues

    def _check_complexity(self, added: list[tuple[int, str]], fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        indent_chars = {" ", "\t"}
        max_depth_seen = 0
        deepest_line = 0

        for line_no, line in added:
            stripped = line.lstrip("+")
            indent = 0
            for ch in stripped:
                if ch == " ":
                    indent += 1
                elif ch == "\t":
                    indent += 4
                else:
                    break
            depth = indent // 4
            if depth > max_depth_seen:
                max_depth_seen = depth
                deepest_line = line_no

        if max_depth_seen > 4:
            issues.append(ReviewIssue(
                severity=Severity.MEDIUM,
                category="complexity",
                message=f"Nesting depth of {max_depth_seen} exceeds recommended maximum of 4",
                line=deepest_line,
                file=fname,
                suggestion="Extract inner logic into separate functions to reduce nesting",
            ))
        return issues

    def _check_unused_imports(self, fdiff: str, fname: str | None) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        imports: list[tuple[int, str]] = []
        added = _added_lines(fdiff)
        added_code = "\n".join(line for _, line in added)

        for line_no, line in added:
            m = re.match(r"^\+\s*(?:import\s+(\w+)|from\s+\S+\s+import\s+(.+))$", line)
            if m:
                names_str = m.group(1) or m.group(2)
                for name in re.split(r"\s*,\s*", names_str):
                    name = name.strip().split(" as ")[-1].strip()
                    if name and name != "*":
                        imports.append((line_no, name))

        for line_no, name in imports:
            occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", added_code))
            if occurrences <= 1:  # only the import itself
                issues.append(ReviewIssue(
                    severity=Severity.LOW,
                    category="maintainability",
                    message=f"Import '{name}' may be unused",
                    line=line_no,
                    file=fname,
                    suggestion="Remove unused imports",
                ))
        return issues

    def _check_file_size(self, fdiff: str, fname: str | None) -> list[ReviewIssue]:
        added_count = sum(1 for line in fdiff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        if added_count > 500:
            return [ReviewIssue(
                severity=Severity.LOW,
                category="maintainability",
                message=f"Diff adds {added_count} lines — consider splitting into smaller changes",
                file=fname,
                suggestion="Break large changes into smaller, focused commits",
            )]
        return []
