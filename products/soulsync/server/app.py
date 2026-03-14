"""
SoulSync API — FastAPI application with REST endpoints and WebSocket chat.
"""

from __future__ import annotations

import sys
import os
import uuid
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from products._shared.ai_engine import AIEngine

from .icebreaker import IcebreakerGenerator, generate_coaching_advice
from .matching import MatchingEngine
from .personality import PersonalityEngine, PersonalityProfile

app = FastAPI(
    title="SoulSync API",
    description="AI-Powered Soulmate Matching Platform",
    version="0.1.0",
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
        "You are SoulSync AI, a compassionate relationship intelligence system. "
        "Provide thoughtful compatibility insights, personalized conversation starters, "
        "and emotionally intelligent dating advice. Be warm, specific, and encouraging "
        "while being realistic about compatibility challenges."
    )
)

personality_engine = PersonalityEngine()
matching_engine = MatchingEngine()
icebreaker_generator = IcebreakerGenerator()

# In-memory stores (swap for a real DB in production)
profiles_db: dict[str, dict[str, Any]] = {}
profile_objects: dict[str, PersonalityProfile] = {}


# ── Request / Response Models ──────────────────────────────────────────


class ProfileCreateRequest(BaseModel):
    user_id: str | None = None
    answers: dict[str, float] = Field(..., description="Questionnaire answers (key→1-5 Likert)")
    interests: list[str] = Field(default_factory=list)
    deal_breakers: dict[str, Any] = Field(default_factory=dict)


class ProfileAnalyzeRequest(BaseModel):
    user_id: str


class MatchScoreRequest(BaseModel):
    user_id_a: str
    user_id_b: str


class MatchFindRequest(BaseModel):
    user_id: str
    limit: int = Field(default=10, ge=1, le=50)


class IcebreakerRequest(BaseModel):
    user_id_a: str
    user_id_b: str
    count: int = Field(default=5, ge=1, le=10)


class CoachingRequest(BaseModel):
    user_id_a: str
    user_id_b: str


# ── Endpoints ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "soulsync",
        "version": "0.1.0",
        "profiles_count": len(profiles_db),
    }


@app.post("/v1/profile/create")
async def create_profile(req: ProfileCreateRequest):
    user_id = req.user_id or str(uuid.uuid4())

    profile = personality_engine.create_profile(
        user_id=user_id,
        answers=req.answers,
        interests=req.interests,
        deal_breakers=req.deal_breakers,
    )

    profile_data = profile.to_dict()
    profiles_db[user_id] = profile_data
    profile_objects[user_id] = profile

    return {
        "user_id": user_id,
        "profile": profile_data,
        "message": "Profile created successfully",
    }


@app.post("/v1/profile/analyze")
async def analyze_profile(req: ProfileAnalyzeRequest):
    if req.user_id not in profile_objects:
        raise HTTPException(status_code=404, detail=f"Profile '{req.user_id}' not found")

    profile = profile_objects[req.user_id]
    analysis = personality_engine.analyze_profile(profile)
    return {"user_id": req.user_id, "analysis": analysis}


@app.post("/v1/match/score")
async def match_score(req: MatchScoreRequest):
    for uid in [req.user_id_a, req.user_id_b]:
        if uid not in profile_objects:
            raise HTTPException(status_code=404, detail=f"Profile '{uid}' not found")

    result = matching_engine.compute_compatibility(
        profile_objects[req.user_id_a],
        profile_objects[req.user_id_b],
    )
    return {
        "user_id_a": req.user_id_a,
        "user_id_b": req.user_id_b,
        "compatibility": result.to_dict(),
    }


@app.post("/v1/match/find")
async def match_find(req: MatchFindRequest):
    if req.user_id not in profile_objects:
        raise HTTPException(status_code=404, detail=f"Profile '{req.user_id}' not found")

    pool = list(profile_objects.values())
    top = matching_engine.find_top_matches(profile_objects[req.user_id], pool, limit=req.limit)
    return {"user_id": req.user_id, "matches": top, "pool_size": len(pool) - 1}


@app.post("/v1/icebreaker/generate")
async def generate_icebreakers(req: IcebreakerRequest):
    for uid in [req.user_id_a, req.user_id_b]:
        if uid not in profile_objects:
            raise HTTPException(status_code=404, detail=f"Profile '{uid}' not found")

    starters = icebreaker_generator.generate(
        profile_objects[req.user_id_a],
        profile_objects[req.user_id_b],
        count=req.count,
    )
    return {
        "user_id_a": req.user_id_a,
        "user_id_b": req.user_id_b,
        "icebreakers": starters,
    }


@app.post("/v1/coaching/advice")
async def coaching_advice(req: CoachingRequest):
    for uid in [req.user_id_a, req.user_id_b]:
        if uid not in profile_objects:
            raise HTTPException(status_code=404, detail=f"Profile '{uid}' not found")

    compatibility = matching_engine.compute_compatibility(
        profile_objects[req.user_id_a],
        profile_objects[req.user_id_b],
    )
    tips = generate_coaching_advice(
        profile_objects[req.user_id_a],
        profile_objects[req.user_id_b],
        compatibility.to_dict(),
    )
    return {
        "user_id_a": req.user_id_a,
        "user_id_b": req.user_id_b,
        "overall_score": round(compatibility.overall_score, 1),
        "advice": tips,
    }


# ── AI-Powered Endpoints ───────────────────────────────────────────────


class AICompatibilityRequest(BaseModel):
    profile_a: dict = Field(..., description="First user profile data")
    profile_b: dict = Field(..., description="Second user profile data")

class AIIcebreakerRequest(BaseModel):
    profile: dict = Field(..., description="Target match profile")
    your_interests: list[str] = Field(default_factory=list)
    count: int = Field(5, ge=1, le=10)

class AIDatingCoachRequest(BaseModel):
    profile: dict = Field(default_factory=dict)
    situation: str = Field(..., min_length=10)
    relationship_stage: str = Field("early", description="early, dating, committed, complicated")

class AIPersonalityRequest(BaseModel):
    traits: dict[str, float] = Field(..., description="Big Five trait scores (0-1)")
    interests: list[str] = Field(default_factory=list)

class AIMessageHelperRequest(BaseModel):
    match_profile: dict = Field(default_factory=dict)
    conversation_history: list[str] = Field(default_factory=list)
    intent: str = Field("flirty", description="flirty, funny, deep, casual, romantic")


@app.post("/v1/ai/compatibility-analysis")
async def ai_compatibility(req: AICompatibilityRequest):
    prompt = (
        f"Analyze the deep compatibility between these two dating profiles.\n\n"
        f"Profile A: {req.profile_a}\n\n"
        f"Profile B: {req.profile_b}\n\n"
        "Provide:\n"
        "1. Overall compatibility assessment\n"
        "2. Strongest connection points\n"
        "3. Potential friction areas\n"
        "4. Communication style compatibility\n"
        "5. Long-term potential analysis\n"
        "6. Advice for building connection"
    )
    resp = await ai.complete(prompt, temperature=0.7)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"analysis": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/icebreakers")
async def ai_icebreakers(req: AIIcebreakerRequest):
    prompt = (
        f"Generate {req.count} personalized, creative conversation starters for a dating match.\n\n"
        f"Their Profile: {req.profile}\n"
        f"Your Interests: {', '.join(req.your_interests) if req.your_interests else 'General'}\n\n"
        "Make each opener unique, specific to their profile, and inviting a genuine response. "
        "Mix humor, curiosity, and warmth. Avoid generic lines."
    )
    resp = await ai.complete(prompt, temperature=0.8)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"icebreakers": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/dating-coach")
async def ai_dating_coach(req: AIDatingCoachRequest):
    prompt = (
        f"Provide empathetic, actionable dating advice for this situation.\n\n"
        f"Profile: {req.profile}\n"
        f"Relationship Stage: {req.relationship_stage}\n"
        f"Situation: {req.situation}\n\n"
        "Be warm and specific. Provide practical next steps, communication tips, "
        "and emotional intelligence insights."
    )
    resp = await ai.complete(prompt, temperature=0.7)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"advice": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/personality-insights")
async def ai_personality_insights(req: AIPersonalityRequest):
    traits_str = ", ".join(f"{k}: {v:.2f}" for k, v in req.traits.items())
    prompt = (
        f"Provide a rich personality analysis and growth insights for dating.\n\n"
        f"Big Five Traits: {traits_str}\n"
        f"Interests: {', '.join(req.interests) if req.interests else 'Not specified'}\n\n"
        "Include:\n"
        "1. Personality summary and dating style\n"
        "2. Strengths in relationships\n"
        "3. Growth areas\n"
        "4. Ideal partner characteristics\n"
        "5. Communication tips based on personality"
    )
    resp = await ai.complete(prompt, temperature=0.7)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"insights": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/message-helper")
async def ai_message_helper(req: AIMessageHelperRequest):
    history = "\n".join(req.conversation_history[-10:]) if req.conversation_history else "No prior messages"
    prompt = (
        f"Help craft a great message to send to a dating match.\n\n"
        f"Match Profile: {req.match_profile}\n"
        f"Conversation So Far:\n{history}\n"
        f"Desired Tone: {req.intent}\n\n"
        "Suggest 3 message options that feel natural and engaging. "
        "Each should be different in approach but match the desired tone."
    )
    resp = await ai.complete(prompt, temperature=0.8)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"suggestions": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


# ── WebSocket Chat ─────────────────────────────────────────────────────


class ConnectionManager:
    """Manages WebSocket connections grouped by match-pair rooms."""

    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = defaultdict(list)
        self.user_rooms: dict[str, str] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        await websocket.accept()
        self.rooms[room_id].append(websocket)
        self.user_rooms[user_id] = room_id

    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        if websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
        self.user_rooms.pop(user_id, None)
        if not self.rooms[room_id]:
            del self.rooms[room_id]

    async def broadcast(self, room_id: str, message: dict[str, Any], exclude: WebSocket | None = None):
        for ws in self.rooms.get(room_id, []):
            if ws is not exclude:
                await ws.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket chat for matched pairs.
    Client sends initial message: {"action": "join", "room_id": "...", "user_id": "..."}
    Then sends messages: {"action": "message", "text": "..."}
    """
    room_id: str | None = None
    user_id: str | None = None

    try:
        await websocket.accept()
        join_data = await websocket.receive_json()

        if join_data.get("action") != "join" or not join_data.get("room_id") or not join_data.get("user_id"):
            await websocket.send_json({"error": "First message must be: {action: 'join', room_id, user_id}"})
            await websocket.close()
            return

        room_id = join_data["room_id"]
        user_id = join_data["user_id"]
        manager.rooms[room_id].append(websocket)
        manager.user_rooms[user_id] = room_id

        await manager.broadcast(
            room_id,
            {"type": "system", "text": f"{user_id} joined the chat"},
            exclude=websocket,
        )
        await websocket.send_json({"type": "system", "text": f"Connected to room {room_id}"})

        while True:
            data = await websocket.receive_json()
            if data.get("action") == "message" and "text" in data:
                await manager.broadcast(
                    room_id,
                    {"type": "message", "user_id": user_id, "text": data["text"]},
                )

    except WebSocketDisconnect:
        if room_id and user_id:
            manager.disconnect(websocket, room_id, user_id)
            await manager.broadcast(
                room_id,
                {"type": "system", "text": f"{user_id} left the chat"},
            )
