import torch
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig

MODEL_PATH = "/workspace/models/Panyuqi/V1-7B-sft-s3-reasoning"
PORT = 8000

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH, padding_side="left", truncation_side="left", trust_remote_code=True
)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Loading model (GPU + CPU offload)...")
config = AutoConfig.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    config=config,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model.eval()
print(f"Model loaded. Device map: {model.hf_device_map}")
print(f"Server starting on http://localhost:{PORT}")


class ChatHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            messages = body.get("messages", [])
            max_tokens = body.get("max_tokens", 512)
            temperature = body.get("temperature", 0.7)
            top_p = body.get("top_p", 0.9)

            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = tokenizer([text], return_tensors="pt").to(model.device)

            with torch.no_grad():
                gen_ids = model.generate(
                    inputs.input_ids,
                    attention_mask=inputs.attention_mask,
                    max_new_tokens=max_tokens,
                    temperature=max(temperature, 0.01),
                    top_p=top_p,
                    do_sample=temperature > 0,
                    use_cache=True,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )

            new_ids = gen_ids[0][inputs.input_ids.shape[1] :]
            reply = tokenizer.decode(new_ids, skip_special_tokens=True)

            response = {
                "choices": [{"message": {"role": "assistant", "content": reply}}],
                "model": "spikingbrain-7b",
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ChatHandler)
    print(f"SpikingBrain-7B ready at http://localhost:{PORT}")
    print("  POST /v1/chat/completions  - chat with the model")
    print("  GET  /health               - health check")
    print("All inference runs 100% locally. No data leaves this machine.")
    server.serve_forever()
