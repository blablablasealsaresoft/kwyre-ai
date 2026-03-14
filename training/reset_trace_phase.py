#!/usr/bin/env python3
"""Reset the trace generation phase in batch-state.json.
Keeps expanded prompts (Phase 1) but forces Phase 2 to re-run."""

import json
import os

state_file = os.path.expanduser("~/.kwyre/training-data/batch-state.json")

with open(state_file) as f:
    state = json.load(f)

print(f"expansion_done: {state.get('expansion_done')}")
print(f"trace_done (before): {state.get('trace_done')}")
print(f"trace_batch_id (before): {state.get('trace_batch_id', 'none')}")

domains = state.get("expanded_prompts", {})
print(f"expanded_prompts: {len(domains)} domains")
for d, prompts in domains.items():
    print(f"  {d}: {len(prompts)} prompts")

state["trace_done"] = False
state.pop("trace_batch_id", None)

with open(state_file, "w") as f:
    json.dump(state, f, indent=2)

print("\nRESET COMPLETE:")
print("  trace_done = False")
print("  trace_batch_id removed")
print("  Phase 1 prompts preserved (will skip expansion)")
print("\nRe-run: python3 training/scripts/generate_traces_batch.py")
