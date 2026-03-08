# Kwyre Fine-Tuning Data Pipeline

Domain-specific data preparation for fine-tuning Kwyre's local AI on legal, financial, and forensic content. The pipeline produces JSONL in Alpaca/OpenHermes format compatible with `model/train_qat.py`.

**No ML dependencies** — uses only Python standard library (`json`, `pathlib`, `re`, `argparse`, `hashlib`). Suitable for data prep on machines without GPU or HuggingFace.

---

## Quick Start

```bash
# 1. Organize documents by domain
mkdir -p raw_docs/legal raw_docs/financial raw_docs/forensic
# Place .txt, .docx, or .pdf files in the appropriate subfolder

# 2. Run the preparation pipeline
python finetune/prepare_data.py raw_docs -o finetune_data.jsonl

# 3. Validate output
python finetune/validate_data.py finetune_data.jsonl

# 4. (On GPU machine) Launch fine-tuning — see "Launching Fine-Tuning" below
```

---

## Input Formats

### Supported File Types

| Format | Support | Notes |
|--------|---------|-------|
| **TXT** | Full | Plain text, UTF-8. No extra dependencies. |
| **DOCX** | Full | Extracted via stdlib (zipfile + xml.etree). |
| **PDF** | Optional | Requires `pdftotext` (poppler-utils). If missing, PDFs are skipped. |

### Directory Structure

Domain is inferred from the folder path. Place documents under:

```
input_dir/
├── legal/          # NDA clauses, contracts, privilege memos
│   ├── nda_sample.txt
│   └── contract.docx
├── financial/      # SEC filings, financial statements, audit docs
│   └── 10k_excerpt.pdf
└── forensic/       # Chain of custody, evidence logs, procedures
    └── coc_template.txt
```

If a file is not under `legal/`, `financial/`, or `forensic/`, it defaults to **legal**.

---

## Pipeline Usage

### `prepare_data.py`

```
usage: prepare_data.py input_dir [-o OUTPUT] [--domains DOMAIN ...] [--max-chunk N] [--min-content N] [--no-dedupe]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-o`, `--output` | `finetune_data.jsonl` | Output JSONL path |
| `--domains` | (all) | Restrict to `legal`, `financial`, `forensic` |
| `--max-chunk` | 4000 | Max characters per document chunk |
| `--min-content` | 100 | Min content length to process |
| `--no-dedupe` | off | Disable deduplication |

**Examples:**

```bash
# Legal only
python finetune/prepare_data.py raw_docs -o legal_data.jsonl --domains legal

# Larger chunks, no deduplication
python finetune/prepare_data.py raw_docs --max-chunk 8000 --no-dedupe
```

### Output Format

Each line is a JSON object compatible with HuggingFace datasets and `train_qat.py`:

```json
{
  "conversations": [
    {"from": "human", "value": "Analyze the following NDA clause for confidentiality obligations:\n\n[document text]"},
    {"from": "gpt", "value": "Provide: (1) Summary of confidentiality scope, (2) Key carve-outs..."}
  ],
  "domain": "legal",
  "difficulty": "medium"
}
```

---

## Validation

### `validate_data.py`

```
usage: validate_data.py INPUT [--strict]
```

- **Format**: Ensures `conversations` array with `human`/`gpt` turns and non-empty `value` strings.
- **Lengths**: Reports min/max instruction and response lengths.
- **Duplicates**: Detects duplicate conversation pairs via content hash.
- **PII**: Warns on patterns for emails, SSNs, US phone numbers, credit cards.
- **Statistics**: Token estimates, domain and difficulty distribution.

Use `--strict` to exit with code 1 on any error or duplicate.

---

## Templates

Templates live in `finetune/templates.py`. Each has:

- `system_prompt` — Role/context for the model
- `instruction_template` — Uses `{document}` or `{content}` placeholder
- `expected_format` — Structure the model should follow in its response
- `difficulty` — `easy`, `medium`, or `hard`

### Domain Coverage

| Domain | Count | Examples |
|--------|-------|----------|
| **Legal** | 12 | NDA analysis, privilege review, contract interpretation, GDPR, M&A due diligence |
| **Financial** | 12 | SEC filing review, forensic accounting, ASC 606, BSA/AML, FINRA, SOX |
| **Forensic** | 12 | Chain of custody, evidence analysis, expert reports, e-discovery, DOJ CCIPS |

---

## Launching Fine-Tuning

`model/train_qat.py` expects a HuggingFace dataset. For local JSONL:

### Option A: Modify `train_qat.py`

Add support for a local JSONL path:

```python
# In load_and_prepare_dataset, when args.dataset points to a file:
if Path(args.dataset).suffix == ".jsonl":
    from datasets import load_dataset
    ds = load_dataset("json", data_files={"train": args.dataset}, split="train")
else:
    ds = load_dataset(args.dataset, split="train")
```

Then run:

```bash
python model/train_qat.py --dataset finetune_data.jsonl --output_dir ./qat_output
```

### Option B: Use HuggingFace Datasets Directly

```python
from datasets import load_dataset
ds = load_dataset("json", data_files={"train": "finetune_data.jsonl"}, split="train")
# Pass ds to your trainer
```

---

## Data Quality Guidelines

1. **Source documents**: Use real but anonymized materials. Avoid synthetic or low-quality text.
2. **Chunking**: Long documents are split at paragraph/sentence boundaries. Adjust `--max-chunk` for your use case.
3. **PII**: Run `validate_data.py` and redact any PII before training.
4. **Balance**: Aim for a reasonable mix of domains and difficulties.
5. **Deduplication**: Keep deduplication enabled unless you intentionally want repeated pairs.

---

## Example End-to-End

```bash
# 1. Create sample input
mkdir -p raw_docs/legal
echo "Confidentiality. Each party agrees to keep confidential all information..." > raw_docs/legal/sample_nda.txt

# 2. Prepare
python finetune/prepare_data.py raw_docs -o finetune_data.jsonl

# 3. Validate
python finetune/validate_data.py finetune_data.jsonl

# 4. Inspect
head -n 1 finetune_data.jsonl | python -m json.tool
```

---

## File Summary

| File | Purpose |
|------|---------|
| `prepare_data.py` | Extract text, apply templates, output JSONL |
| `templates.py` | 36 domain-specific prompt templates |
| `validate_data.py` | Format, PII, and stats validation |
| `README.md` | This documentation |
