"""DentAI Treatment Planner — symptoms + history → phased treatment plan."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Phase(str, Enum):
    URGENT = "urgent"
    NECESSARY = "necessary"
    ELECTIVE = "elective"


class Procedure(BaseModel):
    name: str
    cdt_code: Optional[str] = None
    estimated_cost: float
    priority: int = Field(ge=1, le=10, description="1 = highest priority")
    duration_minutes: int
    rationale: str


class TreatmentPhase(BaseModel):
    phase: Phase
    label: str
    procedures: list[Procedure]
    phase_total: float = 0.0

    def model_post_init(self, __context: object) -> None:
        self.phase_total = round(sum(p.estimated_cost for p in self.procedures), 2)


class TreatmentPlan(BaseModel):
    chief_complaint: str
    summary: str
    phases: list[TreatmentPhase]
    total_estimated_cost: float = 0.0
    notes: list[str] = []

    def model_post_init(self, __context: object) -> None:
        self.total_estimated_cost = round(
            sum(ph.phase_total for ph in self.phases), 2
        )


class TreatmentRequest(BaseModel):
    chief_complaint: str
    symptoms: list[str] = []
    dental_history: list[str] = []
    findings: list[str] = []


# ---------------------------------------------------------------------------
# Symptom / finding → procedure knowledge base
# ---------------------------------------------------------------------------

_SYMPTOM_RULES: list[dict] = [
    {
        "triggers": ["pain", "toothache", "throbbing", "sensitivity to hot", "sensitivity to cold"],
        "phase": Phase.URGENT,
        "procedures": [
            Procedure(
                name="Emergency Exam",
                cdt_code="D0140",
                estimated_cost=85.0,
                priority=1,
                duration_minutes=15,
                rationale="Evaluate source of acute pain",
            ),
            Procedure(
                name="Periapical Radiograph",
                cdt_code="D0220",
                estimated_cost=35.0,
                priority=1,
                duration_minutes=5,
                rationale="Identify periapical pathology",
            ),
        ],
    },
    {
        "triggers": ["cavity", "caries", "decay", "hole in tooth"],
        "phase": Phase.NECESSARY,
        "procedures": [
            Procedure(
                name="Resin-Based Composite — One Surface, Posterior",
                cdt_code="D2391",
                estimated_cost=195.0,
                priority=3,
                duration_minutes=45,
                rationale="Restore carious lesion and prevent progression",
            ),
        ],
    },
    {
        "triggers": ["broken tooth", "fractured", "cracked", "chipped"],
        "phase": Phase.URGENT,
        "procedures": [
            Procedure(
                name="Porcelain/Ceramic Crown",
                cdt_code="D2740",
                estimated_cost=1150.0,
                priority=2,
                duration_minutes=90,
                rationale="Restore structural integrity of fractured tooth",
            ),
        ],
    },
    {
        "triggers": ["abscess", "swelling", "pus", "infection", "fever"],
        "phase": Phase.URGENT,
        "procedures": [
            Procedure(
                name="Incision and Drainage of Abscess",
                cdt_code="D7510",
                estimated_cost=310.0,
                priority=1,
                duration_minutes=30,
                rationale="Drain infection and relieve pressure",
            ),
            Procedure(
                name="Pulpectomy — Anterior",
                cdt_code="D3221",
                estimated_cost=280.0,
                priority=2,
                duration_minutes=45,
                rationale="Remove infected pulp tissue",
            ),
        ],
    },
    {
        "triggers": ["bleeding gums", "gingivitis", "gum disease", "periodontitis", "loose tooth"],
        "phase": Phase.NECESSARY,
        "procedures": [
            Procedure(
                name="Periodontal Scaling and Root Planing — Per Quadrant",
                cdt_code="D4341",
                estimated_cost=275.0,
                priority=3,
                duration_minutes=60,
                rationale="Remove subgingival calculus and biofilm",
            ),
            Procedure(
                name="Full Mouth Debridement",
                cdt_code="D4355",
                estimated_cost=190.0,
                priority=4,
                duration_minutes=60,
                rationale="Enable comprehensive evaluation",
            ),
        ],
    },
    {
        "triggers": ["missing tooth", "gap", "edentulous", "extraction"],
        "phase": Phase.NECESSARY,
        "procedures": [
            Procedure(
                name="Surgical Extraction",
                cdt_code="D7210",
                estimated_cost=350.0,
                priority=2,
                duration_minutes=45,
                rationale="Remove non-restorable or impacted tooth",
            ),
        ],
    },
    {
        "triggers": ["wisdom tooth", "third molar", "impacted"],
        "phase": Phase.NECESSARY,
        "procedures": [
            Procedure(
                name="Surgical Removal of Impacted Tooth — Soft Tissue",
                cdt_code="D7220",
                estimated_cost=400.0,
                priority=3,
                duration_minutes=45,
                rationale="Remove impacted third molar to prevent complications",
            ),
        ],
    },
    {
        "triggers": ["whitening", "staining", "discoloration", "cosmetic"],
        "phase": Phase.ELECTIVE,
        "procedures": [
            Procedure(
                name="In-Office Tooth Whitening",
                cdt_code="D9972",
                estimated_cost=500.0,
                priority=8,
                duration_minutes=60,
                rationale="Improve tooth shade for cosmetic purposes",
            ),
        ],
    },
    {
        "triggers": ["implant", "replacement tooth"],
        "phase": Phase.ELECTIVE,
        "procedures": [
            Procedure(
                name="Endosteal Implant",
                cdt_code="D6010",
                estimated_cost=2200.0,
                priority=5,
                duration_minutes=120,
                rationale="Permanent prosthetic tooth replacement",
            ),
            Procedure(
                name="Implant-Supported Crown",
                cdt_code="D6065",
                estimated_cost=1600.0,
                priority=6,
                duration_minutes=60,
                rationale="Restore implant with ceramic crown",
            ),
        ],
    },
    {
        "triggers": ["root canal", "pulpitis", "necrotic"],
        "phase": Phase.URGENT,
        "procedures": [
            Procedure(
                name="Root Canal — Molar",
                cdt_code="D3330",
                estimated_cost=1050.0,
                priority=2,
                duration_minutes=90,
                rationale="Remove infected pulp and obturate canals",
            ),
        ],
    },
]

# Always recommend a comprehensive exam if none of the urgent triggers fire
_BASELINE_PROCEDURES = [
    Procedure(
        name="Comprehensive Oral Evaluation",
        cdt_code="D0150",
        estimated_cost=95.0,
        priority=5,
        duration_minutes=30,
        rationale="Baseline comprehensive evaluation for new or returning patient",
    ),
    Procedure(
        name="Prophylaxis — Adult",
        cdt_code="D1110",
        estimated_cost=110.0,
        priority=6,
        duration_minutes=45,
        rationale="Routine professional cleaning",
    ),
]


def generate_plan(req: TreatmentRequest) -> TreatmentPlan:
    """Build a phased treatment plan from symptoms, history, and findings."""
    combined_text = " ".join(
        [req.chief_complaint] + req.symptoms + req.findings + req.dental_history
    ).lower()

    phase_map: dict[Phase, list[Procedure]] = {
        Phase.URGENT: [],
        Phase.NECESSARY: [],
        Phase.ELECTIVE: [],
    }

    matched_any = False
    for rule in _SYMPTOM_RULES:
        if any(trigger in combined_text for trigger in rule["triggers"]):
            matched_any = True
            phase_map[rule["phase"]].extend(rule["procedures"])

    if not matched_any:
        phase_map[Phase.NECESSARY].extend(_BASELINE_PROCEDURES)

    # Deduplicate by CDT code within each phase
    for phase_key in phase_map:
        seen: set[str | None] = set()
        unique: list[Procedure] = []
        for proc in phase_map[phase_key]:
            if proc.cdt_code not in seen:
                seen.add(proc.cdt_code)
                unique.append(proc)
        phase_map[phase_key] = unique

    phases = []
    phase_labels = {
        Phase.URGENT: "Phase 1 — Urgent / Immediate",
        Phase.NECESSARY: "Phase 2 — Necessary Treatment",
        Phase.ELECTIVE: "Phase 3 — Elective / Cosmetic",
    }
    for phase_key in Phase:
        procs = phase_map[phase_key]
        if procs:
            procs.sort(key=lambda p: p.priority)
            phases.append(
                TreatmentPhase(
                    phase=phase_key,
                    label=phase_labels[phase_key],
                    procedures=procs,
                )
            )

    notes: list[str] = []
    if any(kw in combined_text for kw in ("diabetes", "hypertension", "blood thinner", "anticoagulant")):
        notes.append("Medical history may affect treatment sequencing — coordinate with patient's physician.")
    if any(kw in combined_text for kw in ("pregnant", "pregnancy")):
        notes.append("Defer elective radiographs and procedures until postpartum when possible.")

    return TreatmentPlan(
        chief_complaint=req.chief_complaint,
        summary=f"Treatment plan addressing: {req.chief_complaint}",
        phases=phases,
        notes=notes,
    )
