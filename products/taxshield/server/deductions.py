from __future__ import annotations

from dataclasses import dataclass, field

IRS_CATEGORIES: dict[str, list[str]] = {
    "business": [
        "office supplies", "software", "subscriptions", "advertising",
        "marketing", "postage", "shipping", "bank fees", "legal fees",
        "accounting", "consulting", "utilities", "rent", "coworking",
    ],
    "home_office": [
        "home office", "internet", "home utilities", "home rent",
        "home mortgage interest", "home repairs",
    ],
    "vehicle": [
        "gas", "fuel", "car payment", "car lease", "auto insurance",
        "parking", "tolls", "car repair", "vehicle maintenance", "mileage",
    ],
    "meals": [
        "business meal", "client dinner", "client lunch", "team lunch",
        "business entertainment",
    ],
    "travel": [
        "airfare", "hotel", "lodging", "uber", "lyft", "taxi",
        "car rental", "train", "travel",
    ],
    "equipment": [
        "computer", "laptop", "monitor", "printer", "phone",
        "furniture", "desk", "chair", "equipment",
    ],
    "professional_development": [
        "conference", "seminar", "course", "training", "certification",
        "books", "education", "workshop",
    ],
    "insurance": [
        "health insurance", "liability insurance", "business insurance",
        "e&o insurance", "workers comp", "disability insurance",
    ],
    "retirement": [
        "sep ira", "solo 401k", "simple ira", "retirement contribution",
        "pension",
    ],
}

COMMONLY_MISSED = [
    {"category": "home_office", "description": "Home office deduction (simplified or actual)", "avg_savings": 1500},
    {"category": "vehicle", "description": "Standard mileage rate (67 cents/mile for 2024)", "avg_savings": 3200},
    {"category": "retirement", "description": "SEP-IRA contributions (up to 25% of net SE income)", "avg_savings": 8000},
    {"category": "insurance", "description": "Self-employed health insurance deduction", "avg_savings": 6000},
    {"category": "professional_development", "description": "Continuing education and certifications", "avg_savings": 1200},
    {"category": "business", "description": "Business use of cell phone", "avg_savings": 600},
    {"category": "equipment", "description": "Section 179 / bonus depreciation on equipment", "avg_savings": 5000},
    {"category": "business", "description": "Qualified Business Income (QBI) deduction — 20% of qualified income", "avg_savings": 4000},
]

FEDERAL_BRACKETS_2024_SINGLE = [
    (11600, 0.10),
    (47150, 0.12),
    (100525, 0.22),
    (191950, 0.24),
    (243725, 0.32),
    (609350, 0.35),
    (float("inf"), 0.37),
]

BRACKET_LABELS = ["10%", "12%", "22%", "24%", "32%", "35%", "37%"]


@dataclass
class Expense:
    description: str
    amount: float
    vendor: str = ""


@dataclass
class CategorizedExpense:
    description: str
    amount: float
    category: str
    confidence: float


@dataclass
class BracketSavings:
    bracket: str
    rate: float
    estimated_savings: float


@dataclass
class AnalysisResult:
    categorized: list[CategorizedExpense] = field(default_factory=list)
    total_deductions: float = 0.0
    savings_by_bracket: list[BracketSavings] = field(default_factory=list)
    missed_deductions: list[dict] = field(default_factory=list)
    category_totals: dict[str, float] = field(default_factory=dict)


def _classify_expense(desc: str) -> tuple[str, float]:
    lower = desc.lower()
    best_category = "business"
    best_score = 0.0

    for category, keywords in IRS_CATEGORIES.items():
        for keyword in keywords:
            if keyword in lower:
                score = len(keyword) / max(len(lower), 1)
                score = min(score * 2, 1.0)
                if score > best_score:
                    best_score = score
                    best_category = category
    return best_category, max(best_score, 0.4)


def _calculate_tax(taxable_income: float) -> float:
    tax = 0.0
    prev = 0.0
    for ceiling, rate in FEDERAL_BRACKETS_2024_SINGLE:
        bracket_income = min(taxable_income, ceiling) - prev
        if bracket_income <= 0:
            break
        tax += bracket_income * rate
        prev = ceiling
    return tax


def _marginal_rate(taxable_income: float) -> float:
    for ceiling, rate in FEDERAL_BRACKETS_2024_SINGLE:
        if taxable_income <= ceiling:
            return rate
    return 0.37


def analyze_deductions(expenses: list[Expense], gross_income: float = 100000) -> AnalysisResult:
    result = AnalysisResult()
    category_totals: dict[str, float] = {}

    for exp in expenses:
        category, confidence = _classify_expense(exp.description)
        result.categorized.append(CategorizedExpense(
            description=exp.description,
            amount=exp.amount,
            category=category,
            confidence=round(confidence, 2),
        ))
        category_totals[category] = category_totals.get(category, 0) + exp.amount

    result.category_totals = category_totals
    result.total_deductions = sum(e.amount for e in expenses)

    for label, (_, rate) in zip(BRACKET_LABELS, FEDERAL_BRACKETS_2024_SINGLE):
        result.savings_by_bracket.append(BracketSavings(
            bracket=label,
            rate=rate,
            estimated_savings=round(result.total_deductions * rate, 2),
        ))

    claimed_categories = set(category_totals.keys())
    for missed in COMMONLY_MISSED:
        if missed["category"] not in claimed_categories:
            result.missed_deductions.append(missed)

    return result
