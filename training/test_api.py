#!/usr/bin/env python3
"""Quick test: is the Anthropic API key working right now?"""
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

print("Testing API key...")
try:
    r = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=50,
        messages=[{"role": "user", "content": "Say hello in exactly 5 words."}]
    )
    print(f"API OK: {r.content[0].text}")
    print(f"Usage: {r.usage.input_tokens} in / {r.usage.output_tokens} out")
except anthropic.BadRequestError as e:
    print(f"BAD REQUEST: {e}")
except anthropic.AuthenticationError as e:
    print(f"AUTH ERROR: {e}")
except anthropic.RateLimitError as e:
    print(f"RATE LIMITED: {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
