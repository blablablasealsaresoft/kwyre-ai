# Kwyre AI inference server
# Model weights are mounted at runtime via volume — never baked into image.
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY model/spike_serve.py ./model/spike_serve.py
COPY security/verify_deps.py ./security/verify_deps.py
COPY chat/chat.html ./chat/chat.html

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["python", "server/serve_local_4bit.py"]
