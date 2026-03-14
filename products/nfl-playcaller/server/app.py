from __future__ import annotations

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analysis import AnalysisEngine
from .live_game import LiveGameManager
from .teams import NFL_TEAMS, TEAM_STATS, get_team, get_divisions
from products._shared.analytics import win_probability, confidence_interval, monte_carlo_forecast
from products._shared.ai_engine import AIEngine

app = FastAPI(
    title="NFL PlayCaller API",
    description="AI Offensive Coordinator Intelligence — powered by Claude",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AnalysisEngine()
game_manager = LiveGameManager(engine)
predictor_ai = AIEngine(default_system="You are an elite NFL analytics AI specializing in play prediction, formation analysis, and game theory. Analyze formations, personnel, tendencies, and micro-movements to predict plays with probability distributions.")


# ── Request / Response Models ──────────────────────────────────────────────────

class ScoutingRequest(BaseModel):
    offense: str = Field(..., description="Offensive team abbreviation (e.g. KC)")
    defense: str = Field(..., description="Defensive team abbreviation (e.g. SF)")
    notes: str = ""

class PlaycallRequest(BaseModel):
    offense: str
    defense: str
    down: str = ""
    distance: str = ""
    field_position: str = ""
    quarter: str = ""
    score: str = ""
    defensive_look: str = ""
    notes: str = ""

class BlitzRequest(BaseModel):
    offense: str
    defense: str
    down: str = ""
    distance: str = ""
    field_position: str = ""
    quarter: str = ""
    score: str = ""
    defensive_look: str = ""
    notes: str = ""

class PlayerRequest(BaseModel):
    offense: str
    defense: str
    player_name: str
    notes: str = ""

class PlaybookRequest(BaseModel):
    offense: str
    defense: str
    notes: str = ""

class PostgameRequest(BaseModel):
    offense: str
    defense: str
    notes: str = ""

class AnalysisResponse(BaseModel):
    analysis_type: str
    offense: str
    defense: str
    result: str


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "nfl-playcaller",
        "version": "1.0.0",
        "ai_available": predictor_ai.available,
        "teams_loaded": len(NFL_TEAMS),
        "live_game_active": game_manager._running,
        "ws_connections": len(game_manager.connections),
    }


# ── Teams ──────────────────────────────────────────────────────────────────────

@app.get("/v1/teams")
async def list_teams():
    return {"teams": NFL_TEAMS}

@app.get("/v1/teams/{abbr}")
async def get_team_detail(abbr: str):
    team = get_team(abbr.upper())
    if not team:
        raise HTTPException(status_code=404, detail=f"Team '{abbr}' not found")
    stats = TEAM_STATS.get(abbr.upper(), {})
    return {"team": team, "stats": stats}

@app.get("/v1/divisions")
async def list_divisions():
    return {"divisions": get_divisions()}


# ── Analysis Endpoints ─────────────────────────────────────────────────────────

@app.post("/v1/analysis/scouting", response_model=AnalysisResponse)
async def analysis_scouting(req: ScoutingRequest):
    result = await engine.run("scouting", req.model_dump())
    return AnalysisResponse(analysis_type="scouting", offense=req.offense, defense=req.defense, result=result)

@app.post("/v1/analysis/playcall", response_model=AnalysisResponse)
async def analysis_playcall(req: PlaycallRequest):
    result = await engine.run("playcall", req.model_dump())
    return AnalysisResponse(analysis_type="playcall", offense=req.offense, defense=req.defense, result=result)

@app.post("/v1/analysis/blitz", response_model=AnalysisResponse)
async def analysis_blitz(req: BlitzRequest):
    result = await engine.run("blitz", req.model_dump())
    return AnalysisResponse(analysis_type="blitz", offense=req.offense, defense=req.defense, result=result)

@app.post("/v1/analysis/player", response_model=AnalysisResponse)
async def analysis_player(req: PlayerRequest):
    result = await engine.run("player", req.model_dump())
    return AnalysisResponse(analysis_type="player", offense=req.offense, defense=req.defense, result=result)

@app.post("/v1/analysis/playbook", response_model=AnalysisResponse)
async def analysis_playbook(req: PlaybookRequest):
    result = await engine.run("playbook", req.model_dump())
    return AnalysisResponse(analysis_type="playbook", offense=req.offense, defense=req.defense, result=result)

@app.post("/v1/analysis/postgame", response_model=AnalysisResponse)
async def analysis_postgame(req: PostgameRequest):
    result = await engine.run("postgame", req.model_dump())
    return AnalysisResponse(analysis_type="postgame", offense=req.offense, defense=req.defense, result=result)


# ── Predictive Analytics Models ────────────────────────────────────────────

FORMATION_TENDENCIES = {
    "Shotgun": {"pass": 0.65, "run": 0.20, "screen": 0.08, "play_action": 0.07},
    "Under Center": {"pass": 0.30, "run": 0.45, "screen": 0.05, "play_action": 0.20},
    "Pistol": {"pass": 0.40, "run": 0.35, "screen": 0.05, "play_action": 0.20},
    "I-Formation": {"pass": 0.25, "run": 0.50, "screen": 0.03, "play_action": 0.22},
    "Singleback": {"pass": 0.50, "run": 0.28, "screen": 0.10, "play_action": 0.12},
    "Empty": {"pass": 0.82, "run": 0.03, "screen": 0.12, "play_action": 0.03},
    "Wildcat": {"pass": 0.10, "run": 0.80, "screen": 0.02, "play_action": 0.08},
    "Trips": {"pass": 0.72, "run": 0.12, "screen": 0.10, "play_action": 0.06},
    "Bunch": {"pass": 0.68, "run": 0.10, "screen": 0.14, "play_action": 0.08},
    "Jumbo": {"pass": 0.10, "run": 0.75, "screen": 0.02, "play_action": 0.13},
    "Goal Line": {"pass": 0.20, "run": 0.65, "screen": 0.02, "play_action": 0.13},
    "Spread": {"pass": 0.70, "run": 0.15, "screen": 0.08, "play_action": 0.07},
}


class PlayPredictionRequest(BaseModel):
    offense: str
    defense: str
    formation: str = "Shotgun"
    down: str = ""
    distance: str = ""
    field_position: str = ""
    quarter: str = ""
    score: str = ""
    notes: str = ""


class FormationAnalysisRequest(BaseModel):
    formation: str
    personnel: str = ""
    offense: str = ""
    notes: str = ""


class WinProbabilityRequest(BaseModel):
    home_score: int
    away_score: int
    quarter: str = "Q1"
    clock: str = "15:00"
    possession: str = "home"


class TrendAnalysisRequest(BaseModel):
    offense: str
    defense: str
    plays: list[dict] = Field(default_factory=list)
    notes: str = ""


def _parse_clock_to_seconds(quarter: str, clock: str) -> int:
    qtr_map = {"Q1": 4, "Q2": 3, "Q3": 2, "Q4": 1, "OT": 0}
    remaining_quarters = qtr_map.get(quarter, 1)
    parts = clock.split(":")
    minutes = int(parts[0]) if parts else 0
    seconds = int(parts[1]) if len(parts) > 1 else 0
    return remaining_quarters * 900 + minutes * 60 + seconds


def _situation_modifier(down: str, distance: str, field_position: str) -> dict[str, float]:
    """Adjust play-type probabilities based on game situation."""
    mods = {"pass": 0.0, "run": 0.0, "screen": 0.0, "play_action": 0.0}

    if down == "3rd":
        try:
            dist = int(distance) if distance and distance != "Goal" else 5
        except ValueError:
            dist = 5
        if dist >= 8:
            mods["pass"] += 0.20
            mods["run"] -= 0.15
            mods["screen"] += 0.05
        elif dist <= 2:
            mods["run"] += 0.15
            mods["pass"] -= 0.10
    elif down == "1st":
        mods["play_action"] += 0.05
    elif down == "4th":
        mods["pass"] += 0.15
        mods["run"] -= 0.10

    if field_position:
        if "Opp" in field_position:
            try:
                yd = int(field_position.replace("Opp ", ""))
                if yd <= 5:
                    mods["run"] += 0.15
                    mods["pass"] -= 0.10
            except ValueError:
                pass

    return mods


# ── Predictive Analytics Endpoints ────────────────────────────────────────

@app.post("/v1/predict/play")
async def predict_play(req: PlayPredictionRequest):
    base = FORMATION_TENDENCIES.get(req.formation, FORMATION_TENDENCIES["Shotgun"]).copy()
    mods = _situation_modifier(req.down, req.distance, req.field_position)

    for k in base:
        base[k] = max(0.0, base[k] + mods.get(k, 0.0))
    total = sum(base.values())
    if total > 0:
        base = {k: round(v / total, 4) for k, v in base.items()}

    predicted = max(base, key=base.get)

    prompt = (
        f"Offense: {req.offense}, Defense: {req.defense}\n"
        f"Formation: {req.formation}, Down: {req.down}, Distance: {req.distance}\n"
        f"Field Position: {req.field_position}, Quarter: {req.quarter}, Score: {req.score}\n"
        f"Statistical model predicts: {predicted} (probabilities: {base})\n"
        f"Additional notes: {req.notes}\n\n"
        "Provide a concise play prediction with reasoning. Include the most likely "
        "specific play call, key players to watch, and defensive counter."
    )
    ai_resp = await predictor_ai.complete(prompt)

    return {
        "prediction": predicted,
        "probabilities": base,
        "formation": req.formation,
        "situation": {"down": req.down, "distance": req.distance, "field_position": req.field_position},
        "ai_analysis": ai_resp.text if ai_resp.ok else None,
        "ai_error": ai_resp.error,
    }


@app.post("/v1/predict/formation")
async def predict_formation(req: FormationAnalysisRequest):
    tendencies = FORMATION_TENDENCIES.get(req.formation, None)
    if not tendencies:
        return {"error": f"Unknown formation: {req.formation}", "available": list(FORMATION_TENDENCIES.keys())}

    prompt = (
        f"Formation: {req.formation}, Personnel: {req.personnel or 'Standard'}\n"
        f"Offense: {req.offense or 'Generic'}\n"
        f"Notes: {req.notes}\n\n"
        "Analyze this formation's alignment. Detail receiver splits, backfield alignment, "
        "tight end positioning, and typical route trees. Predict play type probabilities "
        "and identify defensive vulnerabilities."
    )
    ai_resp = await predictor_ai.complete(prompt)

    return {
        "formation": req.formation,
        "tendencies": tendencies,
        "primary_threat": max(tendencies, key=tendencies.get),
        "ai_analysis": ai_resp.text if ai_resp.ok else None,
        "ai_error": ai_resp.error,
    }


@app.post("/v1/analytics/win-probability")
async def calc_win_probability(req: WinProbabilityRequest):
    diff = req.home_score - req.away_score
    time_left = _parse_clock_to_seconds(req.quarter, req.clock)
    has_possession = req.possession == "home"

    home_wp = win_probability(diff, time_left, possession=has_possession, sport="nfl")
    away_wp = round(1.0 - home_wp, 4)

    return {
        "home_win_probability": home_wp,
        "away_win_probability": away_wp,
        "score_differential": diff,
        "time_remaining_seconds": time_left,
        "possession": req.possession,
        "quarter": req.quarter,
        "clock": req.clock,
    }


@app.post("/v1/analytics/trends")
async def analyze_trends(req: TrendAnalysisRequest):
    play_types = {"run": 0, "pass": 0, "screen": 0, "play_action": 0, "other": 0}
    quarter_breakdown: dict[str, dict[str, int]] = {}
    down_breakdown: dict[str, dict[str, int]] = {}

    for play in req.plays:
        ptype = play.get("type", "other").lower()
        if ptype not in play_types:
            ptype = "other"
        play_types[ptype] += 1

        qtr = play.get("quarter", "Q1")
        quarter_breakdown.setdefault(qtr, {"run": 0, "pass": 0, "screen": 0, "play_action": 0, "other": 0})
        quarter_breakdown[qtr][ptype] += 1

        dn = play.get("down", "")
        if dn:
            down_breakdown.setdefault(dn, {"run": 0, "pass": 0, "screen": 0, "play_action": 0, "other": 0})
            down_breakdown[dn][ptype] += 1

    total = sum(play_types.values())
    percentages = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in play_types.items()}

    prompt = (
        f"Offense: {req.offense}, Defense: {req.defense}\n"
        f"Play distribution: {play_types}\n"
        f"Quarter breakdown: {quarter_breakdown}\n"
        f"Down breakdown: {down_breakdown}\n"
        f"Notes: {req.notes}\n\n"
        "Analyze the play-calling trends. Identify tendencies, predictability, "
        "and suggest adjustments the defense/offense should make."
    )
    ai_resp = await predictor_ai.complete(prompt)

    return {
        "total_plays": total,
        "play_types": play_types,
        "percentages": percentages,
        "by_quarter": quarter_breakdown,
        "by_down": down_breakdown,
        "ai_analysis": ai_resp.text if ai_resp.ok else None,
        "ai_error": ai_resp.error,
    }


# ── WebSocket: Live Game ───────────────────────────────────────────────────────

@app.websocket("/ws/live-game")
async def ws_live_game(ws: WebSocket):
    await game_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "data": "Invalid JSON"})
                continue

            action = msg.get("action")

            if action == "start":
                home = msg.get("home", "KC")
                away = msg.get("away", "SF")
                await game_manager.start_demo(home, away)

            elif action == "stop":
                await game_manager.stop_demo()

            elif action == "status":
                await ws.send_json({"type": "state", "data": game_manager.get_situation()})

            elif action == "suggest":
                suggestion = await game_manager.auto_suggest_play()
                await ws.send_json({
                    "type": "suggestion",
                    "data": {"text": suggestion, "situation": game_manager.state.situation_str},
                })

            else:
                await ws.send_json({"type": "error", "data": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        game_manager.disconnect(ws)
