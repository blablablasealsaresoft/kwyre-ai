#!/usr/bin/env python3
"""
Data validation script for Kwyre fine-tuning JSONL.
Checks format, lengths, PII patterns, statistics. No ML dependencies.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# PII patterns (simplified; may have false positives)
PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "ssn": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


def find_pii(text: str) -> dict[str, list[str]]:
    """Return dict of PII type -> list of matched strings (redacted for reporting)."""
    found = {}
    for name, pat in PII_PATTERNS.items():
        matches = pat.findall(text)
        if matches:
            found[name] = list(set(matches))[:5]  # Limit to 5 examples
    return found


def validate_record(rec: dict, idx: int) -> list[str]:
    """Validate a single record. Returns list of error/warning strings."""
    issues = []
    if not isinstance(rec, dict):
        issues.append(f"[{idx}] Record is not a dict")
        return issues

    conv = rec.get("conversations")
    if not isinstance(conv, list):
        issues.append(f"[{idx}] Missing or invalid 'conversations'")
        return issues

    if len(conv) < 2:
        issues.append(f"[{idx}] Need at least 2 turns (human + gpt)")

    for i, turn in enumerate(conv):
        if not isinstance(turn, dict):
            issues.append(f"[{idx}] Turn {i} is not a dict")
            continue
        role = turn.get("from")
        value = turn.get("value", "")
        if role not in ("human", "gpt", "system"):
            issues.append(f"[{idx}] Turn {i} has invalid 'from': {role!r}")
        if not isinstance(value, str):
            issues.append(f"[{idx}] Turn {i} 'value' is not a string")
        elif len(value) == 0:
            issues.append(f"[{idx}] Turn {i} has empty value")
        elif len(value) > 100_000:
            issues.append(f"[{idx}] Turn {i} very long ({len(value)} chars)")

    return issues


def run_validation(path: Path) -> dict:
    """Run full validation. Returns stats dict."""
    stats = {
        "total": 0,
        "valid": 0,
        "errors": [],
        "warnings": [],
        "hashes": set(),
        "duplicates": 0,
        "domains": {},
        "difficulties": {},
        "total_chars": 0,
        "est_tokens": 0,
        "pii_warnings": [],
        "lengths": {"min_instruction": None, "max_instruction": None, "min_response": None, "max_response": None},
    }

    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            stats["total"] += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                stats["errors"].append(f"Line {idx + 1}: Invalid JSON - {e}")
                continue

            issues = validate_record(rec, idx)
            if issues:
                stats["errors"].extend(issues)
                continue
            stats["valid"] += 1

            conv = rec.get("conversations", [])
            key = json.dumps(conv, sort_keys=True)
            h = hashlib.sha256(key.encode()).hexdigest()
            if h in stats["hashes"]:
                stats["duplicates"] += 1
            stats["hashes"].add(h)

            domain = rec.get("domain", "unknown")
            stats["domains"][domain] = stats["domains"].get(domain, 0) + 1
            diff = rec.get("difficulty", "unknown")
            stats["difficulties"][diff] = stats["difficulties"].get(diff, 0) + 1

            for turn in conv:
                val = turn.get("value", "")
                stats["total_chars"] += len(val)
                stats["est_tokens"] += estimate_tokens(val)
                pii = find_pii(val)
                if pii:
                    stats["pii_warnings"].append({"line": idx + 1, "types": list(pii.keys())})
                if turn.get("from") == "human":
                    L = len(val)
                    if stats["lengths"]["min_instruction"] is None or L < stats["lengths"]["min_instruction"]:
                        stats["lengths"]["min_instruction"] = L
                    if stats["lengths"]["max_instruction"] is None or L > stats["lengths"]["max_instruction"]:
                        stats["lengths"]["max_instruction"] = L
                elif turn.get("from") == "gpt":
                    L = len(val)
                    if stats["lengths"]["min_response"] is None or L < stats["lengths"]["min_response"]:
                        stats["lengths"]["min_response"] = L
                    if stats["lengths"]["max_response"] is None or L > stats["lengths"]["max_response"]:
                        stats["lengths"]["max_response"] = L

    return stats


def main():
    ap = argparse.ArgumentParser(description="Validate fine-tuning JSONL data")
    ap.add_argument("input", type=Path, help="Input JSONL file")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any validation error")
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"Error: {args.input} is not a file")
        sys.exit(1)

    stats = run_validation(args.input)

    print("=" * 60)
    print("Validation Report")
    print("=" * 60)
    print(f"Total records:     {stats['total']}")
    print(f"Valid records:     {stats['valid']}")
    print(f"Errors:           {len(stats['errors'])}")
    print(f"Duplicates:       {stats['duplicates']}")
    print()
    print("Domain distribution:")
    for d, c in sorted(stats["domains"].items()):
        print(f"  {d}: {c}")
    print()
    print("Difficulty distribution:")
    for d, c in sorted(stats["difficulties"].items()):
        print(f"  {d}: {c}")
    print()
    print("Length stats (chars):")
    L = stats["lengths"]
    print(f"  Instruction: min={L['min_instruction']}, max={L['max_instruction']}")
    print(f"  Response:    min={L['min_response']}, max={L['max_response']}")
    print()
    print(f"Total chars:   {stats['total_chars']:,}")
    print(f"Est. tokens:  {stats['est_tokens']:,}")
    print()

    if stats["pii_warnings"]:
        print("PII WARNINGS (review before training):")
        for w in stats["pii_warnings"][:20]:
            print(f"  Line {w['line']}: {w['types']}")
        if len(stats["pii_warnings"]) > 20:
            print(f"  ... and {len(stats['pii_warnings']) - 20} more")
        print()

    if stats["errors"]:
        print("ERRORS:")
        for e in stats["errors"][:30]:
            print(f"  {e}")
        if len(stats["errors"]) > 30:
            print(f"  ... and {len(stats['errors']) - 30} more")
        print()

    if args.strict and (stats["errors"] or stats["duplicates"] > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
