from __future__ import annotations

import sys
import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from products._shared.ai_engine import AIEngine

from .deductions import Expense, analyze_deductions
from .entity import compare_entities
from .depreciation import Asset, calculate_depreciation

app = FastAPI(
    title="TaxShield API",
    description="AI-Powered Tax Strategy by Mint Rail LLC",
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
        "You are TaxShield AI, a senior tax strategist and CPA with expertise in US "
        "federal and state tax law. Provide specific, actionable tax planning advice "
        "with code section references, savings estimates, and compliance considerations. "
        "Always note that this is for informational purposes and clients should consult "
        "their tax professional."
    )
)


# ── Request / Response Models ──────────────────────────────────────────────


class ExpenseItem(BaseModel):
    description: str
    amount: float
    vendor: str = ""


class DeductionRequest(BaseModel):
    expenses: list[ExpenseItem]
    gross_income: float = 100000


class EntityRequest(BaseModel):
    gross_income: float
    business_expenses: float
    owner_salary: float = 0


class AssetItem(BaseModel):
    name: str
    cost: float
    placed_in_service: date
    asset_class: str = "computer"
    use_section_179: bool = False
    use_bonus: bool = True


class DepreciationRequest(BaseModel):
    assets: list[AssetItem]


class QuarterlyRequest(BaseModel):
    gross_income: float
    business_expenses: float = 0
    other_income: float = 0
    filing_status: str = "single"
    withholding_ytd: float = 0
    credits: float = 0


class AuditRiskRequest(BaseModel):
    gross_income: float
    total_deductions: float
    home_office: bool = False
    cash_business: bool = False
    foreign_accounts: bool = False
    large_charitable: float = 0
    schedule_c_loss: bool = False
    crypto_transactions: bool = False
    amended_returns: int = 0
    round_numbers: bool = False
    entity_type: str = "individual"


class StrategyRequest(BaseModel):
    gross_income: float
    business_expenses: float = 0
    owner_salary: float = 0
    filing_status: str = "single"
    entity_type: str = "sole_prop"
    assets: list[AssetItem] = Field(default_factory=list)
    expenses: list[ExpenseItem] = Field(default_factory=list)
    state: str = ""


class AIStrategyRequest(BaseModel):
    gross_income: float
    filing_status: str = "single"
    entity_type: str = "sole_prop"
    business_expenses: float = 0
    deductions_summary: str = ""
    state: str = ""
    goals: str = ""


class AIDeductionAdvisorRequest(BaseModel):
    expenses: list[ExpenseItem]
    gross_income: float = 100000
    filing_status: str = "single"
    industry: str = ""


class AIEntityAdviceRequest(BaseModel):
    gross_income: float
    business_expenses: float = 0
    owner_salary: float = 0
    num_employees: int = 0
    state: str = ""
    industry: str = ""
    growth_plans: str = ""


class AIAuditDefenseRequest(BaseModel):
    audit_type: str = "correspondence"
    issues: str = ""
    gross_income: float = 0
    total_deductions: float = 0
    entity_type: str = "individual"


class AIChatRequest(BaseModel):
    question: str
    context: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────


FEDERAL_BRACKETS_SINGLE = [
    (11600, 0.10), (47150, 0.12), (100525, 0.22),
    (191950, 0.24), (243725, 0.32), (609350, 0.35),
    (float("inf"), 0.37),
]


def _income_tax(taxable: float) -> float:
    if taxable <= 0:
        return 0.0
    tax = 0.0
    prev = 0.0
    for ceiling, rate in FEDERAL_BRACKETS_SINGLE:
        portion = min(taxable, ceiling) - prev
        if portion <= 0:
            break
        tax += portion * rate
        prev = ceiling
    return tax


def _se_tax(net: float) -> float:
    taxable = net * 0.9235
    ss = min(taxable, 168600) * 0.124
    med = taxable * 0.029
    return ss + med


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "healthy", "service": "taxshield", "version": "0.1.0"}


@app.post("/v1/deductions/analyze")
def analyze(req: DeductionRequest):
    expenses = [Expense(e.description, e.amount, e.vendor) for e in req.expenses]
    result = analyze_deductions(expenses, req.gross_income)
    return {
        "categorized": [
            {"description": c.description, "amount": c.amount,
             "category": c.category, "confidence": c.confidence}
            for c in result.categorized
        ],
        "total_deductions": result.total_deductions,
        "category_totals": result.category_totals,
        "savings_by_bracket": [
            {"bracket": s.bracket, "rate": s.rate, "estimated_savings": s.estimated_savings}
            for s in result.savings_by_bracket
        ],
        "missed_deductions": result.missed_deductions,
    }


@app.post("/v1/entity/compare")
def entity_compare(req: EntityRequest):
    results = compare_entities(req.gross_income, req.business_expenses, req.owner_salary)
    return {
        "comparison": [
            {
                "entity_type": r.entity_type,
                "net_income": r.net_income,
                "owner_salary": r.owner_salary,
                "federal_income_tax": r.federal_income_tax,
                "self_employment_tax": r.self_employment_tax,
                "corporate_tax": r.corporate_tax,
                "dividend_tax": r.dividend_tax,
                "total_tax": r.total_tax,
                "effective_rate": r.effective_rate,
                "se_tax_savings_vs_sole_prop": r.se_tax_savings_vs_sole_prop,
                "notes": r.notes,
            }
            for r in results
        ],
        "recommendation": min(results, key=lambda r: r.total_tax).entity_type,
    }


@app.post("/v1/depreciation/plan")
def depreciation_plan(req: DepreciationRequest):
    assets = [
        Asset(
            name=a.name, cost=a.cost,
            placed_in_service=a.placed_in_service,
            asset_class=a.asset_class,
            use_section_179=a.use_section_179,
            use_bonus=a.use_bonus,
        )
        for a in req.assets
    ]
    plan = calculate_depreciation(assets)
    return {
        "assets": [
            {
                "name": a.name, "cost": a.cost, "asset_class": a.asset_class,
                "recovery_years": a.recovery_years, "method": a.method,
                "section_179": a.section_179_amount, "bonus": a.bonus_amount,
                "depreciable_basis": a.depreciable_basis,
                "schedule": [
                    {"year": e.year, "depreciation": e.depreciation,
                     "cumulative": e.cumulative, "remaining": e.remaining_basis}
                    for e in a.schedule
                ],
            }
            for a in plan.assets
        ],
        "total_section_179_used": plan.total_section_179,
        "section_179_remaining": plan.section_179_remaining,
        "total_first_year_deduction": round(plan.total_first_year, 2),
        "total_all_years": plan.total_all_years,
        "summary_by_year": dict(sorted(plan.summary_by_year.items())),
    }


@app.post("/v1/estimate/quarterly")
def quarterly_estimate(req: QuarterlyRequest):
    net = req.gross_income - req.business_expenses + req.other_income
    se = _se_tax(net) if req.filing_status != "w2_only" else 0
    se_deduction = se / 2
    standard_deduction = 14600 if req.filing_status == "single" else 29200
    taxable = max(0, net - se_deduction - standard_deduction)
    income_tax = _income_tax(taxable)
    total_tax = income_tax + se - req.credits
    remaining = max(0, total_tax - req.withholding_ytd)
    quarterly = round(remaining / 4, 2)

    return {
        "annual_estimate": {
            "gross_income": req.gross_income,
            "business_expenses": req.business_expenses,
            "net_income": net,
            "self_employment_tax": round(se, 2),
            "federal_income_tax": round(income_tax, 2),
            "total_estimated_tax": round(total_tax, 2),
            "credits_applied": req.credits,
            "withholding_applied": req.withholding_ytd,
        },
        "quarterly_payments": {
            "amount_per_quarter": quarterly,
            "due_dates": ["April 15", "June 15", "September 15", "January 15"],
            "remaining_liability": round(remaining, 2),
        },
        "safe_harbor_note": "Pay at least 100% of prior year tax (110% if AGI > $150k) to avoid penalties.",
    }


@app.post("/v1/audit/risk")
def audit_risk(req: AuditRiskRequest):
    score = 10  # baseline
    factors = []

    deduction_ratio = req.total_deductions / req.gross_income if req.gross_income > 0 else 0
    if deduction_ratio > 0.60:
        score += 20
        factors.append({"factor": "High deduction-to-income ratio", "impact": 20, "detail": f"{deduction_ratio:.0%} of gross income"})
    elif deduction_ratio > 0.40:
        score += 10
        factors.append({"factor": "Elevated deduction ratio", "impact": 10, "detail": f"{deduction_ratio:.0%} of gross income"})

    if req.home_office:
        score += 8
        factors.append({"factor": "Home office deduction claimed", "impact": 8, "detail": "Historically higher audit trigger"})

    if req.cash_business:
        score += 15
        factors.append({"factor": "Cash-intensive business", "impact": 15, "detail": "IRS focus area for unreported income"})

    if req.foreign_accounts:
        score += 12
        factors.append({"factor": "Foreign accounts / FBAR obligations", "impact": 12, "detail": "Enhanced reporting scrutiny"})

    if req.gross_income > 0 and req.large_charitable / req.gross_income > 0.10:
        bump = 10
        score += bump
        factors.append({"factor": "Large charitable deductions", "impact": bump, "detail": f"${req.large_charitable:,.0f} ({req.large_charitable / req.gross_income:.0%} of income)"})

    if req.schedule_c_loss:
        score += 12
        factors.append({"factor": "Schedule C loss reported", "impact": 12, "detail": "Losses trigger hobby-loss rule scrutiny"})

    if req.crypto_transactions:
        score += 8
        factors.append({"factor": "Cryptocurrency transactions", "impact": 8, "detail": "IRS is actively targeting crypto non-compliance"})

    if req.amended_returns > 1:
        score += 5 * min(req.amended_returns, 3)
        factors.append({"factor": "Multiple amended returns", "impact": 5 * min(req.amended_returns, 3), "detail": f"{req.amended_returns} amendments filed"})

    if req.round_numbers:
        score += 5
        factors.append({"factor": "Round number entries", "impact": 5, "detail": "Round figures suggest estimation rather than records"})

    if req.gross_income > 500000:
        score += 8
        factors.append({"factor": "High income (>$500k)", "impact": 8, "detail": "Higher audit rates for high earners"})
    elif req.gross_income > 200000:
        score += 4
        factors.append({"factor": "Upper income bracket", "impact": 4, "detail": "Moderately elevated audit rate"})

    score = min(score, 100)

    if score <= 25:
        risk_level = "Low"
    elif score <= 50:
        risk_level = "Moderate"
    elif score <= 75:
        risk_level = "Elevated"
    else:
        risk_level = "High"

    return {
        "risk_score": score,
        "risk_level": risk_level,
        "factors": sorted(factors, key=lambda f: f["impact"], reverse=True),
        "recommendations": _audit_recommendations(score, factors),
    }


def _audit_recommendations(score: int, factors: list[dict]) -> list[str]:
    recs = ["Maintain thorough documentation for all claimed deductions"]
    if score > 50:
        recs.append("Consider engaging a tax professional for return review before filing")
    factor_names = {f["factor"] for f in factors}
    if "Home office deduction claimed" in factor_names:
        recs.append("Document exclusive and regular use of home office space with photos and measurements")
    if "Cash-intensive business" in factor_names:
        recs.append("Implement POS systems and maintain daily cash reconciliation logs")
    if "Schedule C loss reported" in factor_names:
        recs.append("Document profit motive — maintain business plans and marketing records")
    if "Cryptocurrency transactions" in factor_names:
        recs.append("Use crypto tax software to generate complete transaction history")
    return recs


@app.post("/v1/strategy/optimize")
def strategy_optimize(req: StrategyRequest):
    strategies = []

    entity_results = compare_entities(req.gross_income, req.business_expenses, req.owner_salary)
    best_entity = min(entity_results, key=lambda r: r.total_tax)
    current_entity = next((e for e in entity_results if req.entity_type.lower() in e.entity_type.lower()), entity_results[0])
    entity_savings = current_entity.total_tax - best_entity.total_tax
    if entity_savings > 500:
        strategies.append({
            "strategy": "Entity Restructuring",
            "description": f"Switch from {current_entity.entity_type} to {best_entity.entity_type}",
            "estimated_annual_savings": round(entity_savings, 2),
            "complexity": "Medium",
            "timeline": "1-3 months",
        })

    if req.expenses:
        expenses = [Expense(e.description, e.amount, e.vendor) for e in req.expenses]
        ded_result = analyze_deductions(expenses, req.gross_income)
        if ded_result.missed_deductions:
            missed_total = sum(d["avg_savings"] for d in ded_result.missed_deductions)
            strategies.append({
                "strategy": "Missed Deduction Recovery",
                "description": f"Claim {len(ded_result.missed_deductions)} commonly missed deductions",
                "estimated_annual_savings": missed_total,
                "complexity": "Low",
                "timeline": "Immediate",
                "details": ded_result.missed_deductions,
            })

    if req.assets:
        assets = [
            Asset(a.name, a.cost, a.placed_in_service, a.asset_class, a.use_section_179, a.use_bonus)
            for a in req.assets
        ]
        dep_plan = calculate_depreciation(assets)
        if dep_plan.total_first_year > 0:
            marginal_rate = 0.24
            tax_savings = dep_plan.total_first_year * marginal_rate
            strategies.append({
                "strategy": "Accelerated Depreciation",
                "description": f"Front-load ${dep_plan.total_first_year:,.0f} in depreciation deductions",
                "estimated_annual_savings": round(tax_savings, 2),
                "complexity": "Low",
                "timeline": "Current tax year",
            })

    net = req.gross_income - req.business_expenses
    if net > 60000:
        retirement_limit = min(net * 0.25, 69000)
        strategies.append({
            "strategy": "Retirement Contribution Optimization",
            "description": f"Maximize SEP-IRA or Solo 401(k) contributions up to ${retirement_limit:,.0f}",
            "estimated_annual_savings": round(retirement_limit * 0.24, 2),
            "complexity": "Low",
            "timeline": "Before tax year end",
        })

    if net > 100000:
        strategies.append({
            "strategy": "Income Timing / Deferral",
            "description": "Defer income to next year or accelerate expenses into current year",
            "estimated_annual_savings": round(net * 0.03, 2),
            "complexity": "Medium",
            "timeline": "Q4 planning",
        })

    strategies.sort(key=lambda s: s["estimated_annual_savings"], reverse=True)
    total_savings = sum(s["estimated_annual_savings"] for s in strategies)

    return {
        "current_entity": current_entity.entity_type,
        "strategies": strategies,
        "total_potential_savings": round(total_savings, 2),
        "disclaimer": "Estimates are for planning purposes only. Consult a qualified tax professional before making tax decisions.",
    }


# ── AI-Powered Endpoints ──────────────────────────────────────────────────


@app.post("/v1/ai/strategy")
async def ai_strategy(req: AIStrategyRequest):
    deductions_info = f"\nDeductions summary: {req.deductions_summary}" if req.deductions_summary else ""
    goals_info = f"\nClient goals: {req.goals}" if req.goals else ""
    state_info = f"\nState: {req.state}" if req.state else ""

    prompt = (
        f"Provide a comprehensive tax strategy analysis for:\n"
        f"- Gross income: ${req.gross_income:,.0f}\n"
        f"- Filing status: {req.filing_status}\n"
        f"- Entity type: {req.entity_type}\n"
        f"- Business expenses: ${req.business_expenses:,.0f}\n"
        f"{deductions_info}{state_info}{goals_info}\n\n"
        f"Include:\n"
        f"1. Immediate tax-saving opportunities with estimated dollar savings\n"
        f"2. Entity structure recommendations with pros/cons\n"
        f"3. Retirement contribution optimization (SEP-IRA, Solo 401k, etc.)\n"
        f"4. Income timing and deferral strategies\n"
        f"5. Relevant IRC code sections\n"
        f"6. State-specific considerations if applicable\n"
        f"7. Compliance risks to watch for\n"
    )

    resp = await ai.complete(prompt, temperature=0.4)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "strategy": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/deduction-advisor")
async def ai_deduction_advisor(req: AIDeductionAdvisorRequest):
    expense_lines = "\n".join(
        f"  - {e.description}: ${e.amount:,.2f}" for e in req.expenses
    )
    industry_info = f"\nIndustry: {req.industry}" if req.industry else ""

    prompt = (
        f"Analyze these business expenses for tax deduction optimization:\n"
        f"Gross income: ${req.gross_income:,.0f}\n"
        f"Filing status: {req.filing_status}\n"
        f"{industry_info}\n\n"
        f"Expenses:\n{expense_lines}\n\n"
        f"For each expense, advise:\n"
        f"1. Correct IRS category and Schedule\n"
        f"2. Deductibility percentage (100%, 50% for meals, etc.)\n"
        f"3. Documentation requirements\n"
        f"4. Red flags that could trigger audit\n\n"
        f"Also suggest commonly missed deductions for this income level and profile.\n"
    )

    resp = await ai.complete(prompt, temperature=0.3)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "advice": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/entity-advice")
async def ai_entity_advice(req: AIEntityAdviceRequest):
    prompt = (
        f"Provide entity structure recommendation for:\n"
        f"- Gross income: ${req.gross_income:,.0f}\n"
        f"- Business expenses: ${req.business_expenses:,.0f}\n"
        f"- Desired owner salary: ${req.owner_salary:,.0f}\n"
        f"- Number of employees: {req.num_employees}\n"
        f"- State: {req.state or 'Not specified'}\n"
        f"- Industry: {req.industry or 'Not specified'}\n"
        f"- Growth plans: {req.growth_plans or 'Not specified'}\n\n"
        f"Compare Sole Proprietorship, Single-Member LLC, S-Corp, and C-Corp.\n"
        f"For each, provide:\n"
        f"1. Estimated total tax liability\n"
        f"2. Self-employment tax impact\n"
        f"3. Liability protection level\n"
        f"4. Administrative burden and costs\n"
        f"5. Best fit scenario\n\n"
        f"Give a clear recommendation with the reasoning.\n"
    )

    resp = await ai.complete(prompt, temperature=0.4)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "recommendation": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/audit-defense")
async def ai_audit_defense(req: AIAuditDefenseRequest):
    prompt = (
        f"Provide audit defense strategy for:\n"
        f"- Audit type: {req.audit_type}\n"
        f"- Issues flagged: {req.issues or 'General review'}\n"
        f"- Gross income: ${req.gross_income:,.0f}\n"
        f"- Total deductions: ${req.total_deductions:,.0f}\n"
        f"- Entity type: {req.entity_type}\n\n"
        f"Include:\n"
        f"1. Immediate steps to take upon receiving notice\n"
        f"2. Documentation to gather and organize\n"
        f"3. Common IRS strategies for this type of audit\n"
        f"4. Rights under the Taxpayer Bill of Rights\n"
        f"5. When to engage professional representation\n"
        f"6. Timeline expectations\n"
        f"7. Potential outcomes and how to prepare for each\n"
    )

    resp = await ai.complete(prompt, temperature=0.3)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "defense_strategy": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }


@app.post("/v1/ai/chat")
async def ai_chat(req: AIChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question is empty")

    context_block = f"\n\nAdditional context:\n{req.context}" if req.context.strip() else ""
    prompt = f"{req.question}{context_block}"

    resp = await ai.complete(prompt, temperature=0.5)
    if not resp.ok:
        return {"error": resp.error, "ai_available": ai.available}

    return {
        "answer": resp.text,
        "model": resp.model,
        "tokens": {"input": resp.input_tokens, "output": resp.output_tokens},
    }
