# LaunchPad — AI-Powered Job Placement Platform

**AI That Lands You the Job.**

Built by [Mint Rail LLC](https://mintrail.com)

---

## What is LaunchPad?

LaunchPad is an end-to-end AI job placement platform that takes candidates from resume to offer letter. It combines NLP-driven resume analysis, personalized interview coaching, intelligent job matching, and salary negotiation strategy into a single product.

## Features

### Resume Optimization
- **ATS Scoring** — Score your resume 0–100 against any job description. Measures keyword density, section completeness, quantified achievements, and action verb usage.
- **Keyword Extraction** — Automatically pull required skills and qualifications from job postings and map them to your resume gaps.
- **Formatting Analysis** — Flag formatting issues that trip up Applicant Tracking Systems (missing section headers, inconsistent dates, walls of text).
- **One-Click Optimization** — Submit your resume + a job description and receive an optimized version with targeted improvements.

### Cover Letter Generation
- Generate tailored cover letters from your resume and a target job description.
- Matches tone and emphasis to the role, company culture, and seniority level.

### Interview Preparation
- **Question Generation** — Behavioral, technical, and situational questions customized to role, company, and experience level.
- **Model Answers** — STAR-format (Situation, Task, Action, Result) sample answers for every generated question.
- **Live Coaching** — Real-time WebSocket-based interview practice with feedback.
- **Role Libraries** — Pre-built question banks for Software Engineer, Product Manager, Data Scientist, Sales, Marketing, Finance, and Consulting.

### Job-Candidate Matching
- **Skills-to-Jobs Similarity** — TF-IDF keyword overlap scoring ranks open positions by fit.
- **Multi-Factor Ranking** — Factors in location preference, salary range, experience level, and industry.
- **Fit Score** — Each job receives a 0–100 match score with a breakdown of why.

### Salary Negotiation Coaching
- Analyze an offer (base, equity, bonus, benefits) against market data.
- Generate a counter-offer strategy with specific talking points and anchoring techniques.

### LinkedIn Profile Optimization
- Section-by-section recommendations for headline, summary, experience, and skills.
- Keyword optimization for recruiter search visibility.

### Application Tracking Dashboard
- Track every application: company, role, status, dates, notes.
- Pipeline view: Applied → Screening → Interview → Offer → Accepted/Rejected.

---

## Architecture

```
products/launchpad/
├── README.md
├── requirements.txt
├── wrangler.toml
├── server/
│   ├── app.py          # FastAPI application + WebSocket
│   ├── resume.py       # ResumeAnalyzer class
│   ├── interview.py    # InterviewPrep class
│   └── matching.py     # JobMatcher class
└── site/
    └── index.html      # Landing page (vanilla HTML/CSS/JS)
```

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Install

```bash
cd products/launchpad
pip install -r requirements.txt
```

### Run the API Server

```bash
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

API docs available at `http://localhost:8000/docs` (Swagger UI).

### Serve the Landing Page

Open `site/index.html` in a browser, or serve it:

```bash
python -m http.server 3000 --directory site
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/v1/resume/analyze` | Analyze resume text → ATS score + improvements |
| POST | `/v1/resume/optimize` | Resume + job description → optimized resume |
| POST | `/v1/cover-letter/generate` | Resume + job description → cover letter |
| POST | `/v1/interview/prepare` | Role + company → questions + model answers |
| POST | `/v1/match/jobs` | Skills + preferences → ranked job matches |
| POST | `/v1/salary/negotiate` | Offer details → counter-offer strategy |
| WS | `/ws/coaching` | Live interview practice session |

### POST `/v1/resume/analyze`

**Request:**
```json
{
  "resume_text": "John Doe\nSoftware Engineer\n...",
  "job_description": "We are looking for a senior engineer..."
}
```

**Response:**
```json
{
  "ats_score": 72,
  "breakdown": {
    "keyword_match": 65,
    "formatting": 80,
    "achievements": 70,
    "action_verbs": 75
  },
  "improvements": [
    "Add quantified achievements (e.g., 'Reduced load time by 40%')",
    "Include 'Kubernetes' — mentioned 3x in the job description"
  ],
  "missing_keywords": ["Kubernetes", "CI/CD", "Agile"],
  "sections_found": ["experience", "education", "skills"]
}
```

### POST `/v1/interview/prepare`

**Request:**
```json
{
  "role": "software_engineer",
  "company": "Stripe",
  "level": "senior"
}
```

**Response:**
```json
{
  "questions": [
    {
      "type": "behavioral",
      "question": "Tell me about a time you had to debug a critical production issue.",
      "model_answer": "Situation: Our payment processing pipeline went down during peak hours..."
    }
  ]
}
```

---

## Pricing

| Feature | Free | Pro ($29/mo) | Enterprise |
|---------|------|-------------|------------|
| Resume Analysis | 3/month | Unlimited | Unlimited |
| Cover Letters | 1/month | Unlimited | Unlimited |
| Interview Prep | Basic | Advanced + Live | Custom |
| Job Matching | 10 results | 50 results | API access |
| Salary Coaching | — | ✓ | ✓ |
| LinkedIn Optimization | — | ✓ | ✓ |
| Application Tracker | 5 apps | Unlimited | Team dashboard |

---

## Deployment

### Cloudflare Pages (Landing Page)

```bash
npx wrangler pages deploy site --project-name launchpad
```

### API Server

Deploy `server/` to any Python-capable host (Railway, Render, Fly.io, EC2).

---

## License

Proprietary — Mint Rail LLC. All rights reserved.
