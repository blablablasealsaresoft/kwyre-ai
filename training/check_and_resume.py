#!/usr/bin/env python3
"""Check batch status and resume trace generation if needed."""

import json
import os
import sys

state_file = os.path.expanduser("~/.kwyre/training-data/batch-state.json")
trace_dir = os.path.expanduser("~/.kwyre/training-data/kwyre-traces")

if not os.path.exists(state_file):
    print("No state file found. Run generate_traces_batch.py from scratch.")
    sys.exit(1)

with open(state_file) as f:
    state = json.load(f)

print(f"expansion_done: {state.get('expansion_done')}")
print(f"trace_done: {state.get('trace_done')}")
print(f"trace_batch_id: {state.get('trace_batch_id', 'none')}")

batch_id = state.get("trace_batch_id")
if not batch_id:
    print("No trace batch ID found. Need to re-submit.")
    sys.exit(0)

try:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    batch = client.messages.batches.retrieve(batch_id)
    counts = batch.request_counts
    total = counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired
    print(f"\nBatch {batch_id}:")
    print(f"  Status: {batch.processing_status}")
    print(f"  Total: {total}")
    print(f"  Succeeded: {counts.succeeded}")
    print(f"  Errored: {counts.errored}")
    print(f"  Processing: {counts.processing}")
    print(f"  Canceled: {counts.canceled}")
    print(f"  Expired: {counts.expired}")

    if batch.processing_status == "ended":
        print("\nBatch ENDED. Re-running generate_traces_batch.py will download results.")
    elif batch.processing_status == "in_progress":
        print("\nBatch still IN PROGRESS. Re-running generate_traces_batch.py will resume polling.")
    else:
        print(f"\nBatch status: {batch.processing_status}")
except Exception as e:
    print(f"Error checking batch: {e}")
