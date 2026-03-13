"""DentAI CDT Code Engine — procedure description → matching CDT codes."""

from __future__ import annotations

from pydantic import BaseModel
from thefuzz import fuzz


class CDTMatch(BaseModel):
    code: str
    description: str
    category: str
    confidence: float


class CodingSuggestion(BaseModel):
    query: str
    matches: list[CDTMatch]


class CodingRequest(BaseModel):
    procedure_description: str
    top_n: int = 3


# ---------------------------------------------------------------------------
# CDT code dictionary (~100 common procedures)
# ---------------------------------------------------------------------------

CDT_CODES: list[dict[str, str]] = [
    # Diagnostic
    {"code": "D0120", "description": "Periodic oral evaluation — established patient", "category": "Diagnostic"},
    {"code": "D0140", "description": "Limited oral evaluation — problem focused", "category": "Diagnostic"},
    {"code": "D0150", "description": "Comprehensive oral evaluation — new or established patient", "category": "Diagnostic"},
    {"code": "D0160", "description": "Detailed and extensive oral evaluation — problem focused", "category": "Diagnostic"},
    {"code": "D0170", "description": "Re-evaluation — limited, problem focused", "category": "Diagnostic"},
    {"code": "D0180", "description": "Comprehensive periodontal evaluation — new or established patient", "category": "Diagnostic"},
    {"code": "D0210", "description": "Intraoral — complete series of radiographic images", "category": "Diagnostic"},
    {"code": "D0220", "description": "Intraoral — periapical first radiographic image", "category": "Diagnostic"},
    {"code": "D0230", "description": "Intraoral — periapical each additional radiographic image", "category": "Diagnostic"},
    {"code": "D0240", "description": "Intraoral — occlusal radiographic image", "category": "Diagnostic"},
    {"code": "D0270", "description": "Bitewing — single radiographic image", "category": "Diagnostic"},
    {"code": "D0272", "description": "Bitewings — two radiographic images", "category": "Diagnostic"},
    {"code": "D0274", "description": "Bitewings — four radiographic images", "category": "Diagnostic"},
    {"code": "D0330", "description": "Panoramic radiographic image", "category": "Diagnostic"},
    {"code": "D0340", "description": "2D cephalometric radiographic image", "category": "Diagnostic"},
    {"code": "D0350", "description": "2D oral/facial photographic image", "category": "Diagnostic"},
    {"code": "D0367", "description": "Cone beam CT — both jaws", "category": "Diagnostic"},
    {"code": "D0431", "description": "Adjunctive pre-diagnostic test — salivary", "category": "Diagnostic"},
    {"code": "D0460", "description": "Pulp vitality tests", "category": "Diagnostic"},
    {"code": "D0470", "description": "Diagnostic casts", "category": "Diagnostic"},

    # Preventive
    {"code": "D1110", "description": "Prophylaxis — adult", "category": "Preventive"},
    {"code": "D1120", "description": "Prophylaxis — child", "category": "Preventive"},
    {"code": "D1206", "description": "Topical application of fluoride varnish", "category": "Preventive"},
    {"code": "D1208", "description": "Topical application of fluoride — excluding varnish", "category": "Preventive"},
    {"code": "D1351", "description": "Sealant — per tooth", "category": "Preventive"},
    {"code": "D1354", "description": "Interim caries arresting medicament application — per tooth", "category": "Preventive"},
    {"code": "D1510", "description": "Space maintainer — fixed, unilateral", "category": "Preventive"},
    {"code": "D1575", "description": "Distal shoe space maintainer", "category": "Preventive"},

    # Restorative
    {"code": "D2140", "description": "Amalgam — one surface, primary or permanent", "category": "Restorative"},
    {"code": "D2150", "description": "Amalgam — two surfaces, primary or permanent", "category": "Restorative"},
    {"code": "D2160", "description": "Amalgam — three surfaces, primary or permanent", "category": "Restorative"},
    {"code": "D2330", "description": "Resin-based composite — one surface, anterior", "category": "Restorative"},
    {"code": "D2331", "description": "Resin-based composite — two surfaces, anterior", "category": "Restorative"},
    {"code": "D2332", "description": "Resin-based composite — three surfaces, anterior", "category": "Restorative"},
    {"code": "D2391", "description": "Resin-based composite — one surface, posterior", "category": "Restorative"},
    {"code": "D2392", "description": "Resin-based composite — two surfaces, posterior", "category": "Restorative"},
    {"code": "D2393", "description": "Resin-based composite — three surfaces, posterior", "category": "Restorative"},
    {"code": "D2394", "description": "Resin-based composite — four or more surfaces, posterior", "category": "Restorative"},
    {"code": "D2610", "description": "Inlay — porcelain/ceramic, one surface", "category": "Restorative"},
    {"code": "D2630", "description": "Inlay — porcelain/ceramic, three or more surfaces", "category": "Restorative"},
    {"code": "D2710", "description": "Crown — resin-based composite (indirect)", "category": "Restorative"},
    {"code": "D2740", "description": "Crown — porcelain/ceramic", "category": "Restorative"},
    {"code": "D2750", "description": "Crown — porcelain fused to high noble metal", "category": "Restorative"},
    {"code": "D2751", "description": "Crown — porcelain fused to predominantly base metal", "category": "Restorative"},
    {"code": "D2752", "description": "Crown — porcelain fused to noble metal", "category": "Restorative"},
    {"code": "D2790", "description": "Crown — full cast high noble metal", "category": "Restorative"},
    {"code": "D2799", "description": "Provisional crown — further treatment required", "category": "Restorative"},
    {"code": "D2910", "description": "Re-cement or re-bond inlay, onlay, veneer, partial or full crown", "category": "Restorative"},
    {"code": "D2920", "description": "Re-cement or re-bond crown", "category": "Restorative"},
    {"code": "D2940", "description": "Protective restoration", "category": "Restorative"},
    {"code": "D2950", "description": "Core buildup, including any pins", "category": "Restorative"},
    {"code": "D2954", "description": "Prefabricated post and core in addition to crown", "category": "Restorative"},

    # Endodontics
    {"code": "D3110", "description": "Pulp cap — direct (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3120", "description": "Pulp cap — indirect (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3220", "description": "Therapeutic pulpotomy (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3221", "description": "Pulpal debridement, primary and permanent teeth", "category": "Endodontics"},
    {"code": "D3310", "description": "Endodontic therapy, anterior tooth (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3320", "description": "Endodontic therapy, premolar tooth (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3330", "description": "Endodontic therapy, molar tooth (excluding final restoration)", "category": "Endodontics"},
    {"code": "D3346", "description": "Retreatment of previous root canal therapy — anterior", "category": "Endodontics"},
    {"code": "D3348", "description": "Retreatment of previous root canal therapy — molar", "category": "Endodontics"},
    {"code": "D3410", "description": "Apicoectomy — anterior", "category": "Endodontics"},
    {"code": "D3426", "description": "Apicoectomy — molar", "category": "Endodontics"},

    # Periodontics
    {"code": "D4210", "description": "Gingivectomy or gingivoplasty — per quadrant", "category": "Periodontics"},
    {"code": "D4240", "description": "Gingival flap procedure, including root planing — per quadrant", "category": "Periodontics"},
    {"code": "D4249", "description": "Clinical crown lengthening — hard tissue", "category": "Periodontics"},
    {"code": "D4260", "description": "Osseous surgery — per quadrant", "category": "Periodontics"},
    {"code": "D4263", "description": "Bone replacement graft — retained natural tooth", "category": "Periodontics"},
    {"code": "D4341", "description": "Periodontal scaling and root planing — per quadrant", "category": "Periodontics"},
    {"code": "D4342", "description": "Periodontal scaling and root planing — one to three teeth per quadrant", "category": "Periodontics"},
    {"code": "D4355", "description": "Full mouth debridement", "category": "Periodontics"},
    {"code": "D4381", "description": "Localized delivery of antimicrobial agents — per tooth", "category": "Periodontics"},
    {"code": "D4910", "description": "Periodontal maintenance", "category": "Periodontics"},

    # Prosthodontics (removable)
    {"code": "D5110", "description": "Complete denture — maxillary", "category": "Prosthodontics"},
    {"code": "D5120", "description": "Complete denture — mandibular", "category": "Prosthodontics"},
    {"code": "D5211", "description": "Maxillary partial denture — resin base", "category": "Prosthodontics"},
    {"code": "D5213", "description": "Maxillary partial denture — cast metal framework with resin base", "category": "Prosthodontics"},
    {"code": "D5214", "description": "Mandibular partial denture — cast metal framework with resin base", "category": "Prosthodontics"},
    {"code": "D5410", "description": "Adjust complete denture — maxillary", "category": "Prosthodontics"},
    {"code": "D5422", "description": "Adjust partial denture — mandibular", "category": "Prosthodontics"},
    {"code": "D5511", "description": "Repair broken complete denture base — mandibular", "category": "Prosthodontics"},
    {"code": "D5611", "description": "Repair resin partial denture base — mandibular", "category": "Prosthodontics"},
    {"code": "D5750", "description": "Reline complete maxillary denture (chairside)", "category": "Prosthodontics"},
    {"code": "D5820", "description": "Interim partial denture — maxillary", "category": "Prosthodontics"},

    # Implants
    {"code": "D6010", "description": "Surgical placement of implant body — endosteal implant", "category": "Implant Services"},
    {"code": "D6040", "description": "Surgical placement — eposteal implant", "category": "Implant Services"},
    {"code": "D6056", "description": "Prefabricated abutment", "category": "Implant Services"},
    {"code": "D6058", "description": "Abutment supported porcelain/ceramic crown", "category": "Implant Services"},
    {"code": "D6065", "description": "Implant supported porcelain/ceramic crown", "category": "Implant Services"},
    {"code": "D6080", "description": "Implant maintenance procedures", "category": "Implant Services"},
    {"code": "D6104", "description": "Bone graft at time of implant placement", "category": "Implant Services"},
    {"code": "D6190", "description": "Radiographic/surgical implant index", "category": "Implant Services"},

    # Oral Surgery
    {"code": "D7111", "description": "Extraction, coronal remnants — primary tooth", "category": "Oral Surgery"},
    {"code": "D7140", "description": "Extraction, erupted tooth or exposed root", "category": "Oral Surgery"},
    {"code": "D7210", "description": "Extraction — surgical removal of erupted tooth", "category": "Oral Surgery"},
    {"code": "D7220", "description": "Removal of impacted tooth — soft tissue", "category": "Oral Surgery"},
    {"code": "D7230", "description": "Removal of impacted tooth — partially bony", "category": "Oral Surgery"},
    {"code": "D7240", "description": "Removal of impacted tooth — completely bony", "category": "Oral Surgery"},
    {"code": "D7250", "description": "Removal of residual tooth roots (cutting procedure)", "category": "Oral Surgery"},
    {"code": "D7310", "description": "Alveoloplasty in conjunction with extractions — per quadrant", "category": "Oral Surgery"},
    {"code": "D7471", "description": "Removal of lateral exostosis", "category": "Oral Surgery"},
    {"code": "D7510", "description": "Incision and drainage of abscess — intraoral soft tissue", "category": "Oral Surgery"},
    {"code": "D7953", "description": "Bone replacement graft for ridge preservation — per site", "category": "Oral Surgery"},

    # Orthodontics
    {"code": "D8010", "description": "Limited orthodontic treatment — primary dentition", "category": "Orthodontics"},
    {"code": "D8020", "description": "Limited orthodontic treatment — transitional dentition", "category": "Orthodontics"},
    {"code": "D8070", "description": "Comprehensive orthodontic treatment — transitional dentition", "category": "Orthodontics"},
    {"code": "D8080", "description": "Comprehensive orthodontic treatment — adolescent dentition", "category": "Orthodontics"},
    {"code": "D8090", "description": "Comprehensive orthodontic treatment — adult dentition", "category": "Orthodontics"},
    {"code": "D8210", "description": "Removable appliance therapy", "category": "Orthodontics"},
    {"code": "D8670", "description": "Periodic orthodontic treatment visit", "category": "Orthodontics"},
    {"code": "D8680", "description": "Orthodontic retention", "category": "Orthodontics"},

    # Adjunctive / Misc
    {"code": "D9110", "description": "Palliative treatment of dental pain — minor procedure", "category": "Adjunctive General Services"},
    {"code": "D9215", "description": "Local anesthesia in conjunction with operative or surgical procedures", "category": "Adjunctive General Services"},
    {"code": "D9222", "description": "Deep sedation/general anesthesia — first 15 minutes", "category": "Adjunctive General Services"},
    {"code": "D9230", "description": "Inhalation of nitrous oxide / analgesia", "category": "Adjunctive General Services"},
    {"code": "D9310", "description": "Consultation — diagnostic service by dentist other than treating", "category": "Adjunctive General Services"},
    {"code": "D9440", "description": "Office visit — after regularly scheduled hours", "category": "Adjunctive General Services"},
    {"code": "D9930", "description": "Treatment of complications — unusual circumstances", "category": "Adjunctive General Services"},
    {"code": "D9972", "description": "External bleaching — per arch — performed in office", "category": "Adjunctive General Services"},
    {"code": "D9986", "description": "Missed appointment", "category": "Adjunctive General Services"},
    {"code": "D9987", "description": "Cancelled appointment", "category": "Adjunctive General Services"},
]


def _score(query: str, entry: dict[str, str]) -> float:
    """Combined fuzzy score against code description and category."""
    desc_score = fuzz.token_set_ratio(query, entry["description"])
    code_score = fuzz.ratio(query.upper(), entry["code"]) * 0.6
    cat_score = fuzz.token_set_ratio(query, entry["category"]) * 0.3
    return max(desc_score, code_score, cat_score)


def suggest_codes(req: CodingRequest) -> CodingSuggestion:
    """Return top-N CDT code matches for a procedure description."""
    query = req.procedure_description.strip()
    scored = [(_score(query, entry), entry) for entry in CDT_CODES]
    scored.sort(key=lambda x: x[0], reverse=True)

    matches: list[CDTMatch] = []
    for score, entry in scored[: req.top_n]:
        matches.append(
            CDTMatch(
                code=entry["code"],
                description=entry["description"],
                category=entry["category"],
                confidence=round(score / 100.0, 3),
            )
        )

    return CodingSuggestion(query=query, matches=matches)
