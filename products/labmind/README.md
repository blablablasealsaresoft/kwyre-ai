# LabMind

**AI for Scientific Discovery** — by Mint Rail LLC

LabMind is a research acceleration platform that gives scientists and R&D teams an API for literature synthesis, experiment design, hypothesis generation, statistical analysis planning, and paper drafting. Built on Python, FastAPI, sentence-transformers, and FAISS.

---

## Features

### Literature Synthesis
Semantic search over your document corpus using FAISS inner-product similarity and sentence-transformer embeddings (`all-MiniLM-L6-v2`). Add papers, search by meaning, and synthesize multiple documents into structured summaries with:
- Thematic clustering via keyword frequency analysis
- Cross-document consensus detection
- Research gap identification from hedging language markers
- Date range and provenance tracking

### Experiment Design
Generate structured experimental protocols from a research question, variables, and hypothesis. The engine:
- Selects the best-fit design (RCT, factorial, crossover, cohort, case-control, repeated measures)
- Computes required sample size via z-approximation power analysis (scipy)
- Identifies controls (negative, randomization, blinding, counterbalancing)
- Enumerates potential confounds with mitigation strategies
- Outputs a step-by-step methodology (recruitment → randomization → baseline → intervention → data collection → analysis)

### Hypothesis Generation
Transform raw observations into formal testable hypotheses:
- Classifies as causal, correlational, or exploratory based on language markers
- Generates null and alternative hypothesis pairs
- Suggests appropriate study designs per hypothesis type

### Statistical Analysis Planning
Describe your data (sample size, groups, data type, paired/independent) and receive:
- Primary and alternative test recommendations (t-test, ANOVA, chi-square, Mann-Whitney, Wilcoxon, Kruskal-Wallis, linear/logistic regression)
- Assumption checklists with scipy function calls
- Effect size metrics and interpretation benchmarks
- P-value guidance and reporting templates

### Paper Drafting
Scaffold publication-ready manuscripts with section templates for introduction, methods, results, discussion, conclusion, and literature review. Includes structural guidance (funnel structure, APA formatting, replication-ready methods).

### Citation Graph Analysis
Map relationships across your indexed literature — identify seminal works, trace lineages, and surface cross-disciplinary connections.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + Uvicorn |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector index | FAISS (inner product, flat index) |
| Power analysis | scipy.stats |
| Data models | Pydantic v2 |
| Runtime | Python 3.11+ |

---

## Project Structure

```
labmind/
├── server/
│   ├── app.py            # FastAPI application with all routes
│   ├── literature.py     # EmbeddingIndex: FAISS + sentence-transformers
│   ├── experiment.py     # Experiment designer with power analysis
│   └── stats.py          # Statistical test recommender
├── site/
│   └── index.html        # Landing page
├── requirements.txt
├── wrangler.toml         # Cloudflare Pages config
└── README.md
```

---

## Quickstart

### Install

```bash
cd products/labmind
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

API docs available at `http://localhost:8000/docs`.

### Example Requests

**Add documents to the index:**

```bash
curl -X POST http://localhost:8000/v1/literature/add \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "CRISPR-Cas9 enables precise genome editing but off-target effects remain a concern...",
      "RNA interference provides an alternative gene silencing approach with distinct specificity..."
    ],
    "metadata": [
      {"title": "CRISPR Off-Target Review", "authors": ["Zhang et al."], "year": 2023},
      {"title": "RNAi Specificity Analysis", "authors": ["Smith et al."], "year": 2022}
    ]
  }'
```

**Search by meaning:**

```bash
curl -X POST http://localhost:8000/v1/literature/search \
  -H "Content-Type: application/json" \
  -d '{"query": "gene editing specificity and safety", "k": 5}'
```

**Design an experiment:**

```bash
curl -X POST http://localhost:8000/v1/experiment/design \
  -H "Content-Type: application/json" \
  -d '{
    "research_question": "Does compound X reduce tumor growth in mice?",
    "independent_vars": ["compound_X_dose"],
    "dependent_vars": ["tumor_volume", "survival_days"],
    "hypothesis": "Compound X reduces tumor volume in a dose-dependent manner",
    "expected_effect_size": 0.6,
    "power": 0.80
  }'
```

**Get a statistical plan:**

```bash
curl -X POST http://localhost:8000/v1/stats/plan \
  -H "Content-Type: application/json" \
  -d '{
    "sample_size": 45,
    "groups": 3,
    "data_type": "continuous",
    "paired": false,
    "normal_distribution": true
  }'
```

**Generate hypotheses:**

```bash
curl -X POST http://localhost:8000/v1/hypothesis/generate \
  -H "Content-Type: application/json" \
  -d '{
    "observations": [
      "Higher caffeine intake correlates with reduced Parkinson risk",
      "Sleep deprivation increases cortisol levels"
    ],
    "domain": "neuroscience"
  }'
```

**Draft a paper:**

```bash
curl -X POST http://localhost:8000/v1/paper/draft \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Effects of Compound X on Tumor Growth",
    "authors": ["J. Doe", "A. Smith"],
    "abstract_summary": "the dose-dependent effects of compound X on tumor volume in murine models",
    "key_findings": ["Compound X reduced tumor volume by 40% at 10mg/kg", "No significant toxicity observed"]
  }'
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/v1/literature/add` | POST | Add documents to the semantic index |
| `/v1/literature/search` | POST | Semantic similarity search |
| `/v1/literature/synthesize` | POST | Multi-document synthesis |
| `/v1/experiment/design` | POST | Generate experimental protocol |
| `/v1/hypothesis/generate` | POST | Pattern-based hypothesis generation |
| `/v1/stats/plan` | POST | Statistical test recommendation |
| `/v1/paper/draft` | POST | Research paper section scaffolding |

Full interactive docs at `/docs` (Swagger) or `/redoc` (ReDoc) when the server is running.

---

## Deployment

### Static Site (Cloudflare Pages)

```bash
npx wrangler pages deploy site/
```

### API Server

Deploy the FastAPI server to any Python-capable host (Docker, Railway, Fly.io, EC2, etc.):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Target Audiences

- **Academic researchers** — accelerate literature reviews, plan experiments, draft publications
- **Pharma R&D** — streamline drug discovery pipelines with structured protocols
- **Biotech** — navigate genomics, proteomics, and molecular biology literature at scale
- **Materials science** — design experiments for novel material characterization

---

## License

Proprietary — Mint Rail LLC. All rights reserved.
