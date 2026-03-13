from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

MACRS_TABLES: dict[int, list[float]] = {
    3: [0.3333, 0.4445, 0.1481, 0.0741],
    5: [0.2000, 0.3200, 0.1920, 0.1152, 0.1152, 0.0576],
    7: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    10: [0.1000, 0.1800, 0.1440, 0.1152, 0.0922, 0.0737, 0.0655, 0.0655, 0.0656, 0.0655, 0.0328],
    15: [0.0500, 0.0950, 0.0855, 0.0770, 0.0693, 0.0623, 0.0590, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0590, 0.0591, 0.0295],
    20: [0.0375, 0.0722, 0.0668, 0.0618, 0.0571, 0.0528, 0.0489, 0.0452, 0.0447, 0.0447, 0.0446, 0.0446, 0.0447, 0.0446, 0.0446, 0.0446, 0.0446, 0.0447, 0.0446, 0.0446, 0.0223],
}

SECTION_179_LIMIT_2024 = 1_220_000
SECTION_179_PHASEOUT_START_2024 = 3_050_000
BONUS_DEPRECIATION_RATE_2024 = 0.60  # phasing down: 80% in 2023, 60% in 2024, 40% in 2025

ASSET_CLASS_YEARS: dict[str, int] = {
    "computer": 5,
    "office_furniture": 7,
    "vehicle": 5,
    "machinery": 7,
    "appliance": 5,
    "building_improvement": 15,
    "land_improvement": 15,
    "residential_rental": 27,  # actually 27.5 — straight-line, not MACRS GDS
    "nonresidential_real": 39,
}


@dataclass
class Asset:
    name: str
    cost: float
    placed_in_service: date
    asset_class: str = "computer"
    use_section_179: bool = False
    use_bonus: bool = True


@dataclass
class YearEntry:
    year: int
    depreciation: float
    cumulative: float
    remaining_basis: float


@dataclass
class AssetSchedule:
    name: str
    cost: float
    asset_class: str
    recovery_years: int
    method: str
    section_179_amount: float
    bonus_amount: float
    depreciable_basis: float
    schedule: list[YearEntry] = field(default_factory=list)
    total_depreciation: float = 0.0


@dataclass
class DepreciationPlan:
    assets: list[AssetSchedule] = field(default_factory=list)
    total_section_179: float = 0.0
    section_179_remaining: float = SECTION_179_LIMIT_2024
    total_first_year: float = 0.0
    total_all_years: float = 0.0
    summary_by_year: dict[int, float] = field(default_factory=dict)


def _resolve_recovery_years(asset_class: str) -> int:
    return ASSET_CLASS_YEARS.get(asset_class, 7)


def calculate_depreciation(assets: list[Asset]) -> DepreciationPlan:
    plan = DepreciationPlan()
    remaining_179 = SECTION_179_LIMIT_2024

    for asset in assets:
        recovery = _resolve_recovery_years(asset.asset_class)
        start_year = asset.placed_in_service.year

        s179 = 0.0
        if asset.use_section_179 and remaining_179 > 0:
            s179 = min(asset.cost, remaining_179)
            remaining_179 -= s179

        basis_after_179 = asset.cost - s179

        bonus = 0.0
        if asset.use_bonus and recovery <= 20:
            bonus = basis_after_179 * BONUS_DEPRECIATION_RATE_2024

        depreciable_basis = basis_after_179 - bonus

        macrs_rates = MACRS_TABLES.get(recovery)
        schedule_entries: list[YearEntry] = []
        cumulative = s179 + bonus

        if macrs_rates and depreciable_basis > 0:
            for i, rate in enumerate(macrs_rates):
                year_dep = round(depreciable_basis * rate, 2)
                cumulative += year_dep
                schedule_entries.append(YearEntry(
                    year=start_year + i,
                    depreciation=year_dep,
                    cumulative=round(cumulative, 2),
                    remaining_basis=round(asset.cost - cumulative, 2),
                ))
        elif depreciable_basis > 0:
            annual = depreciable_basis / recovery
            for i in range(recovery):
                year_dep = round(annual, 2)
                cumulative += year_dep
                schedule_entries.append(YearEntry(
                    year=start_year + i,
                    depreciation=year_dep,
                    cumulative=round(min(cumulative, asset.cost), 2),
                    remaining_basis=round(max(asset.cost - cumulative, 0), 2),
                ))

        method_parts = []
        if s179 > 0:
            method_parts.append("Section 179")
        if bonus > 0:
            method_parts.append(f"Bonus ({BONUS_DEPRECIATION_RATE_2024:.0%})")
        if macrs_rates:
            method_parts.append(f"MACRS {recovery}-year")
        else:
            method_parts.append(f"Straight-line {recovery}-year")

        sched = AssetSchedule(
            name=asset.name,
            cost=asset.cost,
            asset_class=asset.asset_class,
            recovery_years=recovery,
            method=" + ".join(method_parts),
            section_179_amount=round(s179, 2),
            bonus_amount=round(bonus, 2),
            depreciable_basis=round(depreciable_basis, 2),
            schedule=schedule_entries,
            total_depreciation=round(asset.cost, 2),
        )
        plan.assets.append(sched)

        first_year_total = s179 + bonus + (schedule_entries[0].depreciation if schedule_entries else 0)
        plan.total_first_year += first_year_total

        for entry in schedule_entries:
            plan.summary_by_year[entry.year] = plan.summary_by_year.get(entry.year, 0) + entry.depreciation
        if s179 > 0 or bonus > 0:
            plan.summary_by_year[start_year] = plan.summary_by_year.get(start_year, 0) + s179 + bonus

    plan.total_section_179 = SECTION_179_LIMIT_2024 - remaining_179
    plan.section_179_remaining = remaining_179
    plan.total_all_years = sum(a.cost for a in assets)

    return plan
