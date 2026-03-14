# MarchMind
### AI March Madness Tournament Intelligence

> Bracket predictions, matchup analysis, upset radar, and Monte Carlo simulation — powered by KenPom-style efficiency metrics and Claude AI.

[![Claude](https://img.shields.io/badge/inference-Claude%20AI-d4c896.svg)]()
[![Teams](https://img.shields.io/badge/coverage-64%2B%20teams-blue.svg)]()
[![WebSocket](https://img.shields.io/badge/live-WebSocket%20bracket%20feed-green.svg)]()
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)]()

---

## What Is MarchMind

MarchMind is an AI-powered March Madness bracket prediction platform. It uses KenPom-style adjusted efficiency metrics, historical upset rates, Monte Carlo simulation, and Claude AI analysis to help you build smarter brackets.

**Built by Mint Rail LLC.**

---

## Features

| Feature | Description |
|---------|-------------|
| **Matchup Predictor** | Head-to-head win probability using adjusted offensive/defensive efficiency, tempo, and strength of schedule |
| **Upset Radar** | Scans all first-round matchups for upset potential using historical seed-line data |
| **Bracket Simulator** | Monte Carlo simulation (up to 100K runs) to find region champion probabilities |
| **Conference Power** | Conference strength rankings by average adjusted efficiency of tournament teams |
| **AI Analyst** | Claude-powered bracket advice, matchup breakdowns, and strategy analysis |
| **Team Database** | 64+ tournament teams with KenPom-style metrics, records, and historical performance |

---

## Quick Start

```bash
cd products/marchmind

pip install -r requirements.txt

export ANTHROPIC_API_KEY=your-key-here  # for AI features
uvicorn server.app:app --reload
```

Open `site/index.html` in your browser, or deploy to Cloudflare Pages.

---

## API Reference

```
GET  /health
GET  /v1/teams
GET  /v1/teams/{name}
GET  /v1/teams/search/{query}
GET  /v1/teams/seed/{seed}
GET  /v1/teams/conference/{conf}
GET  /v1/regions
GET  /v1/regions/{region}
POST /v1/predict/matchup         { team_a, team_b, round_name }
POST /v1/predict/bracket         { region, simulations }
GET  /v1/predict/upsets?top_n=10
GET  /v1/analytics/conference-strength
GET  /v1/analytics/seed-history
POST /v1/ai/matchup-breakdown    { team_a, team_b, question }
POST /v1/ai/bracket-advice       { region, question }
POST /v1/ai/chat                 { question }
WS   /ws/bracket-live
```

---

## Built By

**Mint Rail LLC** — AI infrastructure, blockchain forensics, and applied machine learning.
