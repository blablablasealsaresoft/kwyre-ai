# DentAI

**AI-Powered Dental Intelligence** by [Mint Rail LLC](https://mintrail.com)

Clinical decision support for modern dental practices — treatment planning, insurance coding, clinical documentation, risk assessment, and material recommendations.

---

## Features

### Treatment Planning
Input chief complaint, symptoms, dental history, and clinical findings. DentAI generates a structured, phased treatment plan:
- **Phase 1 — Urgent**: Immediate interventions (abscess drainage, emergency exams, palliative care)
- **Phase 2 — Necessary**: Required restorative and periodontal treatment
- **Phase 3 — Elective**: Cosmetic and optional procedures

Each procedure includes estimated cost, priority ranking, duration, CDT code, and clinical rationale.

### Radiograph Analysis Prep
Upload dental radiographs (periapical, bitewing, panoramic) for structured pre-analysis. Images are securely stored and queued for AI-assisted diagnostic findings. Supports JPEG, PNG, and TIFF formats.

### CDT Insurance Coding
Describe any dental procedure in plain language. The CDT engine uses fuzzy matching against ~100 common procedure codes to return:
- Top matching CDT codes with confidence scores
- Full ADA code descriptions
- Procedure categories (Diagnostic, Restorative, Endodontics, Periodontics, Oral Surgery, etc.)

### Clinical SOAP Notes
Generate compliant clinical notes from structured input:
- **Subjective**: Chief complaint, HPI, medical history, medications, allergies, pain level
- **Objective**: Exam findings, vitals, teeth examined, periodontal and radiographic findings
- **Assessment**: Diagnoses, differentials, prognosis
- **Plan**: Procedures performed/planned, prescriptions, referrals, patient education, follow-up

### Procedure Risk Assessment
Score procedural risk (0–10) based on:
- Procedure complexity baseline
- Patient factors: age, smoking status, diabetes, immunocompromised status, anticoagulant therapy, pregnancy, ASA classification
- Returns risk level (Low/Moderate/High/Critical), contributing factors, recommendations, and contraindications

### Material Recommendations
Get evidence-based material options for crowns, fillings, implants, dentures, and veneers with:
- Pros and cons for each material
- Estimated cost ranges
- Expected longevity
- Best-use indications

---

## Quick Start

### Prerequisites
- Python 3.10+

### Installation

```bash
cd products/dentai
pip install -r requirements.txt
```

### Run the API Server

```bash
uvicorn server.app:app --reload --port 8000
```

The API is live at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
| POST | `/v1/treatment/plan` | Generate phased treatment plan |
| POST | `/v1/coding/suggest` | CDT code lookup with fuzzy matching |
| POST | `/v1/notes/generate` | Generate SOAP clinical note |
| POST | `/v1/risk/assess` | Procedure risk assessment |
| POST | `/v1/materials/recommend` | Material recommendations |
| POST | `/v1/radiograph/upload` | Upload radiograph for analysis |

### Example: Treatment Plan

```bash
curl -X POST http://localhost:8000/v1/treatment/plan \
  -H "Content-Type: application/json" \
  -d '{
    "chief_complaint": "Severe pain upper right molar",
    "symptoms": ["throbbing pain", "sensitivity to hot"],
    "dental_history": ["crown on #3 two years ago"],
    "findings": ["large carious lesion #2", "periapical radiolucency"]
  }'
```

### Example: CDT Coding

```bash
curl -X POST http://localhost:8000/v1/coding/suggest \
  -H "Content-Type: application/json" \
  -d '{"procedure_description": "porcelain crown on molar"}'
```

### Landing Page

Open `site/index.html` in a browser, or deploy to Cloudflare Pages:

```bash
npx wrangler pages deploy site/
```

---

## Target Audience

- **General Dentists** — streamline treatment planning and documentation
- **Orthodontists** — treatment sequencing and material selection
- **Oral Surgeons** — risk assessment and procedure planning
- **Dental Hygienists** — periodontal findings and SOAP notes
- **Endodontists** — root canal planning and CDT coding
- **Periodontists** — scaling/surgery planning with risk factors
- **Office Managers & Billing Staff** — accurate CDT code lookup to reduce claim denials

---

## Project Structure

```
products/dentai/
├── README.md
├── requirements.txt
├── wrangler.toml
├── server/
│   ├── __init__.py
│   ├── app.py            # FastAPI application + endpoints
│   ├── treatment.py       # Treatment planning engine
│   ├── coding.py          # CDT code fuzzy matching engine
│   └── notes.py           # SOAP note generator
└── site/
    └── index.html         # Landing page
```

---

## HIPAA Compliance Notice

DentAI is designed as a **clinical decision support tool**. When handling Protected Health Information (PHI):

- Deploy behind authentication and TLS in a HIPAA-eligible environment
- Patient data is processed in-memory — no PHI is persisted by default
- Radiograph uploads are stored to a temporary directory and should be configured for encrypted storage in production
- A Business Associate Agreement (BAA) is available for enterprise deployments
- This tool does not replace professional clinical judgment

---

## License

Proprietary — Mint Rail LLC. All rights reserved.
