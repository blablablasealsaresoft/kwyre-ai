FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="Kwyre AI Inference Server" \
      org.opencontainers.image.version="0.1.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip curl gcc \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace

COPY requirements-inference.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y triton 2>/dev/null; true \
    && find /usr/local/lib -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true \
    && find /usr/local/lib -name "*.pyc" -delete 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/torch/test 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/torch/_inductor 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/torch/_dynamo 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/torch/_export 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/torch/_functorch 2>/dev/null; true \
    && rm -rf /usr/local/lib/python3.11/dist-packages/nvidia/nccl 2>/dev/null; true

COPY server/              ./server/
COPY model/spike_serve.py ./model/spike_serve.py
COPY model/spike_qat.py   ./model/spike_qat.py
COPY security/            ./security/
COPY chat/                ./chat/
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "server/serve_local_4bit.py"]
