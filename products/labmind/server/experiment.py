"""Experiment designer: structured protocol generation with power analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats as sp_stats


@dataclass
class ExperimentRequest:
    research_question: str
    independent_vars: list[str]
    dependent_vars: list[str]
    hypothesis: str
    expected_effect_size: float = 0.5
    alpha: float = 0.05
    power: float = 0.80
    design_preference: str | None = None


DESIGN_CATALOG = {
    "rct": {
        "name": "Randomized Controlled Trial",
        "suited_for": "Causal inference with one treatment vs. control",
        "min_vars": 1,
        "max_vars": 1,
    },
    "factorial": {
        "name": "Full Factorial Design",
        "suited_for": "Examining main effects and interactions of 2+ factors",
        "min_vars": 2,
        "max_vars": 5,
    },
    "crossover": {
        "name": "Crossover Design",
        "suited_for": "Within-subject comparisons, reduces individual variability",
        "min_vars": 1,
        "max_vars": 2,
    },
    "cohort": {
        "name": "Prospective Cohort Study",
        "suited_for": "Observational studies tracking exposure over time",
        "min_vars": 1,
        "max_vars": 10,
    },
    "case_control": {
        "name": "Case-Control Study",
        "suited_for": "Rare outcomes, retrospective comparison",
        "min_vars": 1,
        "max_vars": 5,
    },
    "repeated_measures": {
        "name": "Repeated Measures Design",
        "suited_for": "Tracking changes within subjects across conditions/time",
        "min_vars": 1,
        "max_vars": 3,
    },
}


def select_design(req: ExperimentRequest) -> dict:
    """Pick the best-fit experimental design based on the request."""
    if req.design_preference and req.design_preference in DESIGN_CATALOG:
        return DESIGN_CATALOG[req.design_preference]

    n_iv = len(req.independent_vars)
    if n_iv >= 2:
        return DESIGN_CATALOG["factorial"]
    if n_iv == 1 and len(req.dependent_vars) > 1:
        return DESIGN_CATALOG["repeated_measures"]
    return DESIGN_CATALOG["rct"]


def compute_sample_size(
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.80,
    groups: int = 2,
    test_type: str = "two_sample_t",
) -> dict:
    """Estimate required sample size via power analysis."""
    if test_type == "two_sample_t":
        # Two-sample t-test: n per group = ((z_a + z_b) / d)^2
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)
        n_per_group = math.ceil(((z_alpha + z_beta) / effect_size) ** 2)
        total = n_per_group * groups
        return {
            "n_per_group": n_per_group,
            "total_n": total,
            "groups": groups,
            "method": "z-approximation for two-sample t-test",
            "parameters": {"effect_size_d": effect_size, "alpha": alpha, "power": power},
        }

    if test_type == "anova":
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)
        # Cohen's f -> d conversion for per-group sizing
        d_equiv = effect_size * math.sqrt(2)
        n_per_group = math.ceil(((z_alpha + z_beta) / d_equiv) ** 2)
        return {
            "n_per_group": n_per_group,
            "total_n": n_per_group * groups,
            "groups": groups,
            "method": "z-approximation for one-way ANOVA (Cohen's f)",
            "parameters": {"effect_size_f": effect_size, "alpha": alpha, "power": power},
        }

    if test_type == "chi_square":
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)
        n_total = math.ceil(((z_alpha + z_beta) / effect_size) ** 2)
        return {
            "n_per_group": math.ceil(n_total / groups),
            "total_n": n_total,
            "groups": groups,
            "method": "z-approximation for chi-square (Cohen's w)",
            "parameters": {"effect_size_w": effect_size, "alpha": alpha, "power": power},
        }

    n_per_group = math.ceil(((1.96 + 0.84) / effect_size) ** 2)
    return {
        "n_per_group": n_per_group,
        "total_n": n_per_group * groups,
        "groups": groups,
        "method": "generic z-approximation",
        "parameters": {"effect_size": effect_size, "alpha": alpha, "power": power},
    }


def identify_confounds(
    independent_vars: list[str],
    dependent_vars: list[str],
) -> list[dict]:
    """Heuristic confound identification based on common experimental patterns."""
    confounds = [
        {
            "name": "Temporal effects",
            "description": "Time of day, season, or maturation effects may covary with treatment.",
            "mitigation": "Randomize timing, include time as a covariate.",
        },
        {
            "name": "Selection bias",
            "description": "Non-random assignment may create pre-existing group differences.",
            "mitigation": "Use random assignment; if not possible, match on key demographics.",
        },
        {
            "name": "Experimenter effects",
            "description": "Researcher expectations may influence measurement.",
            "mitigation": "Use double-blind protocols where feasible.",
        },
    ]

    if len(dependent_vars) > 1:
        confounds.append({
            "name": "Multiple comparisons",
            "description": f"{len(dependent_vars)} dependent variables increase Type I error risk.",
            "mitigation": "Apply Bonferroni or FDR correction.",
        })

    if len(independent_vars) > 2:
        confounds.append({
            "name": "Higher-order interactions",
            "description": "Complex interactions between many IVs may obscure main effects.",
            "mitigation": "Consider a fractional factorial design or pre-register interaction tests.",
        })

    return confounds


def design_experiment(req: ExperimentRequest) -> dict:
    """Generate a full structured experimental protocol."""
    design = select_design(req)
    n_iv = len(req.independent_vars)

    groups = 2 ** n_iv if n_iv <= 4 else 2 * n_iv
    test_type = "anova" if groups > 2 else "two_sample_t"
    sample = compute_sample_size(
        effect_size=req.expected_effect_size,
        alpha=req.alpha,
        power=req.power,
        groups=groups,
        test_type=test_type,
    )

    confounds = identify_confounds(req.independent_vars, req.dependent_vars)

    methodology = _build_methodology(req, design, sample)
    controls = _build_controls(req)

    return {
        "research_question": req.research_question,
        "hypothesis": req.hypothesis,
        "design": {
            "type": design["name"],
            "suited_for": design["suited_for"],
            "independent_variables": req.independent_vars,
            "dependent_variables": req.dependent_vars,
            "groups": groups,
        },
        "sample_size": sample,
        "methodology": methodology,
        "controls": controls,
        "potential_confounds": confounds,
        "statistical_plan": {
            "primary_test": test_type.replace("_", " ").title(),
            "alpha": req.alpha,
            "power": req.power,
            "effect_size": req.expected_effect_size,
            "corrections": "Bonferroni" if len(req.dependent_vars) > 1 else "None required",
        },
    }


def _build_methodology(req: ExperimentRequest, design: dict, sample: dict) -> list[dict]:
    steps = [
        {
            "step": 1,
            "phase": "Recruitment",
            "description": f"Recruit {sample['total_n']} participants meeting inclusion criteria.",
            "details": "Screen for eligibility, obtain informed consent, collect baseline demographics.",
        },
        {
            "step": 2,
            "phase": "Randomization",
            "description": f"Randomly assign participants to {sample['groups']} groups.",
            "details": "Use block randomization stratified by key covariates.",
        },
        {
            "step": 3,
            "phase": "Baseline measurement",
            "description": f"Measure all dependent variables: {', '.join(req.dependent_vars)}.",
            "details": "Establish pre-intervention baselines for within-subject comparisons.",
        },
        {
            "step": 4,
            "phase": "Intervention",
            "description": f"Apply levels of {', '.join(req.independent_vars)} per group assignment.",
            "details": f"Follow {design['name']} protocol; maintain blinding where possible.",
        },
        {
            "step": 5,
            "phase": "Data collection",
            "description": "Collect outcome measures at pre-specified time points.",
            "details": "Use validated instruments; ensure inter-rater reliability > 0.80.",
        },
        {
            "step": 6,
            "phase": "Analysis",
            "description": "Analyze data per the pre-registered statistical plan.",
            "details": "Check assumptions, run primary and sensitivity analyses, report effect sizes.",
        },
    ]
    return steps


def _build_controls(req: ExperimentRequest) -> list[dict]:
    controls = [
        {
            "type": "Negative control",
            "description": "Group receiving no intervention or placebo to establish baseline.",
        },
        {
            "type": "Randomization",
            "description": "Random group assignment to minimize selection bias.",
        },
        {
            "type": "Blinding",
            "description": "Single or double-blind where feasible to reduce expectation effects.",
        },
    ]

    if len(req.independent_vars) > 1:
        controls.append({
            "type": "Counterbalancing",
            "description": "Vary the order of conditions to control for order effects.",
        })

    return controls
