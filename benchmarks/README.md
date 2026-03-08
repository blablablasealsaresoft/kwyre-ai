# Kwyre Benchmark Suite

Benchmark framework for evaluating Kwyre AI against GPT-4o on compliance-relevant legal, financial, and forensic analysis tasks.

## Quick Start

```bash
# Ensure Kwyre server is running locally
python server/serve_local_4bit.py

# Run benchmarks against local Kwyre only
python benchmarks/benchmark.py

# Run with GPT-4o comparison (requires OpenAI API key)
OPENAI_API_KEY=sk-... python benchmarks/benchmark.py --compare-openai

# Run a specific dataset
python benchmarks/benchmark.py --dataset nda_analysis

# Run with custom Kwyre endpoint
python benchmarks/benchmark.py --kwyre-url http://127.0.0.1:8000
```

## Datasets

| Dataset | File | Tasks | Domain |
|---------|------|-------|--------|
| **Compliance Tasks** | `datasets/compliance_tasks.json` | 10 | Cross-domain: GDPR, AML, corporate governance, expert witness, insurance |
| **NDA Analysis** | `datasets/nda_analysis.json` | 10 | Contract law: confidentiality obligations, carve-outs, remedies, term |
| **Financial Analysis** | `datasets/financial_analysis.json` | 10 | SEC filings, forensic accounting, insurance, actuarial, AML |

Each dataset contains tasks with:
- Professional-grade prompts reflecting real-world use cases
- Reference answers with key points for scoring
- Scoring criteria specific to the domain
- Difficulty ratings (easy/medium/hard)

## How Scoring Works

The benchmark uses an **LLM-as-judge** approach:

1. Each prompt is sent to Kwyre (and optionally GPT-4o)
2. The response is evaluated against reference answers and scoring criteria
3. The local model scores each response on four dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **Accuracy** | 30% | Factual correctness of legal/financial/forensic claims |
| **Completeness** | 25% | Coverage of all key points in the reference answer |
| **Relevance** | 20% | Focus on the question asked, without tangential information |
| **Legal Correctness** | 25% | Proper use of legal terminology, appropriate caveats, jurisdictional awareness |

Scores are on a 1-10 scale per dimension, producing a weighted composite score.

## Output

Results are written to `benchmarks/results/` as timestamped markdown reports:

```
results/
  benchmark_2026-03-08_143000.md     # Full report with scores and comparisons
```

Each report includes:
- Per-task scores for each model
- Aggregate scores by category and difficulty
- Latency measurements (time to first token, total generation time)
- Side-by-side comparison when GPT-4o data is available
- Summary statistics and analysis

## Command-Line Options

```
python benchmarks/benchmark.py [OPTIONS]

Options:
  --kwyre-url URL          Kwyre API endpoint (default: http://127.0.0.1:8000)
  --kwyre-api-key KEY      Kwyre API key (default: sk-kwyre-dev-local)
  --compare-openai         Also run prompts against GPT-4o for comparison
  --openai-model MODEL     OpenAI model to compare against (default: gpt-4o)
  --dataset NAME           Run only a specific dataset (compliance_tasks, nda_analysis, financial_analysis)
  --max-tokens N           Max tokens per response (default: 1024)
  --output-dir DIR         Output directory for results (default: benchmarks/results)
  --verbose                Print responses to stdout during benchmark
  --skip-scoring           Skip LLM-as-judge scoring (latency benchmarks only)
```

## Requirements

- Python 3.10+
- `requests` library (included in Kwyre's requirements)
- Running Kwyre server instance
- (Optional) `openai` Python package and `OPENAI_API_KEY` for GPT-4o comparison

## Adding New Datasets

Create a JSON file in `datasets/` with this structure:

```json
{
  "name": "Dataset Name",
  "category": "legal|financial|forensic",
  "tasks": [
    {
      "id": "task-001",
      "prompt": "The actual prompt sent to the model...",
      "reference_answer": "Key points the response should cover...",
      "scoring_criteria": ["criterion1", "criterion2"],
      "difficulty": "easy|medium|hard"
    }
  ]
}
```

Then run:

```bash
python benchmarks/benchmark.py --dataset your_dataset_name
```

## Notes

- Benchmarks run against the local Kwyre server, so results reflect your hardware configuration
- GPT-4o comparison requires an active internet connection and API key — this breaks Kwyre's air-gap, so run comparisons on a separate machine or before air-gap deployment
- LLM-as-judge scoring has inherent variability; run multiple times for statistical significance
- The scoring model is Kwyre itself (the local model judges its own output), which may introduce self-preference bias — account for this when interpreting comparative results
