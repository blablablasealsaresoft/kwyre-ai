from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .resume import ResumeAnalyzer
from .interview import InterviewPrep
from .matching import JobMatcher, CandidateProfile

app = FastAPI(
    title="LaunchPad API",
    description="AI-Powered Job Placement Platform — Mint Rail LLC",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ResumeAnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=20, description="Raw resume text")
    job_description: str = Field("", description="Target job description for keyword matching")

class ResumeOptimizeRequest(BaseModel):
    resume_text: str = Field(..., min_length=20)
    job_description: str = Field(..., min_length=20)

class CoverLetterRequest(BaseModel):
    resume_text: str = Field(..., min_length=20)
    job_description: str = Field(..., min_length=20)
    tone: str = Field("professional", description="Tone: professional, enthusiastic, conversational")

class InterviewPrepRequest(BaseModel):
    role: str = Field(..., description="Target role (software_engineer, product_manager, etc.)")
    company: str = Field("", description="Target company name")
    level: str = Field("mid", description="Seniority: junior, mid, senior, staff")
    count: int = Field(8, ge=1, le=20, description="Number of questions")

class JobMatchRequest(BaseModel):
    skills: list[str] = Field(..., min_length=1)
    experience_years: int = Field(0, ge=0)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_min: int = Field(0, ge=0)
    salary_max: int = Field(0, ge=0)
    preferred_industries: list[str] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=50)

class SalaryNegotiateRequest(BaseModel):
    base_salary: int = Field(..., gt=0)
    equity: str = Field("", description="Equity/stock details")
    bonus: str = Field("", description="Bonus structure")
    benefits: str = Field("", description="Benefits package")
    role: str = Field("", description="Role title")
    location: str = Field("", description="Job location")
    years_experience: int = Field(0, ge=0)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "launchpad", "version": "0.1.0"}


@app.post("/v1/resume/analyze")
async def analyze_resume(req: ResumeAnalyzeRequest):
    analyzer = ResumeAnalyzer(req.resume_text, req.job_description)
    result = analyzer.analyze()
    return {
        "ats_score": result.ats_score,
        "breakdown": {
            "keyword_match": result.breakdown.keyword_match,
            "formatting": result.breakdown.formatting,
            "achievements": result.breakdown.achievements,
            "action_verbs": result.breakdown.action_verbs,
        },
        "improvements": result.improvements,
        "missing_keywords": result.missing_keywords,
        "sections_found": result.sections_found,
    }


@app.post("/v1/resume/optimize")
async def optimize_resume(req: ResumeOptimizeRequest):
    analyzer = ResumeAnalyzer(req.resume_text, req.job_description)
    return analyzer.optimize()


@app.post("/v1/cover-letter/generate")
async def generate_cover_letter(req: CoverLetterRequest):
    analyzer = ResumeAnalyzer(req.resume_text, req.job_description)
    analysis = analyzer.analyze()
    keywords = analyzer._extract_jd_keywords()[:8]

    tone_map = {
        "professional": ("I am writing to express my interest", "I am confident", "I look forward to"),
        "enthusiastic": ("I'm thrilled to apply", "I'm passionate about", "I'd love the chance to"),
        "conversational": ("I came across this role and", "What excites me most", "I'd be happy to"),
    }
    opener, middle, closer = tone_map.get(req.tone, tone_map["professional"])

    skills_mentioned = ", ".join(keywords[:4]) if keywords else "the required skills"
    extra_skills = ", ".join(keywords[4:7]) if len(keywords) > 4 else "relevant technologies"

    sections = analysis.sections_found
    has_experience = "experience" in sections

    cover_letter = f"""Dear Hiring Manager,

{opener} in this position. With {'extensive' if has_experience else 'relevant'} experience in {skills_mentioned}, I believe I would be a strong addition to your team.

Throughout my career, I have developed deep expertise in {extra_skills}. {middle} that my background aligns well with what you're looking for. I have consistently delivered results by combining technical proficiency with a collaborative approach to problem-solving.

My resume highlights key achievements that demonstrate my ability to drive impact. I bring a track record of quantifiable results and a commitment to continuous growth.

{closer} discussing how my skills and experience can contribute to your team's success. Thank you for considering my application.

Sincerely,
[Your Name]"""

    return {
        "cover_letter": cover_letter,
        "keywords_used": keywords[:7],
        "tone": req.tone,
        "resume_score": analysis.ats_score,
    }


@app.post("/v1/interview/prepare")
async def prepare_interview(req: InterviewPrepRequest):
    prep = InterviewPrep(req.role, req.company, req.level)
    questions = prep.generate_questions(req.count)
    return {
        "role": req.role,
        "company": req.company or "(not specified)",
        "level": req.level,
        "question_count": len(questions),
        "questions": questions,
        "available_roles": InterviewPrep.get_available_roles(),
    }


@app.post("/v1/match/jobs")
async def match_jobs(req: JobMatchRequest):
    profile = CandidateProfile(
        skills=req.skills,
        experience_years=req.experience_years,
        preferred_locations=req.preferred_locations,
        salary_min=req.salary_min,
        salary_max=req.salary_max,
        preferred_industries=req.preferred_industries,
    )
    matcher = JobMatcher()
    matches = matcher.match(profile, req.limit)
    return {
        "candidate_skills": req.skills,
        "match_count": len(matches),
        "matches": matches,
    }


@app.post("/v1/salary/negotiate")
async def negotiate_salary(req: SalaryNegotiateRequest):
    base = req.base_salary
    counter_base = int(base * 1.15)
    aggressive_base = int(base * 1.25)

    strategies: list[dict] = [
        {
            "strategy": "Anchoring High",
            "description": (
                f"Counter at ${aggressive_base:,} (25% above offer). "
                f"This sets a high anchor and gives room to negotiate down to your target of ${counter_base:,}."
            ),
            "counter_amount": aggressive_base,
        },
        {
            "strategy": "Market Data",
            "description": (
                f"Research shows the market range for {req.role or 'this role'} "
                f"in {req.location or 'major markets'} is typically "
                f"${int(base * 0.9):,}–${int(base * 1.3):,}. "
                f"Position your counter of ${counter_base:,} as the market midpoint."
            ),
            "counter_amount": counter_base,
        },
        {
            "strategy": "Total Compensation",
            "description": (
                "If base salary is firm, negotiate other components: "
                "signing bonus ($10K–$25K), additional equity, flexible PTO, "
                "remote work, professional development budget, or accelerated review cycle."
            ),
            "counter_amount": base,
        },
    ]

    talking_points = [
        f"Express enthusiasm for the role before discussing compensation",
        f"Reference your {req.years_experience} years of experience as justification",
        f"Use specific market data rather than 'I feel I deserve more'",
        f"Frame the negotiation as collaborative: 'How can we close the gap?'",
        f"Have a walk-away number in mind (your BATNA) but don't reveal it",
        f"Get the final offer in writing before accepting",
    ]

    equity_notes = []
    if req.equity:
        equity_notes.append(f"Evaluate equity at a discount: assume 50–70% of stated value")
        equity_notes.append("Ask about vesting schedule, cliff period, and exercise window")
    if req.bonus:
        equity_notes.append("Clarify if bonus is guaranteed or performance-based, and typical payout percentage")

    return {
        "current_offer": {
            "base": base,
            "equity": req.equity or "none specified",
            "bonus": req.bonus or "none specified",
            "benefits": req.benefits or "none specified",
        },
        "recommended_counter": counter_base,
        "strategies": strategies,
        "talking_points": talking_points,
        "equity_notes": equity_notes,
        "confidence_level": "high" if req.years_experience >= 5 else "moderate",
    }


# ---------------------------------------------------------------------------
# WebSocket — Live interview coaching
# ---------------------------------------------------------------------------

COACHING_TIPS = {
    "tell me about yourself": (
        "Structure your answer: Present → Past → Future. "
        "30 seconds on your current role, 30 seconds on key past experience, "
        "30 seconds on why this opportunity excites you. Keep it under 2 minutes."
    ),
    "greatest weakness": (
        "Choose a real but non-critical weakness. Show self-awareness and the steps "
        "you're taking to improve. Example: 'I tend to over-prepare for presentations. "
        "I've started setting time limits for prep to be more efficient.'"
    ),
    "why should we hire you": (
        "Connect three things: your strongest relevant skill, a specific achievement "
        "that proves it, and how it directly benefits this team. Be specific, not generic."
    ),
    "where do you see yourself": (
        "Show ambition aligned with the company's growth path. "
        "Avoid 'in your chair' jokes. Focus on skill growth and increasing impact. "
        "Example: 'I want to deepen my expertise in X and eventually lead initiatives in Y.'"
    ),
    "salary expectations": (
        "Deflect early-stage: 'I'd like to learn more about the full scope of the role first.' "
        "If pressed, give a researched range: 'Based on my experience and market data, "
        "I'd expect $X–$Y, but I'm open to discussing total compensation.'"
    ),
}

DEFAULT_COACHING = (
    "Good practice! Here are general tips for this type of question: "
    "1) Use the STAR method (Situation, Task, Action, Result). "
    "2) Be specific with numbers and outcomes. "
    "3) Keep answers under 2 minutes. "
    "4) End with what you learned or the impact you made."
)


@app.websocket("/ws/coaching")
async def coaching_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "system",
        "message": (
            "Welcome to LaunchPad Live Coaching! "
            "Send a question you're practicing and I'll provide feedback and tips. "
            "Type 'quit' to end the session."
        ),
    })
    try:
        while True:
            data = await websocket.receive_text()
            if data.strip().lower() == "quit":
                await websocket.send_json({"type": "system", "message": "Session ended. Good luck with your interviews!"})
                await websocket.close()
                break

            lower = data.strip().lower()
            tip = DEFAULT_COACHING
            matched_topic = None
            for keyword, coaching in COACHING_TIPS.items():
                if keyword in lower:
                    tip = coaching
                    matched_topic = keyword
                    break

            await websocket.send_json({
                "type": "coaching",
                "topic": matched_topic or "general",
                "feedback": tip,
                "follow_up": "Try answering this out loud, then send your next question.",
            })
    except WebSocketDisconnect:
        pass
