# NFL PlayCaller AI
### AI Offensive Coordinator Intelligence

> Blitz prediction, play optimization, scouting reports, and live game analysis — all running on Kwyre's local inference engine. Your data never leaves your machine.

[![Kwyre](https://img.shields.io/badge/inference-Kwyre%20Local%20AI-d4c896.svg)]()
[![Teams](https://img.shields.io/badge/coverage-32%20NFL%20teams-blue.svg)]()
[![WebSocket](https://img.shields.io/badge/live-WebSocket%20game%20feed-green.svg)]()
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)]()
[![React](https://img.shields.io/badge/UI-React%20%2B%20Vite-61DAFB.svg)]()

---

## What Is NFL PlayCaller

NFL PlayCaller is an AI-powered NFL analysis platform that acts as your personal offensive coordinator and defensive analyst. It uses Kwyre's local AI inference engine to generate professional coaching staff-level analysis — scouting reports, situational play calls, blitz predictions, player movement profiles, playbook reverse engineering, and post-game breakdowns.

All analysis runs locally through Kwyre. No data is sent to third-party cloud AI providers.

**Built by Mint Rail LLC.**

---

## Features

### Six Analysis Modes

| Mode | What It Does |
|------|-------------|
| **Pre-Game Scouting Report** | Full matchup breakdown with offensive tendencies, key playmakers, defensive scheme analysis, head-to-head advantages, and situational strategy (red zone, 3rd down, 2-minute) |
| **Situational Play Call** | Input the game situation — get the optimal play call with primary read, hot read, EV estimate, clock impact, and two alternatives |
| **Blitz & Coverage Read** | Predict blitz probability, coverage shell, pressure type, matchup assignments, and where the vulnerability is for the offense |
| **Player Movement Profile** | Deep dive on any player's route tree, tendencies by down/distance, red zone behavior, injury impact, and containment strategy |
| **Playbook Reverse Engineer** | Reconstruct a team's offensive scheme from formation frequencies, motion patterns, run/pass splits, and 5-year evolution |
| **Post-Game Breakdown** | Analyze completed games with drive-by-drive critical sequence analysis, scheme evaluation, and adjustment recommendations |

### Live Game Mode

Real-time game analysis via WebSocket. Connect to a live game feed and get:

- **Real-time scoreboard** — score, clock, quarter, possession
- **Play-by-play feed** — every play streamed as it happens
- **Auto play suggestions** — AI-generated play calls based on the current situation
- **Game state tracking** — down, distance, field position, drive stats
- **Demo mode** — simulated game for testing without a live data source

### All 32 NFL Teams

Complete tendency data for every team across all 8 divisions:

- Run/pass ratio
- Blitz rate
- Coverage base (Cover 1 / Cover 2 / Cover 3)
- Offensive tempo
- 5-year historical baseline

### Kwyre Integration

All AI analysis routes through Kwyre's local inference API at `localhost:8000`:

- OpenAI-compatible `/v1/chat/completions` endpoint
- No data leaves your machine
- Works with Kwyre Personal (4B), Professional (9B), or Cloud
- RAM-only processing — analysis never touches disk

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React App (Vite)          port 3000                    │
│  ├── Analysis Tab → POST /v1/analysis/*                 │
│  └── Live Game Tab → WS /ws/live-game                   │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  FastAPI Server                port 8080                │
│  ├── /health                                            │
│  ├── /v1/teams, /v1/divisions                           │
│  ├── /v1/analysis/scouting                              │
│  ├── /v1/analysis/playcall                              │
│  ├── /v1/analysis/blitz                                 │
│  ├── /v1/analysis/player                                │
│  ├── /v1/analysis/playbook                              │
│  ├── /v1/analysis/postgame                              │
│  ├── /ws/live-game (WebSocket)                          │
│  ├── AnalysisEngine → builds prompts, calls Kwyre       │
│  └── LiveGameManager → game state, demo simulation      │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  Kwyre Local AI                port 8000                │
│  └── /v1/chat/completions (OpenAI-compatible)           │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Kwyre running at `localhost:8000` (any tier — Personal, Professional, Air, or Cloud)

### 1. Start Kwyre

```bash
# Kwyre should already be running at localhost:8000
curl http://localhost:8000/health
```

### 2. Start the API Server

```bash
cd products/nfl-playcaller

pip install -r requirements.txt

uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
```

### 3. Start the React App

```bash
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

### 4. Landing Page (Static)

The marketing landing page is at `site/index.html`. Deploy to Cloudflare Pages:

```bash
npx wrangler pages deploy site
```

---

## API Reference

### Health

```
GET /health
```

Returns service status, Kwyre endpoint, team count, and live game state.

### Teams

```
GET /v1/teams                  → all 32 teams
GET /v1/teams/{abbr}           → team detail + stats
GET /v1/divisions              → teams grouped by division
```

### Analysis

All analysis endpoints accept JSON with `offense` and `defense` team abbreviations plus mode-specific fields.

```
POST /v1/analysis/scouting     → { offense, defense, notes }
POST /v1/analysis/playcall     → { offense, defense, down, distance, field_position, quarter, score, defensive_look, notes }
POST /v1/analysis/blitz        → { offense, defense, down, distance, field_position, quarter, score, defensive_look, notes }
POST /v1/analysis/player       → { offense, defense, player_name, notes }
POST /v1/analysis/playbook     → { offense, defense, notes }
POST /v1/analysis/postgame     → { offense, defense, notes }
```

Response:

```json
{
  "analysis_type": "scouting",
  "offense": "KC",
  "defense": "SF",
  "result": "## Pre-Game Scouting Report\n\n..."
}
```

### WebSocket: Live Game

```
WS /ws/live-game
```

Send JSON messages:

```json
{"action": "start", "home": "KC", "away": "SF"}
{"action": "stop"}
{"action": "status"}
{"action": "suggest"}
```

Receive events:

```json
{"type": "state", "data": { ... game state ... }}
{"type": "play", "data": { ... state + play_result ... }}
{"type": "suggestion", "data": { "text": "...", "situation": "..." }}
{"type": "final", "data": { ... final state ... }}
```

---

## Project Structure

```
products/nfl-playcaller/
├── server/
│   ├── app.py              # FastAPI server — routes, WebSocket, CORS
│   ├── analysis.py          # AnalysisEngine — prompt building, Kwyre integration
│   ├── live_game.py         # LiveGameManager — game state, WebSocket, demo sim
│   ├── teams.py             # All 32 NFL teams + tendency stats
│   └── __init__.py
├── app/
│   ├── App.jsx              # React app — analysis tab + live game tab
│   └── main.jsx             # React entry point
├── site/
│   └── index.html           # Landing page — tactical/military aesthetic
├── index.html               # Vite entry point
├── vite.config.js           # Vite config with API proxy
├── package.json             # React + Vite dependencies
├── requirements.txt         # Python dependencies
├── wrangler.toml            # Cloudflare Pages deployment
└── README.md
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| Kwyre API URL | `http://localhost:8000` | Set in `server/analysis.py` — `KWYRE_BASE_URL` |
| API server port | `8080` | Set in `uvicorn` command |
| React dev port | `3000` | Set in `vite.config.js` |
| WebSocket URL | `ws://localhost:8080/ws/live-game` | Set in `app/App.jsx` — `WS_URL` |

---

## Built By

**Mint Rail LLC** — AI infrastructure, blockchain forensics, and applied machine learning.

NFL PlayCaller is a Kwyre product. Visit [kwyre.com](https://kwyre.com) for the full platform.

---

*All analysis runs locally through Kwyre. No data leaves your machine.*
