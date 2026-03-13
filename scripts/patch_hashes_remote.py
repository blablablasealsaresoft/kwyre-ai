import sys

path = "/root/kwyre-ai/server/serve_local_4bit.py"
with open(path) as f:
    c = f.read()

old_hashes = {
    "ddc63e1c717afa86c865bb5e01313d89d72bb53b97ad4a8a03ba8510c0621670": "8ba006f74fecfaaeb392872a60f4a480e7ec9860153d2e1b769ec81f9a147f8a",
    "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8": "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
}

# Only replace the 4B block's tokenizer.json hash (appears second)
old_tok = "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
new_tok = "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4"

for old, new in old_hashes.items():
    c = c.replace(old, new)

# The tokenizer hash appears in both 9B and 4B blocks — only replace the second occurrence
idx = c.find(old_tok)
if idx >= 0:
    idx2 = c.find(old_tok, idx + 1)
    if idx2 >= 0:
        c = c[:idx2] + new_tok + c[idx2 + len(old_tok):]
        print("Patched tokenizer.json hash (4B block)")

with open(path, "w") as f:
    f.write(c)

print("Done — WEIGHT_HASHES_4B updated for Qwen/Qwen3-4B")
