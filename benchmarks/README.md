# Benchmarks

Benchmark suite comparing Kwyre against GPT-4o.

- `benchmark.py` — Runner: loads datasets, queries server, LLM-as-judge scoring
- `datasets/compliance_tasks.json` — 10 compliance analysis tasks
- `datasets/nda_analysis.json` — 10 NDA/contract analysis tasks
- `datasets/financial_analysis.json` — 10 financial forensics tasks

Run: `python benchmarks/benchmark.py` (requires running server)
