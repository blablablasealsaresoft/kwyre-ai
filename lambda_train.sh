#!/bin/bash
# Kwyre QAT Training — Lambda GH200 (96 GB HBM3)
# Run this script on the Lambda instance after cloning the repo.
#
# Usage:
#   chmod +x lambda_train.sh
#   ./lambda_train.sh
#
# To resume from a checkpoint:
#   ./lambda_train.sh --resume_from ./qat_output_v1/checkpoint-500
set -euo pipefail

echo "============================================================"
echo "Kwyre QAT Training — Lambda GH200 Setup"
echo "============================================================"

pip install --upgrade pip Pillow
pip install torch torchvision torchaudio
pip install transformers accelerate bitsandbytes peft trl datasets
pip install psutil safetensors tokenizers scipy pyyaml huggingface_hub

echo "[Setup] Dependencies installed."

echo "[Setup] Downloading Qwen3.5-9B model weights..."
python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer
print('Downloading tokenizer...')
AutoTokenizer.from_pretrained('Qwen/Qwen3.5-9B', trust_remote_code=True)
print('Downloading model weights (this takes a few minutes)...')
AutoModelForCausalLM.from_pretrained('Qwen/Qwen3.5-9B', trust_remote_code=True, torch_dtype='auto')
print('Model cached successfully.')
"

echo "[Setup] Downloading OpenHermes-2.5 dataset..."
python -c "
from datasets import load_dataset
ds = load_dataset('teknium/OpenHermes-2.5', split='train')
print(f'Dataset cached: {len(ds):,} samples')
"

echo ""
echo "============================================================"
echo "Starting QAT Training"
echo "============================================================"
echo ""

# GH200 96GB optimizations:
#   - batch_size=8 (vs 1 on laptop) — 96GB can hold 8 sequences easily
#   - grad_accum=2 (effective batch = 16, same as laptop config)
#   - layer_stride=1 (hook ALL layers — we have the VRAM for it)
#   - max_seq_len=2048 (full context, no compromise)
#   - num_epochs=1 (47.5K samples, ~2969 steps at eff_batch=16)
#   - Estimated: ~5-10s/step on GH200 → ~4-8 hours total

python model/train_qat.py \
  --model_id Qwen/Qwen3.5-9B \
  --dataset teknium/OpenHermes-2.5 \
  --max_samples 50000 \
  --num_epochs 1 \
  --batch_size 8 \
  --grad_accum 2 \
  --lora_rank 64 \
  --lora_alpha 128 \
  --max_seq_len 2048 \
  --layer_stride 1 \
  --k_start 50.0 \
  --k_end 5.0 \
  --k_schedule step \
  --lr 2e-5 \
  --output_dir ./qat_output_v1 \
  --save_steps 500 \
  --eval_steps 250 \
  --logging_steps 25 \
  "$@"

echo ""
echo "============================================================"
echo "Training complete. Artifacts in ./qat_output_v1/final/"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Copy trained adapters back to your local machine:"
echo "     scp -r ubuntu@<lambda-ip>:~/kwyre-ai/qat_output_v1/final/ ./qat_output_v1/final/"
echo "  2. Merge LoRA adapters (optional, can be done locally):"
echo "     python -c \"from peft import PeftModel; ...\""
echo "  3. Update serve_local_4bit.py to load the trained model"
