# Server

Inference server backends for all Kwyre products.

- `serve_local_4bit.py` — GPU backend (NF4/AWQ, speculative decoding, SpikeServe, KV cache, RAG, streaming)
- `serve_vllm.py` — vLLM backend (continuous batching, PagedAttention)
- `serve_cpu.py` — Kwyre Air CPU backend (llama.cpp / GGUF)
- `serve_mlx.py` — Apple Silicon backend (MLX / Metal)
- `security_core.py` — Shared 6-layer security infrastructure (all backends import this)
- `rag.py` — RAG document ingestion (FAISS + sentence-transformers)
- `audit.py` — Per-user audit logging + SIEM export (JSONL, CEF)
- `users.py` — Multi-user management with Fernet-encrypted storage
- `tools.py` — External API tool router (opt-in, default off)
