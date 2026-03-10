# Training

Custom model training pipeline for the Professional tier.

- `run_full_pipeline.sh` — Automated: traces → distillation → GRPO → export
- `run_training_only.sh` — Skip traces, run distillation → GRPO
- `setup_gpu.sh` — GPU instance setup script (CUDA + deps)
- `scripts/generate_traces.py` — Claude-powered reasoning trace generation
- `scripts/generate_traces_parallel.py` — Parallel multi-domain trace generation
- `scripts/train_distillation.py` — Unsloth QLoRA distillation fine-tuning
- `scripts/train_grpo_vanilla.py` — Vanilla GRPO reinforcement learning (no Unsloth)

Requires: H100 or A100 GPU with 24GB+ VRAM.
