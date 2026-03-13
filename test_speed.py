import urllib.request, json, time

URL = "http://127.0.0.1:8000/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer sk-kwyre-dev-local",
    "Content-Type": "application/json",
}

def bench(prompt, max_tokens=100, label=""):
    payload = json.dumps({
        "model": "kwyre-4b-spikeserve",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(URL, data=payload, headers=HEADERS)
    t = time.time()
    resp = urllib.request.urlopen(req, timeout=300)
    elapsed = time.time() - t
    d = json.loads(resp.read())
    toks = d["usage"]["completion_tokens"]
    speed = toks / elapsed if elapsed > 0 else 0
    print(f"[{label}] {toks} tokens in {elapsed:.1f}s = {speed:.1f} tok/s")
    content = d['choices'][0]['message']['content'][:200]
    print(f"  Response: {content.encode('ascii', 'replace').decode()}")
    return speed

print("=== Kwyre 4B + Speculative Decoding Benchmark ===\n")
print("Warmup run...")
bench("Say hello.", max_tokens=20, label="warmup")
print()

speeds = []
for i, (prompt, tok) in enumerate([
    ("What is 2+2? Answer in one sentence.", 30),
    ("Explain quantum computing in 3 sentences.", 100),
    ("Write a Python function to reverse a string.", 80),
], 1):
    s = bench(prompt, max_tokens=tok, label=f"test{i}")
    speeds.append(s)
    print()

avg = sum(speeds) / len(speeds)
print(f"=== Average speed: {avg:.1f} tok/s ===")
