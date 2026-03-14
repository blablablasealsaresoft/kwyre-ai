#!/usr/bin/env python3
"""Test a single trace generation to debug the pipeline."""
import os
import time
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
print("Generating one test trace...")
t0 = time.time()
r = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    temperature=0.6,
    system="You are an expert blockchain forensic analyst.",
    messages=[{"role": "user", "content": "Explain how to trace cryptocurrency money laundering.\n\nIMPORTANT: Show your complete reasoning process inside <think>...</think> tags FIRST, then provide your final answer AFTER the closing </think> tag."}],
)
elapsed = time.time() - t0
text = r.content[0].text
print(f"Got response in {elapsed:.1f}s")
print(f"Tokens: {r.usage.input_tokens} in, {r.usage.output_tokens} out")
print(f"Length: {len(text)} chars")
print(f"Has <think>: {'<think>' in text}")
print(f"First 200 chars: {text[:200]}")
print("SUCCESS")
