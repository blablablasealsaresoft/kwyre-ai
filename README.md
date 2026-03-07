# Kwyre AI: Spike-Encoded LLM Inference

**Production-grade LLM serving with SpikeServe** -- a novel activation encoding layer that quantizes neural activations into integer spike counts, enabling 40-60% fewer multiplications on sparse-aware hardware.

Currently serving **Qwen3.5-9B** at [api.kwyre.com](https://api.kwyre.com) with 4-bit weight quantization + spike activation analysis, 19 live API tools, and a full QAT training pipeline.

Built on research from [SpikingBrain](https://arxiv.org/abs/2509.05276) (BICLab, 2025).

---

## How SpikeServe Works

Traditional inference quantizes **weights** (GPTQ, GGUF, bitsandbytes). SpikeServe quantizes **activations** into integer spike counts:

```
Activation x  -->  vth = mean(|x|) / k
              -->  spikes = round(x / vth)      # integer spike counts
              -->  clamp to [-max_spike, max_spike]
              -->  x_approx = spikes * vth       # reconstructed activation
```

**Why this works:** ~40-60% of spike counts are zero. On sparse-aware hardware (neuromorphic chips, sparse matrix engines), zero spikes mean zero compute -- no multiplication needed.

**This stacks on top of weight quantization:**
- Weights: 4-bit NF4 (bitsandbytes) -- saves memory
- Activations: Dynamic spike encoding (SpikeServe) -- saves compute

### Key Research Finding

Spike encoding **cannot** be bolted onto an arbitrary pretrained model. Even the most conservative settings (k=50) produce garbled output on unmodified Qwen3.5-9B. The model's weights must learn to tolerate activation quantization noise through **Quantization-Aware Training (QAT)**. SpikeServe measures 8.5% projected activation sparsity at k=8 on the unmodified model -- the activations *are* sparse enough to exploit, but QAT is required to actually apply them.

---

## Architecture

```
                    Kwyre AI Stack
    ┌─────────────────────────────────────────┐
    │           serve_local_4bit.py           │
    │    OpenAI-compatible HTTP API server    │
    │  POST /v1/chat/completions  GET /health │
    ├───────────────┬─────────────────────────┤
    │   tools.py    │    spike_serve.py       │
    │  19 live API  │  Activation spike hooks │
    │  integrations │  (measure or apply)     │
    ├───────────────┴─────────────────────────┤
    │        Qwen3.5-9B (4-bit NF4)          │
    │  262K context | 201 languages | MoE     │
    └─────────────────────────────────────────┘

              QAT Training Pipeline
    ┌─────────────────────────────────────────┐
    │           train_qat.py                  │
    │  QLoRA + STE spike hooks + k-curriculum │
    ├─────────────────────────────────────────┤
    │           spike_qat.py                  │
    │  SpikeSTEFunction (autograd)            │
    │  KCurriculumScheduler (k: 50 -> 5)     │
    ├─────────────────────────────────────────┤
    │  eval_spike.py    merge_and_export.py   │
    │  PPL + sparsity   LoRA merge + deploy   │
    └─────────────────────────────────────────┘
```

---

## Project Structure

```
├── serve_local_4bit.py    # Production server: Qwen3.5-9B + SpikeServe + tools
├── spike_serve.py         # SpikeServe: hook-based activation spike encoding
├── tools.py               # 19 live API tool integrations
├── chat.html              # Web UI for Kwyre AI
│
├── spike_qat.py           # QAT: STE spike encoding + k-curriculum scheduler
├── train_qat.py           # QAT training script (QLoRA + spike hooks)
├── eval_spike.py          # Evaluate spike quality across k values
├── merge_and_export.py    # Merge LoRA adapters + deploy
│
├── hf_7B_model/           # SpikingBrain-7B HuggingFace model (GLA-SWA)
├── hf_7B_VLM/             # SpikingBrain Vision-Language model
├── W8ASpike/              # Quantized inference with pseudo-spiking (Int2Spike)
├── vllm_hymeta/           # vLLM plugin for SpikingBrain inference
├── run_model/             # Example inference scripts
├── docker_build/          # Docker patches
│
├── test_*.py              # Test suite (tools, e2e, spike sweeps, baselines)
├── Dockerfile             # Container deployment
├── requirements.txt       # Dependencies
└── setup.py               # vllm_hymeta package setup
```

---

## Quick Start

### 1. Serve locally

```bash
pip install -r requirements.txt
pip install bitsandbytes accelerate peft

# Start the API server (downloads Qwen3.5-9B on first run, ~18GB)
python serve_local_4bit.py
```

The server starts at `http://localhost:8000` with:
- `POST /v1/chat/completions` -- OpenAI-compatible chat (requires API key)
- `GET /health` -- model info + spike sparsity stats
- `GET /` -- web chat UI

### 2. Chat via API

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-kwyre-..." \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is the weather in Tokyo?"}]}'
```

The server automatically detects tool-worthy queries (weather, crypto, math, etc.) and augments the LLM response with live data from 19 free APIs.

### 3. Docker deployment

```bash
docker build -t kwyre-ai .
docker run --gpus all -p 8000:8000 kwyre-ai
```

---

## SpikeServe Details

### spike_serve.py -- Inference layer

Attaches `register_forward_pre_hook` to eligible Linear layers (including bitsandbytes 4-bit). Two modes:

- **`measure_only=True`** (default): Computes sparsity stats without modifying activations. The model runs at full fidelity while reporting what sparsity spike encoding *would* achieve.
- **`measure_only=False`**: Actually replaces activations with spike-encoded approximations. Requires a QAT-trained model.

Layers skipped: embeddings, lm_head, layer norms, attention projections (q/k/v/o).

### spike_qat.py -- Training layer

Same spike encoding wrapped in a custom `torch.autograd.Function` with **Straight-Through Estimator (STE)**: the forward pass quantizes activations to integer spikes and reconstructs, while the backward pass passes gradients straight through as if the quantization wasn't there.

**K-curriculum scheduler** gradually increases quantization aggressiveness during training:

| Phase | k value | Effect |
|-------|---------|--------|
| 1 | k=50 | Nearly lossless (~2% quantization error) |
| 2 | k=25 | Mild quantization |
| 3 | k=12 | Moderate -- model starts adapting |
| 4 | k=8 | Production target |
| 5 | k=5 | Aggressive -- maximum sparsity |

---

## QAT Training

Teaches Qwen3.5-9B to tolerate spike-encoded activations via QLoRA fine-tuning with STE spike hooks.

### Run training

```bash
python train_qat.py \
  --gradient_checkpointing \
  --max_seq_len 1024 \
  --num_epochs 5 \
  --batch_size 1 \
  --grad_accum 16
```

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model_id` | Local HF cache | Model path or HuggingFace ID |
| `--dataset` | `teknium/OpenHermes-2.5` | Training dataset |
| `--max_samples` | 100,000 | Max training examples |
| `--lora_rank` | 64 | LoRA adapter rank |
| `--lora_alpha` | 128 | LoRA scaling factor |
| `--k_start` | 50.0 | Initial spike threshold divisor |
| `--k_end` | 5.0 | Final spike threshold divisor |
| `--k_schedule` | `step` | `step` (discrete phases) or `linear` |
| `--max_spike` | 31 | Maximum spike count |
| `--lr` | 2e-5 | Learning rate |
| `--warmup_steps` | 500 | LR warmup steps |

### What gets trained

- **Base model**: Frozen (4-bit NF4 quantized)
- **LoRA adapters**: Trainable, rank 64, on MLP layers only (`gate_proj`, `up_proj`, `down_proj`)
- **Optimizer**: paged_adamw_8bit (VRAM-efficient)
- **Spike hooks**: STE encoding on all MLP linear layers (408 layers on Qwen3.5-9B)

### Post-training

```bash
# Evaluate across k values
python eval_spike.py --adapter_path ./qat_output/final --k_values 50,25,12,8,5,3

# Merge LoRA into base model
python merge_and_export.py \
  --adapter_path ./qat_output/final \
  --output_dir ./qat_merged \
  --test_generation
```

---

## API Tools

The server routes user queries through 19 live API integrations (all free, no keys required):

| Category | Tools |
|----------|-------|
| **Data** | Weather (Open-Meteo), Cryptocurrency (CoinGecko), Exchange Rates (Frankfurter) |
| **Knowledge** | Dictionary, Country Info, Wikipedia-style facts |
| **Science** | NASA APOD, Earthquakes (USGS), Space News |
| **Math** | Expression solver (Newton API -- simplify, derive, integrate) |
| **Fun** | Jokes, Quotes, Trivia, Pokemon, Dog/Cat facts, Number facts |
| **Utility** | IP Geolocation, University search, Activity suggestions |

Tool routing is regex-based in `tools.py`. Up to 3 tools can fire per query.

---

## Performance

| Metric | Value |
|--------|-------|
| Base model | Qwen3.5-9B (Feb 2026) |
| Weight quantization | 4-bit NF4 (bitsandbytes) |
| VRAM usage | ~7.6 GB (inference), ~12 GB (QAT training) |
| Inference speed | ~4.6 tok/s (with tools), ~5.0 tok/s (pure) |
| Context window | 262,144 tokens |
| Languages | 201 |
| Spike layers analyzed | 408 (MLP linear layers) |
| Projected sparsity (k=8) | 8.5% (pre-QAT, measure only) |

---

## Original SpikingBrain Research

This project extends the spike encoding innovation from **SpikingBrain** (BICLab, 2025):

- Paper: [arXiv:2509.05276](https://arxiv.org/abs/2509.05276)
- Original repo: [BICLab/SpikingBrain-7B](https://github.com/BICLab/SpikingBrain-7B)
- Architecture: Hybrid GLA (Gated Linear Attention) + SWA (Sliding Window Attention)
- Key innovation: Dynamic spike encoding of activations achieving 69%+ sparsity

### Available SpikingBrain Models (ModelScope)

- [Pre-trained 7B](https://www.modelscope.cn/models/Panyuqi/V1-7B-base)
- [Chat 7B-SFT](https://www.modelscope.cn/models/Panyuqi/V1-7B-sft-s3-reasoning)
- [Vision-Language 7B](https://www.modelscope.cn/models/sherry12334/SpikingBrain-7B-VL)
- [Quantized W8ASpike](https://www.modelscope.cn/models/Abel2076/SpikingBrain-7B-W8ASpike)

### Citation

```bibtex
@article{pan2025spikingbrain,
  title={SpikingBrain Technical Report: Spiking Brain-inspired Large Models},
  author={Pan, Yuqi and Feng, Yupeng and Zhuang, Jinghao and Ding, Siyu and Liu, Zehao and Sun, Bohan and Chou, Yuhong and Xu, Han and Qiu, Xuerui and Deng, Anlin and others},
  journal={arXiv preprint arXiv:2509.05276},
  year={2025}
}
```

---

## License

MIT License. See [LICENSE](LICENSE).
