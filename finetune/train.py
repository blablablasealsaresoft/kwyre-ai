#!/usr/bin/env python3
"""
Kwyre AI — Fine-tune Pipeline Bridge
Connects the finetune/ data preparation to training/scripts/ training.

Usage:
    python finetune/train.py --domain legal_compliance --data examples.jsonl
    python finetune/train.py --domain legal_compliance --data raw_docs/ --prepare
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_SCRIPTS = PROJECT_ROOT / "training" / "scripts"
FINETUNE_DIR = Path(__file__).resolve().parent
KWYRE_HOME = Path(os.path.expanduser("~/.kwyre"))
TRACES_DIR = KWYRE_HOME / "training-data" / "kwyre-traces"

VALID_DOMAINS = [
    "legal_compliance", "insurance_actuarial", "healthcare_lifesciences",
    "defense_intelligence", "financial_trading", "blockchain_crypto",
    "sports_analytics", "relationship_matching",
]

# Map bridge domains to prepare_data.py domains (legal, financial, forensic)
DOMAIN_TO_PREPARE = {
    "legal_compliance": "legal",
    "insurance_actuarial": "financial",
    "healthcare_lifesciences": "forensic",
    "defense_intelligence": "forensic",
    "financial_trading": "financial",
    "blockchain_crypto": "financial",
    "sports_analytics": "financial",
    "relationship_matching": "forensic",
}


def prepare_data(raw_path: str, domain: str, output_path: str) -> str:
    """Run finetune/prepare_data.py to convert raw data to training format."""
    prepare_domain = DOMAIN_TO_PREPARE.get(domain, "legal")
    cmd = [
        sys.executable, str(FINETUNE_DIR / "prepare_data.py"),
        raw_path,
        "-o", output_path,
        "--domains", prepare_domain,
    ]
    print(f"[Prepare] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    return output_path


def validate_data(data_path: str) -> bool:
    """Run finetune/validate_data.py to check training data quality."""
    cmd = [
        sys.executable, str(FINETUNE_DIR / "validate_data.py"),
        data_path,
    ]
    print(f"[Validate] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[Validate] FAILED: {result.stderr}", file=sys.stderr)
        return False
    return True


def _conversations_to_messages(record: dict) -> dict | None:
    """Convert finetune 'conversations' format to train_distillation 'messages' format."""
    conv = record.get("conversations")
    if not isinstance(conv, list) or len(conv) < 2:
        return None
    messages = []
    for turn in conv:
        role = "user" if turn.get("from") == "human" else "assistant"
        val = turn.get("value", "")
        if isinstance(val, str):
            messages.append({"role": role, "content": val})
        else:
            messages.append({"role": role, "content": str(val)})
    return {"messages": messages}


def ensure_trace_file(domain: str, data_path: str) -> str:
    """
    Ensure training data is at the path train_distillation expects.
    Converts 'conversations' format to 'messages' if needed.
    Returns the path train_distillation will load from.
    """
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    trace_file = str(TRACES_DIR / f"{domain}.jsonl")

    with open(data_path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    first = json.loads(first_line) if first_line.strip() else {}

    if "messages" in first:
        shutil.copy2(data_path, trace_file)
        return trace_file

    with open(data_path, "r", encoding="utf-8") as fin:
        with open(trace_file, "w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                converted = _conversations_to_messages(rec)
                if converted:
                    fout.write(json.dumps(converted, ensure_ascii=False) + "\n")
    return trace_file


def run_distillation(domain: str, data_path: str, base_model: str | None = None):
    """Run training/scripts/train_distillation.py."""
    ensure_trace_file(domain, data_path)
    env = os.environ.copy()
    env["KWYRE_DOMAIN"] = domain
    if base_model:
        env["KWYRE_BASE_MODEL"] = base_model

    cmd = [sys.executable, str(TRAINING_SCRIPTS / "train_distillation.py")]
    print(f"[Train] {' '.join(cmd)}")
    subprocess.run(cmd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description="Kwyre fine-tune pipeline bridge")
    parser.add_argument("--domain", required=True, choices=VALID_DOMAINS,
                        help="Target domain for fine-tuning")
    parser.add_argument("--data", required=True,
                        help="Path to JSONL training data or raw document directory")
    parser.add_argument("--prepare", action="store_true",
                        help="Run data preparation first (for raw documents)")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip data validation step")
    parser.add_argument("--base-model", default=None,
                        help="Override base model ID")
    parser.add_argument("--output", default=None,
                        help="Output path for prepared data (with --prepare)")
    args = parser.parse_args()

    data_path = args.data

    if args.prepare:
        output = args.output or str(
            KWYRE_HOME / "training-data" / f"{args.domain}-prepared.jsonl"
        )
        data_path = prepare_data(args.data, args.domain, output)

    if not args.skip_validation:
        if not validate_data(data_path):
            print("Data validation failed. Fix issues or use --skip-validation.", file=sys.stderr)
            sys.exit(1)

    run_distillation(args.domain, data_path, args.base_model)
    print(f"\nFine-tuning complete for domain '{args.domain}'.")
    print("Check ~/.kwyre/lora-adapters/ for the trained adapter.")


if __name__ == "__main__":
    main()
