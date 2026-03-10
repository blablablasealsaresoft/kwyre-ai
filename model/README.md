# Model

Model training, quantization, and inference hooks.

- `spike_serve.py` — SpikeServe activation encoding (inference hooks)
- `spike_qat.py` — QAT training hooks (STE, k-curriculum)
- `train_qat.py` — QAT training pipeline (Professional tier, 9B only)
- `quantize_nf4.py` — NF4 pre-quantization script
- `quantize_awq.py` — AWQ quantization (Professional tier)
- `convert_gguf.py` — HuggingFace → GGUF converter
- `convert_mlx.py` — HuggingFace → MLX converter
- `merge_and_export.py` — LoRA merge + deployment export
- `eval_spike.py` — Spike sparsity evaluation
