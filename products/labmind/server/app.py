"""LabMind API — AI for Scientific Discovery."""

from __future__ import annotations

import sys
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from products._shared.ai_engine import AIEngine

from .literature import EmbeddingIndex
from .experiment import ExperimentRequest, design_experiment
from .stats import DataDescription, recommend_tests

app = FastAPI(
    title="LabMind",
    description="AI for Scientific Discovery — by Mint Rail LLC",
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
        "You are LabMind AI, a multidisciplinary research scientist with expertise "
        "across biology, chemistry, physics, and data science. Provide rigorous "
        "scientific analysis, experimental design with proper controls, statistical "
        "methodology recommendations, and literature synthesis. Cite methodological "
        "standards and statistical best practices."
    )
)

index = EmbeddingIndex()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "labmind",
        "index_size": index.size,
    }


# ---------------------------------------------------------------------------
# Literature
# ---------------------------------------------------------------------------

class AddDocumentsRequest(BaseModel):
    texts: list[str]
    metadata: list[dict] | None = None

class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=50)

class SynthesizeRequest(BaseModel):
    doc_ids: list[str]


@app.post("/v1/literature/add")
def literature_add(req: AddDocumentsRequest):
    if not req.texts:
        raise HTTPException(400, "texts must be non-empty")
    ids = index.add_documents(req.texts, req.metadata)
    return {"added": len(ids), "doc_ids": ids, "index_size": index.size}


@app.post("/v1/literature/search")
def literature_search(req: SearchRequest):
    results = index.search(req.query, k=req.k)
    return {"query": req.query, "results": results, "total_in_index": index.size}


@app.post("/v1/literature/synthesize")
def literature_synthesize(req: SynthesizeRequest):
    if not req.doc_ids:
        raise HTTPException(400, "doc_ids must be non-empty")
    synthesis = index.synthesize(req.doc_ids)
    if "error" in synthesis:
        raise HTTPException(404, synthesis["error"])
    return synthesis


# ---------------------------------------------------------------------------
# Experiment design
# ---------------------------------------------------------------------------

class ExperimentDesignRequest(BaseModel):
    research_question: str
    independent_vars: list[str]
    dependent_vars: list[str]
    hypothesis: str
    expected_effect_size: float = 0.5
    alpha: float = 0.05
    power: float = 0.80
    design_preference: str | None = None


@app.post("/v1/experiment/design")
def experiment_design(req: ExperimentDesignRequest):
    er = ExperimentRequest(
        research_question=req.research_question,
        independent_vars=req.independent_vars,
        dependent_vars=req.dependent_vars,
        hypothesis=req.hypothesis,
        expected_effect_size=req.expected_effect_size,
        alpha=req.alpha,
        power=req.power,
        design_preference=req.design_preference,
    )
    return design_experiment(er)


# ---------------------------------------------------------------------------
# Hypothesis generation
# ---------------------------------------------------------------------------

class HypothesisRequest(BaseModel):
    observations: list[str]
    domain: str = "general"
    max_hypotheses: int = Field(default=3, ge=1, le=10)


@app.post("/v1/hypothesis/generate")
def hypothesis_generate(req: HypothesisRequest):
    """Pattern-based hypothesis generator using observation analysis."""
    if not req.observations:
        raise HTTPException(400, "observations must be non-empty")

    hypotheses = _generate_hypotheses(req.observations, req.domain, req.max_hypotheses)
    return {
        "domain": req.domain,
        "observation_count": len(req.observations),
        "hypotheses": hypotheses,
    }


def _generate_hypotheses(
    observations: list[str],
    domain: str,
    max_h: int,
) -> list[dict]:
    causal_markers = ["increases", "decreases", "causes", "leads to", "results in", "inhibits", "promotes"]
    corr_markers = ["associated with", "correlates", "linked to", "related to", "co-occurs"]

    hypotheses = []
    for i, obs in enumerate(observations):
        obs_lower = obs.lower()
        h_type = "exploratory"
        for m in causal_markers:
            if m in obs_lower:
                h_type = "causal"
                break
        if h_type != "causal":
            for m in corr_markers:
                if m in obs_lower:
                    h_type = "correlational"
                    break

        null_h = _negate(obs)
        hypotheses.append({
            "id": i + 1,
            "type": h_type,
            "alternative_hypothesis": f"H{i+1}: {obs}",
            "null_hypothesis": f"H{i+1}₀: {null_h}",
            "testable": True,
            "suggested_design": _suggest_design(h_type),
            "domain": domain,
        })
        if len(hypotheses) >= max_h:
            break

    return hypotheses


def _negate(statement: str) -> str:
    negations = {
        "increases": "does not increase",
        "decreases": "does not decrease",
        "causes": "does not cause",
        "leads to": "does not lead to",
        "inhibits": "does not inhibit",
        "promotes": "does not promote",
        "is associated with": "is not associated with",
        "correlates with": "does not correlate with",
    }
    result = statement
    for phrase, neg in negations.items():
        if phrase in result.lower():
            idx = result.lower().index(phrase)
            result = result[:idx] + neg + result[idx + len(phrase):]
            return result
    return f"There is no effect: {statement}"


def _suggest_design(h_type: str) -> str:
    return {
        "causal": "Randomized Controlled Trial or quasi-experimental design",
        "correlational": "Cross-sectional survey or longitudinal cohort study",
        "exploratory": "Observational study or preliminary pilot experiment",
    }.get(h_type, "Observational study")


# ---------------------------------------------------------------------------
# Statistical planning
# ---------------------------------------------------------------------------

class StatsPlanRequest(BaseModel):
    sample_size: int = Field(ge=2)
    groups: int = Field(default=2, ge=1)
    data_type: str = "continuous"
    paired: bool = False
    normal_distribution: bool | None = None
    equal_variance: bool | None = None


@app.post("/v1/stats/plan")
def stats_plan(req: StatsPlanRequest):
    desc = DataDescription(
        sample_size=req.sample_size,
        groups=req.groups,
        data_type=req.data_type,
        paired=req.paired,
        normal_distribution=req.normal_distribution,
        equal_variance=req.equal_variance,
    )
    return recommend_tests(desc)


# ---------------------------------------------------------------------------
# Paper drafting
# ---------------------------------------------------------------------------

class PaperDraftRequest(BaseModel):
    title: str
    authors: list[str]
    abstract_summary: str
    sections: list[str] = Field(
        default=["introduction", "methods", "results", "discussion", "conclusion"]
    )
    key_findings: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


@app.post("/v1/paper/draft")
def paper_draft(req: PaperDraftRequest):
    """Generate a structured paper scaffold with section templates."""
    draft: dict = {
        "title": req.title,
        "authors": req.authors,
        "sections": [],
    }

    templates = {
        "introduction": (
            f"This study investigates {req.abstract_summary}. "
            "Prior work has established [CITE RELEVANT LITERATURE]. "
            "However, gaps remain in [SPECIFY GAPS]. "
            "The present research aims to address these gaps by [APPROACH]."
        ),
        "methods": (
            "Participants/Materials: [DESCRIBE SAMPLE]\n"
            "Design: [EXPERIMENTAL DESIGN]\n"
            "Procedure: [STEP-BY-STEP PROTOCOL]\n"
            "Analysis: [STATISTICAL METHODS]"
        ),
        "results": _results_template(req.key_findings),
        "discussion": (
            f"The findings of this study regarding {req.abstract_summary} "
            "suggest [INTERPRETATION]. These results are consistent with / "
            "extend / contrast with prior work by [AUTHORS]. "
            "Limitations include [LIMITATIONS]. "
            "Future research should [DIRECTIONS]."
        ),
        "conclusion": (
            f"In summary, this study demonstrates [KEY CONTRIBUTION] "
            f"in the context of {req.abstract_summary}. "
            "These findings have implications for [FIELD/APPLICATION]."
        ),
        "literature_review": (
            "A systematic review of the literature reveals [THEMES]. "
            "Key studies include [CITE]. Collectively, these findings suggest [SYNTHESIS]."
        ),
        "references": _format_references(req.references),
    }

    for section in req.sections:
        s_lower = section.lower().replace(" ", "_")
        draft["sections"].append({
            "heading": section.replace("_", " ").title(),
            "template": templates.get(s_lower, f"[Content for {section} section]"),
            "guidance": _section_guidance(s_lower),
        })

    return draft


def _results_template(findings: list[str]) -> str:
    if not findings:
        return (
            "Descriptive statistics are presented in Table 1. "
            "[PRIMARY ANALYSIS] revealed [RESULT], [STATISTIC] = [VALUE], "
            "p = [VALUE], [EFFECT SIZE] = [VALUE]."
        )
    lines = ["Key findings:"]
    for i, f in enumerate(findings, 1):
        lines.append(f"  {i}. {f}")
    lines.append("\n[Expand each finding with statistical evidence and tables/figures.]")
    return "\n".join(lines)


def _format_references(refs: list[str]) -> str:
    if not refs:
        return "[Add references in APA 7th edition format]"
    return "\n".join(f"[{i}] {r}" for i, r in enumerate(refs, 1))


def _section_guidance(section: str) -> str:
    return {
        "introduction": "Funnel structure: broad context -> specific gap -> your contribution.",
        "methods": "Sufficient detail for replication. Use past tense.",
        "results": "Report findings without interpretation. Use tables and figures.",
        "discussion": "Interpret results, compare with literature, acknowledge limitations.",
        "conclusion": "Brief, impactful summary. No new information.",
        "literature_review": "Synthesize, don't just list. Identify themes and gaps.",
        "references": "Use consistent citation format (APA 7th recommended).",
    }.get(section, "Follow journal-specific guidelines for this section.")


# ---------------------------------------------------------------------------
# AI-Powered Endpoints
# ---------------------------------------------------------------------------

class AISynthesizeRequest(BaseModel):
    topic: str = Field(..., min_length=5)
    papers: list[str] = Field(default_factory=list, description="Paper summaries or abstracts")
    focus: str = ""

class AIHypothesisRequest(BaseModel):
    observations: list[str] = Field(..., min_length=1)
    domain: str = "general"
    existing_theories: list[str] = Field(default_factory=list)

class AIMethodologyRequest(BaseModel):
    research_question: str = Field(..., min_length=10)
    proposed_method: str = ""
    constraints: list[str] = Field(default_factory=list)

class AIPaperDraftRequest(BaseModel):
    title: str = Field(..., min_length=5)
    section: str = Field("introduction", description="introduction, methods, results, discussion")
    key_points: list[str] = Field(..., min_length=1)
    context: str = ""

class AIStatsAdvisorRequest(BaseModel):
    research_question: str = Field(..., min_length=10)
    data_description: str = ""
    sample_size: int = 0
    variables: list[str] = Field(default_factory=list)
    data_type: str = Field("continuous", description="continuous, categorical, ordinal, mixed")


@app.post("/v1/ai/synthesize")
async def ai_synthesize(req: AISynthesizeRequest):
    papers_text = "\n\n".join(f"Paper {i+1}: {p}" for i, p in enumerate(req.papers)) if req.papers else "No specific papers provided"
    prompt = (
        f"Synthesize the literature on the following topic.\n\n"
        f"Topic: {req.topic}\n"
        f"Focus Area: {req.focus or 'General synthesis'}\n\n"
        f"Source Material:\n{papers_text}\n\n"
        "Provide:\n"
        "1. Thematic synthesis of key findings\n"
        "2. Areas of consensus and controversy\n"
        "3. Methodological trends\n"
        "4. Research gaps identified\n"
        "5. Suggested future directions"
    )
    resp = await ai.complete(prompt, temperature=0.4)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"synthesis": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/hypothesis")
async def ai_hypothesis(req: AIHypothesisRequest):
    obs_text = "\n".join(f"- {o}" for o in req.observations)
    theories_text = "\n".join(f"- {t}" for t in req.existing_theories) if req.existing_theories else "None specified"
    prompt = (
        f"Refine hypotheses and develop testing strategies.\n\n"
        f"Domain: {req.domain}\n"
        f"Observations:\n{obs_text}\n"
        f"Existing Theories:\n{theories_text}\n\n"
        "For each observation, provide:\n"
        "1. Refined testable hypothesis (H1 and H0)\n"
        "2. Predicted outcomes\n"
        "3. Suggested experimental design\n"
        "4. Required controls\n"
        "5. Potential confounds to address"
    )
    resp = await ai.complete(prompt, temperature=0.5)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"hypotheses": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/methodology")
async def ai_methodology(req: AIMethodologyRequest):
    prompt = (
        f"Critique and improve the research methodology.\n\n"
        f"Research Question: {req.research_question}\n"
        f"Proposed Method: {req.proposed_method or 'Not yet determined — suggest approaches'}\n"
        f"Constraints: {', '.join(req.constraints) if req.constraints else 'None specified'}\n\n"
        "Provide:\n"
        "1. Methodology assessment (if provided) or recommended approaches\n"
        "2. Validity threats (internal and external)\n"
        "3. Suggested improvements or alternatives\n"
        "4. Required sample size estimation\n"
        "5. Data collection protocol recommendations"
    )
    resp = await ai.complete(prompt, temperature=0.4)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"methodology": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/paper-draft")
async def ai_paper_draft(req: AIPaperDraftRequest):
    points_text = "\n".join(f"- {p}" for p in req.key_points)
    prompt = (
        f"Draft a {req.section} section for an academic paper.\n\n"
        f"Paper Title: {req.title}\n"
        f"Section: {req.section.title()}\n"
        f"Key Points to Cover:\n{points_text}\n"
        f"Additional Context: {req.context or 'None'}\n\n"
        "Write in formal academic style. Follow standard conventions for this section type. "
        "Include placeholders for citations as [Author, Year]."
    )
    resp = await ai.complete(prompt, temperature=0.5)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"draft": resp.text, "section": req.section, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}


@app.post("/v1/ai/stats-advisor")
async def ai_stats_advisor(req: AIStatsAdvisorRequest):
    vars_text = ", ".join(req.variables) if req.variables else "Not specified"
    prompt = (
        f"Recommend statistical analysis approaches.\n\n"
        f"Research Question: {req.research_question}\n"
        f"Data Description: {req.data_description or 'Not specified'}\n"
        f"Sample Size: {req.sample_size or 'Not determined'}\n"
        f"Variables: {vars_text}\n"
        f"Data Type: {req.data_type}\n\n"
        "Provide:\n"
        "1. Recommended primary statistical test with justification\n"
        "2. Assumptions to verify\n"
        "3. Alternative tests if assumptions are violated\n"
        "4. Effect size measures to report\n"
        "5. Power analysis recommendations\n"
        "6. Multiple comparison corrections if needed"
    )
    resp = await ai.complete(prompt, temperature=0.3)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}
    return {"stats_advice": resp.text, "model": resp.model, "tokens": resp.input_tokens + resp.output_tokens}
