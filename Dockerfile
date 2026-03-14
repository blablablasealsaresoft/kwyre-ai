# Stage 1: Install Python dependencies
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip gcc g++ \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/kwyre-venv
ENV PATH="/opt/kwyre-venv/bin:$PATH"

COPY requirements-inference.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y triton 2>/dev/null; true \
    && find /opt/kwyre-venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true \
    && find /opt/kwyre-venv -name "*.pyc" -delete 2>/dev/null; true \
    && rm -rf /opt/kwyre-venv/lib/python3.11/site-packages/torch/test 2>/dev/null; true

# Stage 2: Runtime image
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="Kwyre AI Inference Server" \
      org.opencontainers.image.version="1.6.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/kwyre-venv /opt/kwyre-venv
ENV PATH="/opt/kwyre-venv/bin:$PATH"

RUN groupadd -r kwyre && useradd -r -g kwyre -d /workspace -s /usr/sbin/nologin kwyre

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace

COPY server/              ./server/
COPY model/spike_serve.py ./model/spike_serve.py
COPY model/spike_qat.py   ./model/spike_qat.py
COPY security/            ./security/
COPY chat/                ./chat/
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh
RUN python security/verify_deps.py generate || true

RUN chown -R kwyre:kwyre /workspace
USER kwyre

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "server/serve_local_4bit.py"]
