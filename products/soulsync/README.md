# SoulSync

**Find Your Person. For Real.**

AI-Powered Soulmate Matching Platform by Mint Rail LLC.

SoulSync is not a swipe app. It's a deep matching platform that uses personality science and AI to connect people who are genuinely compatible — not just mutually attractive.

## Features

### Deep Personality Profiling
Comprehensive assessment combining Big Five personality traits, attachment style theory, love language identification, and core values alignment. One questionnaire, four psychological dimensions.

### AI-Powered Compatibility Scoring
Multi-dimensional matching algorithm that scores compatibility across personality complementarity, shared values, attachment dynamics, and love language alignment. Every match comes with a detailed breakdown — not just a number.

### Conversation Starters
Personalized icebreakers generated from the overlap and contrast between two profiles. References specific shared interests, complementary traits, and unique aspects of each person. No generic "hey" energy.

### Relationship Coaching
AI-driven guidance for new matches. Understands the psychological dynamics between two profiles and offers tailored advice for building connection based on each person's communication style and attachment needs.

### Deal-Breaker Detection
Flags hard incompatibilities before matching. Children preferences, religious alignment, location constraints, and lifestyle non-negotiables are caught early — saving time and emotional energy.

### Growth Compatibility
Predicts long-term relationship trajectory by analyzing how two personality profiles are likely to evolve together. Identifies areas of natural growth synergy and potential friction points.

## Architecture

```
products/soulsync/
├── server/
│   ├── app.py              # FastAPI application + WebSocket chat
│   ├── personality.py       # Big Five, attachment, love language, values
│   ├── matching.py          # Compatibility scoring algorithm
│   └── icebreaker.py        # Personalized conversation starters
├── site/
│   └── index.html           # Landing page
├── requirements.txt
├── wrangler.toml            # Cloudflare Pages config
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| POST | `/v1/profile/create` | Questionnaire answers → personality profile |
| POST | `/v1/profile/analyze` | Profile → Big Five + attachment + love language |
| POST | `/v1/match/score` | Two profiles → compatibility score + breakdown |
| POST | `/v1/match/find` | Profile → top matches from pool |
| POST | `/v1/icebreaker/generate` | Two profiles → conversation starters |
| POST | `/v1/coaching/advice` | Match context → relationship guidance |
| WS | `/ws/chat` | Real-time messaging for matched pairs |

## Quick Start

```bash
cd products/soulsync
pip install -r requirements.txt
uvicorn server.app:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`.

## How Matching Works

1. **Trait Complementarity** (25%) — Introvert + extrovert pairs score higher than same-same. Conscientiousness similarity is rewarded. Neuroticism gaps are penalized.
2. **Shared Values** (30%) — Career, family, adventure, stability, growth, spirituality. Overlap on what matters most drives long-term compatibility.
3. **Attachment Dynamics** (20%) — Secure + anything is favorable. Anxious + avoidant is flagged as high-risk. Two secures is ideal.
4. **Love Language Alignment** (15%) — Matching on how you give and receive love reduces friction.
5. **Deal-Breaker Check** (10%) — Hard filters on children, religion, location. Binary pass/fail that gates the final score.

## License

Proprietary — Mint Rail LLC. All rights reserved.
