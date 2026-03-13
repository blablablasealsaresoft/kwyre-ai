#!/bin/bash
################################################################################
# KWYRE AI — GPU Training Environment Setup
# Run on a fresh Ubuntu 22.04 GPU instance (DigitalOcean H100 / Lambda A100)
#
# Usage: bash setup_gpu.sh
################################################################################
set -euo pipefail

echo "========================================"
echo "  KWYRE — GPU Training Environment Setup"
echo "========================================"

# Install NVIDIA drivers if not present
if ! command -v nvidia-smi &>/dev/null; then
    echo "[1/4] Installing NVIDIA drivers + CUDA..."
    apt-get update -qq
    apt-get install -y -qq linux-headers-$(uname -r) software-properties-common
    wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
    dpkg -i cuda-keyring_1.1-1_all.deb
    apt-get update -qq
    apt-get install -y -qq cuda-toolkit-12-4 nvidia-driver-550
    rm -f cuda-keyring_1.1-1_all.deb
    export PATH="/usr/local/cuda-12.4/bin:$PATH"
    export LD_LIBRARY_PATH="/usr/local/cuda-12.4/lib64:${LD_LIBRARY_PATH:-}"
    echo "[1/4] NVIDIA drivers installed. May need reboot."
else
    echo "[1/4] NVIDIA drivers already installed."
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi

# Install Python deps
echo "[2/4] Installing Python training dependencies..."
pip3 install -q --upgrade pip
pip3 install -q \
    "unsloth[cu124-torch260] @ git+https://github.com/unslothai/unsloth.git" \
    torch torchvision torchaudio \
    transformers accelerate peft trl datasets \
    bitsandbytes scipy sentencepiece protobuf \
    openai

echo "[3/4] Creating directory structure..."
mkdir -p ~/.kwyre/{models/trained,models/export,lora-adapters,training-data/kwyre-traces,logs}

echo "[4/4] Verifying GPU..."
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"

echo ""
echo "========================================"
echo "  Setup complete!"
echo "  Next: Upload traces to ~/.kwyre/training-data/kwyre-traces/"
echo "  Then: python3 train_distillation.py"
echo "========================================"
