"""DentAI API — FastAPI application serving dental intelligence endpoints."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .coding import CodingRequest, CodingSuggestion, suggest_codes
from .notes import NoteRequest, SOAPNote, generate_note
from .treatment import TreatmentPlan, TreatmentRequest, generate_plan

app = FastAPI(
    title="DentAI",
    description="AI-Powered Dental Intelligence — treatment planning, CDT coding, clinical notes, risk assessment, and material recommendations.",
    version="0.1.0",
    contact={"name": "Mint Rail LLC"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "dentai", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Treatment Planning
# ---------------------------------------------------------------------------

@app.post("/v1/treatment/plan", response_model=TreatmentPlan)
async def treatment_plan(req: TreatmentRequest):
    return generate_plan(req)


# ---------------------------------------------------------------------------
# CDT Coding
# ---------------------------------------------------------------------------

@app.post("/v1/coding/suggest", response_model=CodingSuggestion)
async def coding_suggest(req: CodingRequest):
    return suggest_codes(req)


# ---------------------------------------------------------------------------
# SOAP Note Generation
# ---------------------------------------------------------------------------

@app.post("/v1/notes/generate", response_model=SOAPNote)
async def notes_generate(req: NoteRequest):
    return generate_note(req)


# ---------------------------------------------------------------------------
# Risk Assessment
# ---------------------------------------------------------------------------

class PatientFactors(BaseModel):
    age: int = 35
    smoker: bool = False
    diabetic: bool = False
    immunocompromised: bool = False
    blood_thinners: bool = False
    pregnancy: bool = False
    previous_complications: bool = False
    periodontal_disease: bool = False
    allergies: list[str] = []
    asa_class: int = Field(1, ge=1, le=6, description="ASA physical status classification")


class RiskRequest(BaseModel):
    procedure: str
    patient_factors: PatientFactors = PatientFactors()


class RiskAssessment(BaseModel):
    procedure: str
    risk_score: float = Field(ge=0.0, le=10.0)
    risk_level: str
    factors: list[str]
    recommendations: list[str]
    contraindications: list[str]


_PROCEDURE_BASE_RISK: dict[str, float] = {
    "extraction": 2.5,
    "surgical extraction": 4.0,
    "wisdom tooth removal": 4.5,
    "root canal": 2.0,
    "implant": 5.0,
    "bone graft": 5.5,
    "crown": 1.5,
    "filling": 1.0,
    "cleaning": 0.5,
    "deep cleaning": 1.5,
    "scaling and root planing": 2.0,
    "apicoectomy": 5.0,
    "gingivectomy": 3.0,
    "osseous surgery": 5.5,
    "denture": 1.0,
    "veneer": 1.0,
    "whitening": 0.5,
    "sealant": 0.3,
    "biopsy": 3.5,
    "sedation": 4.0,
    "general anesthesia": 6.0,
}


@app.post("/v1/risk/assess", response_model=RiskAssessment)
async def risk_assess(req: RiskRequest):
    proc_lower = req.procedure.lower()

    base = 2.0
    for key, val in _PROCEDURE_BASE_RISK.items():
        if key in proc_lower:
            base = val
            break

    pf = req.patient_factors
    modifiers: list[tuple[float, str]] = []

    if pf.age > 65:
        modifiers.append((0.8, "Advanced age (>65) increases healing time and complication risk"))
    elif pf.age > 50:
        modifiers.append((0.3, "Age >50 slightly elevates procedural risk"))

    if pf.smoker:
        modifiers.append((1.5, "Smoking impairs wound healing and increases infection risk"))
    if pf.diabetic:
        modifiers.append((1.2, "Diabetes affects healing and increases infection susceptibility"))
    if pf.immunocompromised:
        modifiers.append((1.8, "Immunocompromised status significantly increases infection risk"))
    if pf.blood_thinners:
        modifiers.append((1.0, "Anticoagulant therapy increases bleeding risk — coordinate with physician"))
    if pf.pregnancy:
        modifiers.append((0.5, "Pregnancy requires modified treatment approach and medication selection"))
    if pf.previous_complications:
        modifiers.append((0.7, "History of complications warrants additional precautions"))
    if pf.periodontal_disease:
        modifiers.append((0.5, "Active periodontal disease may complicate procedure"))
    if pf.asa_class >= 3:
        modifiers.append((1.0 * (pf.asa_class - 2), f"ASA Class {pf.asa_class} — elevated systemic risk"))

    total = base + sum(m[0] for m in modifiers)
    risk_score = round(min(total, 10.0), 1)

    if risk_score <= 2.0:
        risk_level = "Low"
    elif risk_score <= 4.5:
        risk_level = "Moderate"
    elif risk_score <= 7.0:
        risk_level = "High"
    else:
        risk_level = "Critical"

    factors = [m[1] for m in modifiers] or ["No significant modifying factors identified"]

    recommendations: list[str] = []
    if pf.smoker:
        recommendations.append("Advise smoking cessation at least 48 hours before and 72 hours after procedure")
    if pf.blood_thinners:
        recommendations.append("Consult with prescribing physician regarding anticoagulant management")
    if pf.diabetic:
        recommendations.append("Ensure blood glucose is well-controlled; schedule morning appointments")
    if risk_score > 5.0:
        recommendations.append("Consider pre-operative medical consultation")
    if pf.asa_class >= 3:
        recommendations.append("Obtain medical clearance before proceeding")
    if not recommendations:
        recommendations.append("Standard pre-operative protocol sufficient")

    contraindications: list[str] = []
    if pf.pregnancy and any(kw in proc_lower for kw in ("whitening", "sedation", "general anesthesia")):
        contraindications.append("Procedure generally contraindicated during pregnancy")
    if pf.asa_class >= 5:
        contraindications.append("Elective procedures contraindicated — ASA Class V/VI")
    if pf.allergies:
        contraindications.append(f"Verify materials against known allergies: {', '.join(pf.allergies)}")

    return RiskAssessment(
        procedure=req.procedure,
        risk_score=risk_score,
        risk_level=risk_level,
        factors=factors,
        recommendations=recommendations,
        contraindications=contraindications,
    )


# ---------------------------------------------------------------------------
# Material Recommendations
# ---------------------------------------------------------------------------

class MaterialRequest(BaseModel):
    procedure: str
    tooth_location: Optional[str] = None
    patient_age: Optional[int] = None
    aesthetic_priority: bool = False


class Material(BaseModel):
    name: str
    type: str
    pros: list[str]
    cons: list[str]
    estimated_cost_range: str
    longevity_years: str
    best_for: str


class MaterialRecommendation(BaseModel):
    procedure: str
    materials: list[Material]
    recommendation: str


_MATERIAL_DB: dict[str, list[Material]] = {
    "crown": [
        Material(
            name="Porcelain/Ceramic (e.g., E.max, Zirconia)",
            type="All-ceramic",
            pros=["Excellent aesthetics", "Biocompatible", "Good strength (zirconia)"],
            cons=["Can fracture under heavy bite force", "Higher cost", "Requires more tooth reduction"],
            estimated_cost_range="$800–$1,500",
            longevity_years="10–15",
            best_for="Anterior teeth and visible premolars",
        ),
        Material(
            name="Porcelain-Fused-to-Metal (PFM)",
            type="Metal-ceramic",
            pros=["Good strength", "Reasonable aesthetics", "Long track record"],
            cons=["Metal margin may show", "Porcelain can chip", "Less translucent"],
            estimated_cost_range="$700–$1,200",
            longevity_years="10–15",
            best_for="Posterior teeth where strength is critical",
        ),
        Material(
            name="Gold Alloy",
            type="Full metal",
            pros=["Exceptional durability", "Gentle on opposing teeth", "Precise fit"],
            cons=["Non-aesthetic (metallic color)", "High material cost"],
            estimated_cost_range="$900–$1,400",
            longevity_years="20–30",
            best_for="Posterior molars in patients who prioritize longevity",
        ),
        Material(
            name="Zirconia (monolithic)",
            type="All-ceramic",
            pros=["Extremely strong", "Good aesthetics", "Minimal tooth reduction"],
            cons=["Can wear opposing teeth", "Less translucent than E.max"],
            estimated_cost_range="$800–$1,400",
            longevity_years="15–20",
            best_for="Posterior crowns, bruxism patients",
        ),
    ],
    "filling": [
        Material(
            name="Composite Resin",
            type="Direct restorative",
            pros=["Tooth-colored", "Bonds directly to tooth", "Conservative preparation"],
            cons=["May shrink on curing", "Staining over time", "Lower strength than amalgam for large restorations"],
            estimated_cost_range="$150–$300",
            longevity_years="5–10",
            best_for="Small to medium cavities, anterior and posterior teeth",
        ),
        Material(
            name="Amalgam",
            type="Direct restorative",
            pros=["Very durable", "Cost-effective", "Self-sealing"],
            cons=["Silver/dark appearance", "Requires more tooth removal", "Mercury content concerns"],
            estimated_cost_range="$100–$200",
            longevity_years="10–15",
            best_for="Large posterior restorations where aesthetics are not primary concern",
        ),
        Material(
            name="Glass Ionomer",
            type="Direct restorative",
            pros=["Releases fluoride", "Bonds chemically to tooth", "Good for root caries"],
            cons=["Lower strength", "Less aesthetic than composite", "Limited longevity"],
            estimated_cost_range="$100–$250",
            longevity_years="3–5",
            best_for="Pediatric patients, root surface cavities, interim restorations",
        ),
    ],
    "implant": [
        Material(
            name="Titanium Implant",
            type="Endosteal implant",
            pros=["Proven biocompatibility", "Excellent osseointegration", "High success rate (95%+)"],
            cons=["Metal allergies (rare)", "Gray color may show through thin tissue"],
            estimated_cost_range="$1,500–$3,000",
            longevity_years="20+",
            best_for="Standard implant cases with adequate bone",
        ),
        Material(
            name="Zirconia Implant",
            type="Ceramic implant",
            pros=["Metal-free", "White color", "Hypoallergenic", "Low plaque affinity"],
            cons=["Less long-term data", "One-piece design limits options", "Higher cost"],
            estimated_cost_range="$2,000–$4,000",
            longevity_years="10–15+ (emerging data)",
            best_for="Patients with metal sensitivities or high aesthetic zone placement",
        ),
    ],
    "denture": [
        Material(
            name="Acrylic Resin",
            type="Denture base",
            pros=["Cost-effective", "Easy to repair and reline", "Good aesthetics"],
            cons=["Less durable", "Can fracture", "Bulkier"],
            estimated_cost_range="$600–$1,500",
            longevity_years="5–8",
            best_for="Immediate dentures, budget-conscious patients",
        ),
        Material(
            name="Cast Metal Framework (Chrome-Cobalt)",
            type="Partial denture framework",
            pros=["Strong and thin", "Durable", "Comfortable fit"],
            cons=["Higher cost", "Clasps may be visible", "Cannot be easily modified"],
            estimated_cost_range="$1,200–$2,500",
            longevity_years="8–15",
            best_for="Partial dentures requiring strength and precision",
        ),
        Material(
            name="Flexible Nylon (Valplast)",
            type="Partial denture",
            pros=["Comfortable", "Aesthetic (no metal clasps)", "Lightweight"],
            cons=["Difficult to reline", "Can stain", "Less rigid"],
            estimated_cost_range="$900–$2,000",
            longevity_years="3–5",
            best_for="Patients wanting clasp-free partial dentures",
        ),
    ],
    "veneer": [
        Material(
            name="Porcelain Veneer",
            type="Indirect restoration",
            pros=["Excellent aesthetics", "Stain-resistant", "Durable"],
            cons=["Irreversible preparation", "Higher cost", "Can chip"],
            estimated_cost_range="$800–$2,000",
            longevity_years="10–20",
            best_for="Comprehensive smile makeovers, staining, minor alignment issues",
        ),
        Material(
            name="Composite Veneer",
            type="Direct restoration",
            pros=["Lower cost", "Reversible", "Single-visit placement"],
            cons=["Less durable", "Stains more easily", "Requires more maintenance"],
            estimated_cost_range="$250–$600",
            longevity_years="3–7",
            best_for="Budget-friendly aesthetic improvements, younger patients",
        ),
    ],
}


@app.post("/v1/materials/recommend", response_model=MaterialRecommendation)
async def materials_recommend(req: MaterialRequest):
    proc_lower = req.procedure.lower()

    matched_key = None
    for key in _MATERIAL_DB:
        if key in proc_lower:
            matched_key = key
            break

    if matched_key:
        materials = _MATERIAL_DB[matched_key]
    else:
        materials = [
            Material(
                name="Consult Provider",
                type="N/A",
                pros=["Material selection depends on specific clinical scenario"],
                cons=["Insufficient data for automated recommendation"],
                estimated_cost_range="Varies",
                longevity_years="Varies",
                best_for="Requires clinical judgment",
            )
        ]

    rec_text = f"For {req.procedure}"
    if req.aesthetic_priority:
        rec_text += ", prioritizing aesthetics, consider ceramic or composite options"
    elif req.tooth_location and any(kw in req.tooth_location.lower() for kw in ("molar", "posterior")):
        rec_text += ", in a posterior location, prioritize strength and durability"
    else:
        rec_text += ", consider patient preferences, location, and budget"

    return MaterialRecommendation(
        procedure=req.procedure,
        materials=materials,
        recommendation=rec_text,
    )


# ---------------------------------------------------------------------------
# Radiograph Upload (stub — stores to temp, returns analysis placeholder)
# ---------------------------------------------------------------------------

class RadioAnalysisStub(BaseModel):
    file_id: str
    filename: str
    status: str
    message: str
    findings: list[str]


@app.post("/v1/radiograph/upload", response_model=RadioAnalysisStub)
async def radiograph_upload(file: UploadFile = File(...)):
    file_id = uuid.uuid4().hex[:12]
    tmp_dir = Path(tempfile.gettempdir()) / "dentai_uploads"
    tmp_dir.mkdir(exist_ok=True)

    dest = tmp_dir / f"{file_id}_{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return RadioAnalysisStub(
        file_id=file_id,
        filename=file.filename or "unknown",
        status="pending_analysis",
        message="Image received. Radiograph analysis requires integration with a diagnostic imaging AI model. This stub confirms upload and storage.",
        findings=[
            "Upload successful — image stored for processing",
            "Automated analysis not yet connected (requires DICOM/imaging AI integration)",
            "Manual review recommended pending model integration",
        ],
    )
