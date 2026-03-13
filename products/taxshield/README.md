# TaxShield

**AI-Powered Tax Strategy** by Mint Rail LLC

TaxShield helps CPAs, tax attorneys, financial advisors, and small business owners optimize tax outcomes through intelligent analysis of deductions, entity structures, depreciation strategies, and audit risk.

## Features

- **Tax Planning Optimization** — Analyze income, deductions, and credits to minimize tax liability across federal and state levels.
- **Deduction Analysis** — Categorize expenses into IRS categories, surface commonly missed deductions, and estimate savings at each tax bracket.
- **Entity Structure Recommendations** — Side-by-side comparison of Sole Proprietorship, LLC, S-Corp, and C-Corp with total tax, effective rate, and self-employment tax savings.
- **Depreciation Planning** — MACRS schedules (3–20 year property classes), Section 179 immediate expensing, and bonus depreciation with year-by-year breakdowns.
- **Estimated Tax Calculations** — Quarterly estimated payment projections based on income, deductions, and filing status.
- **Audit Risk Scoring** — Score tax return profiles from 1–100 based on red-flag indicators used in IRS DIF scoring.
- **Multi-State Tax Optimization** — Identify nexus obligations and allocation strategies for businesses operating across state lines.

## Target Users

| Audience | Use Case |
|---|---|
| CPAs | Client tax planning and scenario modeling |
| Tax Attorneys | Entity restructuring analysis |
| Financial Advisors | Integrated tax-aware financial planning |
| Small Business Owners | Self-service deduction and entity optimization |

## Quick Start

```bash
cd server
pip install -r ../requirements.txt
uvicorn app:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Visit `/docs` for the interactive Swagger UI.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health check |
| POST | `/v1/deductions/analyze` | Analyze expenses for deductions and savings |
| POST | `/v1/entity/compare` | Compare tax liability across entity types |
| POST | `/v1/depreciation/plan` | Generate depreciation schedules for assets |
| POST | `/v1/estimate/quarterly` | Calculate quarterly estimated payments |
| POST | `/v1/audit/risk` | Score audit risk (1–100) |
| POST | `/v1/strategy/optimize` | Full-profile tax strategy recommendations |

## Project Structure

```
taxshield/
├── server/
│   ├── app.py              # FastAPI application and routes
│   ├── deductions.py        # Deduction categorization and analysis
│   ├── entity.py            # Entity structure comparison engine
│   └── depreciation.py      # MACRS, Section 179, bonus depreciation
├── site/
│   └── index.html           # Landing page
├── requirements.txt
├── wrangler.toml            # Cloudflare Pages configuration
└── README.md
```

## License

Proprietary — Mint Rail LLC. All rights reserved.
