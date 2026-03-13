from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from server.analysis import AnalysisEngine
from server.live_game import LiveGameManager
from server.teams import NFL_TEAMS, TEAM_STATS, get_team, get_divisions

app = FastAPI(
    title="NFL PlayCaller API",
    description="AI Offensive Coordinator Intelligence — powered by Kwyre local inference",
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
        "kwyre_endpoint": engine.kwyre_url,
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
        return {"error": f"Team '{abbr}' not found"}, 404
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
