# NFLonr — Pre-Snap Intelligence Platform

NFL play prediction and formation analysis engine powered by Apollo CyberSentinel AI. Analyzes pre-snap formations, personnel groupings, micro-reads (stance tells, weight distribution, eye patterns), and historical tendency data to predict plays before the snap.

## Features

- **Play Prediction** — Formation + situation-based play probability modeling
- **Formation Analysis** — 200+ NFL formations with personnel groupings and tendency data
- **Micro-Read Detection** — Pre-snap tell categories (stance, weight, eyes, hands)
- **Tendency Analysis** — Historical play-calling pattern breakdowns by team/situation
- **AI Breakdown** — Claude-powered detailed game analysis
- **Live Predictions** — WebSocket-driven real-time prediction feed

## Quick Start

```bash
cd products/nflonr
pip install -r requirements.txt
python -m uvicorn server.app:app --reload --port 8002
```

API at `http://localhost:8002`, frontend at `site/index.html`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| POST | `/v1/predict/play` | Predict play from formation + situation |
| POST | `/v1/predict/formation` | Formation recognition and tendencies |
| POST | `/v1/analyze/micro-reads` | Pre-snap micro-aggression analysis |
| POST | `/v1/analyze/tendencies` | Team tendency breakdown |
| POST | `/v1/ai/breakdown` | AI-powered game breakdown |
| WS | `/ws/live-predictions` | Live prediction WebSocket |

## Architecture

Uses shared `products/_shared/ai_engine.py` (Anthropic Claude) and `products/_shared/analytics.py` (win probability, confidence intervals) modules.
