#!/usr/bin/env python3
"""Quick test: verify Claude API key works."""
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
print("Testing Claude API...")
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=256,
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(f"Response: {response.content[0].text}")
print(f"Model: {response.model}")
print(f"Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
print("Claude API working!")
