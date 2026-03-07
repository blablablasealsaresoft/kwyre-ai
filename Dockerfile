# Kwyre AI inference server
# Base: nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 (verified on Docker Hub)
# NOTE: Model weights are mounted at runtime via volume — never baked into image.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-distutils curl \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
# Install torch for CUDA 12.1 before other deps (PyPI default is CPU)
RUN python -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY model/spike_serve.py ./model/spike_serve.py
COPY security/verify_deps.py ./security/verify_deps.py
COPY chat/chat.html ./chat/chat.html

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["python", "server/serve_local_4bit.py"]
