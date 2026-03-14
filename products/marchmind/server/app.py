"""
MarchMind — March Madness Tournament Intelligence API

AI-powered bracket predictions, matchup analysis, upset radar,
conference strength rankings, and Monte Carlo bracket simulation.
"""

from __future__ import annotations

import json
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from products._shared.ai_engine import AIEngine

from .brackets import (
    get_team,
    search_teams,
    get_teams_by_seed,
    get_teams_by_conference,
    get_region_bracket,
    TEAMS,
    REGIONS,
    CONFERENCES,
    HISTORICAL_UPSET_RATES,
)
from .predictions import (
    predict_matchup,
    upset_radar,
    simulate_bracket,
    conference_strength,
)

app = FastAPI(
    title="MarchMind API",
    description="March Madness Tournament Intelligence — AI bracket predictions and matchup analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai = AIEngine(
    default_system=(
        "You are MarchMind AI, an elite college basketball analytics expert specializing "
        "in March Madness tournament prediction. You combine KenPom-style efficiency metrics, "
        "historical upset patterns, coaching matchups, conference strength, and situational "
        "factors to provide expert bracket analysis. Provide specific statistical reasoning "
        "with seed-line history, tempo matchup implications, and confidence levels."
    )
)


# ── Request Models ──────────────────────────────────────────────────────────

class MatchupRequest(BaseModel):
    team_a: str = Field(..., description="First team name (e.g. 'UConn')")
    team_b: str = Field(..., description="Second team name (e.g. 'Alabama')")
    round_name: str = ""
    notes: str = ""


class BracketRequest(BaseModel):
    region: str = Field(..., description="Region: East, West, South, or Midwest")
    simulations: int = Field(default=10000, ge=100, le=100000)


class TeamSearchRequest(BaseModel):
    query: str


class AIAnalysisRequest(BaseModel):
    team_a: str
    team_b: str = ""
    region: str = ""
    question: str = ""
    notes: str = ""


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "marchmind",
        "version": "1.0.0",
        "teams": len(TEAMS),
        "regions": REGIONS,
        "ai_available": ai.available,
        "ai_backend": ai.backend,
    }


# ── Team Data ───────────────────────────────────────────────────────────────

@app.get("/v1/teams")
async def list_teams():
    return {"teams": [asdict(t) for t in TEAMS], "count": len(TEAMS)}


@app.get("/v1/teams/{name}")
async def team_detail(name: str):
    team = get_team(name)
    if not team:
        return {"error": f"Team '{name}' not found"}
    return {"team": asdict(team)}


@app.get("/v1/teams/search/{query}")
async def team_search(query: str):
    results = search_teams(query)
    return {"teams": [asdict(t) for t in results], "count": len(results)}


@app.get("/v1/teams/seed/{seed}")
async def teams_by_seed(seed: int):
    results = get_teams_by_seed(seed)
    return {"seed": seed, "teams": [asdict(t) for t in results]}


@app.get("/v1/teams/conference/{conf}")
async def teams_by_conference(conf: str):
    results = get_teams_by_conference(conf)
    return {"conference": conf, "teams": [asdict(t) for t in results]}


@app.get("/v1/regions")
async def list_regions():
    return {"regions": REGIONS}


@app.get("/v1/regions/{region}")
async def region_bracket(region: str):
    bracket = get_region_bracket(region)
    if not bracket:
        return {"error": f"Region '{region}' not found. Use: {', '.join(REGIONS)}"}
    return {"region": region, "bracket": [asdict(t) for t in bracket]}


# ── Predictions ─────────────────────────────────────────────────────────────

@app.post("/v1/predict/matchup")
async def predict_matchup_endpoint(req: MatchupRequest):
    result = predict_matchup(req.team_a, req.team_b)
    if not result:
        return {"error": f"Could not find one or both teams: '{req.team_a}', '{req.team_b}'"}
    return {
        "matchup": asdict(result),
        "round": req.round_name or "Unknown",
    }


@app.post("/v1/predict/bracket")
async def simulate_bracket_endpoint(req: BracketRequest):
    if req.region not in REGIONS:
        return {"error": f"Invalid region. Use: {', '.join(REGIONS)}"}
    results = simulate_bracket(req.region, runs=req.simulations)
    return {
        "region": req.region,
        "simulations": req.simulations,
        "champion_probabilities": results,
    }


@app.get("/v1/predict/upsets")
async def upset_radar_endpoint(top_n: int = 10):
    upsets = upset_radar(top_n)
    return {"upsets": upsets, "count": len(upsets)}


@app.get("/v1/analytics/conference-strength")
async def conference_strength_endpoint():
    rankings = conference_strength()
    return {"conferences": rankings}


@app.get("/v1/analytics/seed-history")
async def seed_history():
    return {
        "upset_rates": {
            f"{k[0]} vs {k[1]}": round(v * 100, 1)
            for k, v in sorted(HISTORICAL_UPSET_RATES.items())
        },
        "note": "Historical upset rates by seed matchup in NCAA tournament first round",
    }


# ── AI Analysis ─────────────────────────────────────────────────────────────

@app.post("/v1/ai/matchup-breakdown")
async def ai_matchup_breakdown(req: AIAnalysisRequest):
    result = predict_matchup(req.team_a, req.team_b) if req.team_b else None

    context = f"Matchup: {req.team_a} vs {req.team_b}\n"
    if result:
        context += f"Win probability: {result.team_a} {result.win_prob_a:.0%} — {result.team_b} {result.win_prob_b:.0%}\n"
        context += f"Predicted margin: {result.margin} points\n"
        context += f"Key factors: {'; '.join(result.key_factors)}\n"
    if req.notes:
        context += f"Additional context: {req.notes}\n"

    prompt = (
        f"{context}\n"
        f"Provide a detailed March Madness matchup breakdown including:\n"
        f"1. Style matchup analysis (tempo, offense vs defense)\n"
        f"2. Key players and matchup advantages\n"
        f"3. Historical seed-line performance\n"
        f"4. Upset potential and conditions\n"
        f"5. Prediction with confidence level"
    )

    resp = await ai.complete(prompt)
    return {
        "analysis": resp.text if resp.ok else None,
        "statistical_prediction": asdict(result) if result else None,
        "ai_available": ai.available,
        "error": resp.error,
    }


@app.post("/v1/ai/bracket-advice")
async def ai_bracket_advice(req: AIAnalysisRequest):
    if req.region:
        bracket = get_region_bracket(req.region)
        sim = simulate_bracket(req.region, runs=5000)
        teams_str = ", ".join(f"({t.seed}) {t.name}" for t in bracket[:8])
        sim_str = ", ".join(f"{r['team']} {r['probability']:.0%}" for r in sim[:5])
        context = f"Region: {req.region}\nTop seeds: {teams_str}\nSimulation favorites: {sim_str}"
    else:
        context = "Full tournament bracket advice"

    upsets = upset_radar(5)
    upset_str = ", ".join(f"({u['underdog']['seed']}) {u['underdog']['name']} over ({u['favored']['seed']}) {u['favored']['name']} ({u['upset_probability']:.0%})" for u in upsets)
    context += f"\nTop upset picks: {upset_str}"

    if req.question:
        context += f"\nUser question: {req.question}"

    prompt = (
        f"{context}\n\n"
        f"Provide expert March Madness bracket advice including:\n"
        f"1. Region champion pick with reasoning\n"
        f"2. Best upset picks for this region\n"
        f"3. Sleeper teams to watch\n"
        f"4. Key first-round matchups\n"
        f"5. Common bracket mistakes to avoid"
    )

    resp = await ai.complete(prompt)
    return {
        "advice": resp.text if resp.ok else None,
        "upset_radar": upsets,
        "ai_available": ai.available,
        "error": resp.error,
    }


@app.post("/v1/ai/chat")
async def ai_chat(req: AIAnalysisRequest):
    prompt = req.question or "Provide your top March Madness predictions and bracket strategy."
    resp = await ai.complete(prompt)
    return {
        "response": resp.text if resp.ok else None,
        "ai_available": ai.available,
        "error": resp.error,
    }


# ── WebSocket: Live Bracket Updates ─────────────────────────────────────────

@app.websocket("/ws/bracket-live")
async def bracket_live(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_json({
            "type": "connected",
            "data": {"regions": REGIONS, "teams": len(TEAMS)},
        })
        while True:
            msg = await ws.receive_json()
            action = msg.get("action", "")

            if action == "simulate":
                region = msg.get("region", "East")
                runs = min(msg.get("runs", 5000), 50000)
                results = simulate_bracket(region, runs=runs)
                await ws.send_json({"type": "simulation", "region": region, "data": results})

            elif action == "matchup":
                team_a = msg.get("team_a", "")
                team_b = msg.get("team_b", "")
                result = predict_matchup(team_a, team_b)
                if result:
                    await ws.send_json({"type": "matchup", "data": asdict(result)})
                else:
                    await ws.send_json({"type": "error", "data": "Teams not found"})

            elif action == "upsets":
                upsets = upset_radar(msg.get("top_n", 10))
                await ws.send_json({"type": "upsets", "data": upsets})

            elif action == "conference":
                rankings = conference_strength()
                await ws.send_json({"type": "conference", "data": rankings})

    except WebSocketDisconnect:
        pass
