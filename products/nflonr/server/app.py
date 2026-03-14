"""
NFLonr — Pre-Snap Intelligence Platform API

FastAPI backend for play prediction, formation analysis, micro-read detection,
tendency scoring, and AI-powered game breakdowns.
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from products._shared.ai_engine import AIEngine
from products._shared.analytics import win_probability, confidence_interval

from server.formations import (
    get_formation,
    search_formations,
    formation_tendencies,
    list_all_formations,
    formations_by_tag,
    formations_by_personnel,
    FORMATIONS,
)
from server.predictions import (
    predict_play,
    analyze_formation,
    team_tendencies,
    analyze_micro_reads,
    MICRO_READ_CATEGORIES,
    TEAM_TENDENCY_PROFILES,
)

app = FastAPI(
    title="NFLonr API",
    description="Pre-Snap Intelligence Platform — AI play prediction, formation analysis, and micro-read detection",
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
        "You are an elite NFL pre-snap intelligence analyst. You specialize in "
        "reading formations, detecting pre-snap tells, predicting plays before "
        "the snap, and analyzing offensive/defensive tendencies. You think in "
        "terms of probability distributions, personnel groupings, alignment "
        "keys, and micro-aggressions (stance tells, weight shifts, eye patterns, "
        "hand placement). Be precise, data-driven, and actionable."
    )
)

ws_connections: list[WebSocket] = []


# ── Request Models ────────────────────────────────────────────────────────

class PlayPredictRequest(BaseModel):
    formation: str = "Shotgun Spread"
    offense: str = ""
    defense: str = ""
    down: str = ""
    distance: str = ""
    field_position: str = ""
    quarter: str = ""
    score_diff: int = 0
    notes: str = ""


class FormationPredictRequest(BaseModel):
    formation: str
    personnel: str = ""
    offense: str = ""
    notes: str = ""


class MicroReadRequest(BaseModel):
    formation: str = ""
    categories: list[str] = Field(default_factory=list)
    notes: str = ""


class TendencyRequest(BaseModel):
    team: str
    opponent: str = ""
    situation: str = ""
    notes: str = ""


class AIBreakdownRequest(BaseModel):
    offense: str
    defense: str
    formation: str = ""
    down: str = ""
    distance: str = ""
    field_position: str = ""
    quarter: str = ""
    score: str = ""
    context: str = ""


# ── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "nflonr",
        "version": "1.0.0",
        "formations_loaded": len(FORMATIONS),
        "teams_with_profiles": len(TEAM_TENDENCY_PROFILES),
        "micro_read_categories": len(MICRO_READ_CATEGORIES),
        "ai_available": ai.available,
        "ws_connections": len(ws_connections),
    }


# ── Play Prediction ──────────────────────────────────────────────────────

@app.post("/v1/predict/play")
async def predict_play_endpoint(req: PlayPredictRequest):
    prediction = predict_play(
        formation_name=req.formation,
        offense=req.offense,
        down=req.down,
        distance=req.distance,
        field_position=req.field_position,
        quarter=req.quarter,
        score_diff=req.score_diff,
    )

    ai_analysis = None
    ai_error = None
    if req.offense and req.defense:
        prompt = (
            f"Formation: {prediction.formation}\n"
            f"Offense: {req.offense}, Defense: {req.defense}\n"
            f"Down: {req.down}, Distance: {req.distance}, Field: {req.field_position}\n"
            f"Quarter: {req.quarter}, Score diff: {req.score_diff}\n"
            f"Model prediction: {prediction.predicted_play} ({prediction.probabilities})\n"
            f"Micro-reads detected: {len(prediction.micro_reads)}\n"
            f"Notes: {req.notes}\n\n"
            "Give a concise pre-snap read: what play is likely, why, and what "
            "the defense should key on. Include specific player matchups to watch."
        )
        resp = await ai.complete(prompt)
        ai_analysis = resp.text if resp.ok else None
        ai_error = resp.error

    return {
        "predicted_play": prediction.predicted_play,
        "probabilities": prediction.probabilities,
        "confidence": prediction.confidence,
        "formation": prediction.formation,
        "situation": prediction.situation_factors,
        "micro_reads": [
            {
                "category": mr.category,
                "indicator": mr.indicator,
                "confidence": mr.confidence,
                "lean": mr.play_lean,
                "description": mr.description,
            }
            for mr in prediction.micro_reads
        ],
        "reasoning": prediction.reasoning,
        "ai_analysis": ai_analysis,
        "ai_error": ai_error,
    }


# ── Formation Analysis ───────────────────────────────────────────────────

@app.post("/v1/predict/formation")
async def predict_formation_endpoint(req: FormationPredictRequest):
    analysis = analyze_formation(req.formation)

    if not analysis:
        matches = search_formations(req.formation)
        return {
            "error": f"Formation '{req.formation}' not found",
            "suggestions": [f.name for f in matches[:10]],
            "total_formations": len(FORMATIONS),
        }

    ai_analysis = None
    ai_error = None
    prompt = (
        f"Formation: {analysis['formation']} ({analysis['personnel']} personnel)\n"
        f"Alignment: {analysis['alignment']}\n"
        f"Tendencies: {analysis['tendencies']}\n"
        f"Primary threat: {analysis['primary_threat']} ({analysis['primary_threat_pct']:.0%})\n"
        f"Tags: {analysis['tags']}\n"
        f"Offense: {req.offense or 'Generic'}\n"
        f"Notes: {req.notes}\n\n"
        "Analyze this formation in depth. Cover receiver splits, backfield "
        "alignment, route tree tendencies, run scheme fit, defensive counters, "
        "and key pre-snap indicators to watch."
    )
    resp = await ai.complete(prompt)
    ai_analysis = resp.text if resp.ok else None
    ai_error = resp.error

    return {
        **analysis,
        "ai_analysis": ai_analysis,
        "ai_error": ai_error,
    }


# ── Micro-Read Analysis ──────────────────────────────────────────────────

@app.post("/v1/analyze/micro-reads")
async def analyze_micro_reads_endpoint(req: MicroReadRequest):
    cats = req.categories if req.categories else None
    result = analyze_micro_reads(formation_name=req.formation, categories=cats)

    ai_analysis = None
    ai_error = None
    if req.formation:
        detected = [
            ind for cat in result["categories"].values()
            for ind in cat["indicators"]
            if ind["detected"]
        ]
        prompt = (
            f"Formation: {req.formation}\n"
            f"Detected pre-snap tells:\n"
            + "\n".join(f"- {d['description']} (lean: {d['lean']}, conf: {d['confidence']:.0%})" for d in detected[:8])
            + f"\n\nOverall lean: {result['summary']['overall_lean']}\n"
            f"Notes: {req.notes}\n\n"
            "Interpret these micro-reads. What do they collectively suggest? "
            "How reliable are these tells? What should the defense do?"
        )
        resp = await ai.complete(prompt)
        ai_analysis = resp.text if resp.ok else None
        ai_error = resp.error

    return {
        **result,
        "formation": req.formation,
        "ai_analysis": ai_analysis,
        "ai_error": ai_error,
    }


# ── Tendency Analysis ─────────────────────────────────────────────────────

@app.post("/v1/analyze/tendencies")
async def analyze_tendencies_endpoint(req: TendencyRequest):
    score = team_tendencies(req.team)

    opponent_score = None
    if req.opponent:
        opponent_score = team_tendencies(req.opponent)

    ai_analysis = None
    ai_error = None
    prompt = (
        f"Team: {score.team}\n"
        f"Run rate: {score.run_rate:.1%}, Pass rate: {score.pass_rate:.1%}\n"
        f"Screen rate: {score.screen_rate:.1%}, PA rate: {score.play_action_rate:.1%}\n"
        f"Aggressiveness: {score.aggressiveness:.1%}, Predictability: {score.predictability:.1%}\n"
    )
    if opponent_score:
        prompt += (
            f"\nOpponent: {opponent_score.team}\n"
            f"Opp run rate: {opponent_score.run_rate:.1%}, Opp pass rate: {opponent_score.pass_rate:.1%}\n"
        )
    prompt += (
        f"Situation: {req.situation}\n"
        f"Notes: {req.notes}\n\n"
        "Analyze these tendencies. What patterns are exploitable? "
        "How predictable is this offense? What defensive adjustments "
        "should be made based on these tendencies?"
    )
    resp = await ai.complete(prompt)
    ai_analysis = resp.text if resp.ok else None
    ai_error = resp.error

    result = {
        "team": asdict(score),
        "ai_analysis": ai_analysis,
        "ai_error": ai_error,
    }
    if opponent_score:
        result["opponent"] = asdict(opponent_score)

    return result


# ── AI Breakdown ──────────────────────────────────────────────────────────

@app.post("/v1/ai/breakdown")
async def ai_breakdown_endpoint(req: AIBreakdownRequest):
    context_parts = []
    if req.formation:
        form_data = analyze_formation(req.formation)
        if form_data:
            context_parts.append(f"Formation: {form_data['formation']} ({form_data['personnel']})")
            context_parts.append(f"Alignment: {form_data['alignment']}")
            context_parts.append(f"Tendencies: Run {form_data['tendencies']['run']:.0%}, Pass {form_data['tendencies']['pass']:.0%}")

    if req.offense:
        off_tend = team_tendencies(req.offense)
        context_parts.append(f"Offense ({off_tend.team}): Run {off_tend.run_rate:.0%}, Pass {off_tend.pass_rate:.0%}, Aggression {off_tend.aggressiveness:.0%}")

    if req.defense:
        def_tend = team_tendencies(req.defense)
        context_parts.append(f"Defense ({def_tend.team}): Facing run {def_tend.run_rate:.0%}, pass {def_tend.pass_rate:.0%}")

    prompt = (
        f"GAME BREAKDOWN REQUEST\n"
        f"Offense: {req.offense} vs Defense: {req.defense}\n"
        f"Formation: {req.formation or 'Not specified'}\n"
        f"Situation: {req.down} & {req.distance}, {req.field_position}, {req.quarter}\n"
        f"Score: {req.score}\n"
        f"\nAnalytical Context:\n" + "\n".join(f"- {c}" for c in context_parts) +
        f"\n\nAdditional context: {req.context}\n\n"
        "Provide a comprehensive game breakdown covering:\n"
        "1. Offensive scheme analysis and likely game plan\n"
        "2. Defensive alignment and coverage tendencies\n"
        "3. Key matchups to watch\n"
        "4. Play prediction with probability reasoning\n"
        "5. Tactical adjustments recommended for both sides"
    )

    resp = await ai.complete(prompt, max_tokens=6000)

    return {
        "offense": req.offense,
        "defense": req.defense,
        "formation": req.formation,
        "situation": {"down": req.down, "distance": req.distance, "field_position": req.field_position, "quarter": req.quarter},
        "breakdown": resp.text if resp.ok else None,
        "error": resp.error,
        "context_data": context_parts,
    }


# ── WebSocket: Live Predictions ───────────────────────────────────────────

@app.websocket("/ws/live-predictions")
async def ws_live_predictions(ws: WebSocket):
    await ws.accept()
    ws_connections.append(ws)
    try:
        await ws.send_json({"type": "connected", "formations": len(FORMATIONS)})
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")

            if action == "predict":
                prediction = predict_play(
                    formation_name=msg.get("formation", "Shotgun Spread"),
                    offense=msg.get("offense", ""),
                    down=msg.get("down", ""),
                    distance=msg.get("distance", ""),
                    field_position=msg.get("field_position", ""),
                    quarter=msg.get("quarter", ""),
                    score_diff=msg.get("score_diff", 0),
                )
                await ws.send_json({
                    "type": "prediction",
                    "data": {
                        "predicted_play": prediction.predicted_play,
                        "probabilities": prediction.probabilities,
                        "confidence": prediction.confidence,
                        "formation": prediction.formation,
                        "micro_reads": [
                            {"category": mr.category, "indicator": mr.indicator,
                             "confidence": mr.confidence, "lean": mr.play_lean}
                            for mr in prediction.micro_reads
                        ],
                    },
                })

            elif action == "micro_reads":
                result = analyze_micro_reads(
                    formation_name=msg.get("formation", ""),
                    categories=msg.get("categories"),
                )
                await ws.send_json({"type": "micro_reads", "data": result})

            elif action == "tendencies":
                team = msg.get("team", "KC")
                score = team_tendencies(team)
                await ws.send_json({"type": "tendencies", "data": asdict(score)})

            elif action == "formation":
                result = analyze_formation(msg.get("formation", "Shotgun Spread"))
                await ws.send_json({"type": "formation", "data": result})

            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        ws_connections.remove(ws)
