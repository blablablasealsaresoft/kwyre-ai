"""Statistical analysis planner: recommends tests and validates assumptions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DataDescription:
    sample_size: int
    groups: int = 2
    data_type: str = "continuous"       # continuous | ordinal | nominal | count
    paired: bool = False
    normal_distribution: bool | None = None
    equal_variance: bool | None = None
    independent_observations: bool = True


TEST_CATALOG: dict[str, dict] = {
    "independent_t_test": {
        "name": "Independent Samples t-test",
        "family": "parametric",
        "use_case": "Compare means of 2 independent groups",
        "assumptions": [
            "Continuous dependent variable",
            "Independent observations",
            "Approximate normal distribution (or n >= 30 by CLT)",
            "Homogeneity of variance (Levene's test)",
        ],
        "effect_size": "Cohen's d",
        "effect_interpretation": {
            "small": 0.2,
            "medium": 0.5,
            "large": 0.8,
        },
    },
    "paired_t_test": {
        "name": "Paired Samples t-test",
        "family": "parametric",
        "use_case": "Compare means of 2 related/matched measurements",
        "assumptions": [
            "Continuous dependent variable",
            "Paired observations from the same subjects",
            "Differences are approximately normally distributed",
        ],
        "effect_size": "Cohen's d (paired)",
        "effect_interpretation": {
            "small": 0.2,
            "medium": 0.5,
            "large": 0.8,
        },
    },
    "one_way_anova": {
        "name": "One-Way ANOVA",
        "family": "parametric",
        "use_case": "Compare means across 3+ independent groups",
        "assumptions": [
            "Continuous dependent variable",
            "Independent observations",
            "Normal distribution within each group",
            "Homogeneity of variance across groups",
        ],
        "effect_size": "Eta-squared (\u03b7\u00b2) or Omega-squared (\u03c9\u00b2)",
        "effect_interpretation": {
            "small": 0.01,
            "medium": 0.06,
            "large": 0.14,
        },
        "post_hoc": "Tukey HSD or Bonferroni-corrected pairwise comparisons",
    },
    "repeated_measures_anova": {
        "name": "Repeated Measures ANOVA",
        "family": "parametric",
        "use_case": "Compare means across 3+ related measurements",
        "assumptions": [
            "Continuous dependent variable",
            "Paired/repeated observations",
            "Normal distribution of differences",
            "Sphericity (Mauchly's test); use Greenhouse-Geisser correction if violated",
        ],
        "effect_size": "Partial Eta-squared (\u03b7\u00b2p)",
        "effect_interpretation": {
            "small": 0.01,
            "medium": 0.06,
            "large": 0.14,
        },
    },
    "chi_square_independence": {
        "name": "Chi-Square Test of Independence",
        "family": "nonparametric",
        "use_case": "Test association between 2 categorical variables",
        "assumptions": [
            "Categorical (nominal/ordinal) variables",
            "Independent observations",
            "Expected cell counts >= 5 (use Fisher's exact if not)",
        ],
        "effect_size": "Cram\u00e9r's V",
        "effect_interpretation": {
            "small": 0.1,
            "medium": 0.3,
            "large": 0.5,
        },
    },
    "mann_whitney_u": {
        "name": "Mann-Whitney U Test",
        "family": "nonparametric",
        "use_case": "Compare distributions of 2 independent groups (non-normal data)",
        "assumptions": [
            "Ordinal or continuous dependent variable",
            "Independent observations",
            "Similar distribution shapes (for median comparison interpretation)",
        ],
        "effect_size": "Rank-biserial correlation (r)",
        "effect_interpretation": {
            "small": 0.1,
            "medium": 0.3,
            "large": 0.5,
        },
    },
    "wilcoxon_signed_rank": {
        "name": "Wilcoxon Signed-Rank Test",
        "family": "nonparametric",
        "use_case": "Compare 2 related samples when normality is violated",
        "assumptions": [
            "Ordinal or continuous dependent variable",
            "Paired observations",
            "Symmetric distribution of differences (approx.)",
        ],
        "effect_size": "Matched-pairs rank-biserial r",
        "effect_interpretation": {
            "small": 0.1,
            "medium": 0.3,
            "large": 0.5,
        },
    },
    "kruskal_wallis": {
        "name": "Kruskal-Wallis H Test",
        "family": "nonparametric",
        "use_case": "Compare distributions of 3+ independent groups (non-normal data)",
        "assumptions": [
            "Ordinal or continuous dependent variable",
            "Independent observations",
            "Similar distribution shapes across groups",
        ],
        "effect_size": "Epsilon-squared (\u03b5\u00b2)",
        "effect_interpretation": {
            "small": 0.01,
            "medium": 0.06,
            "large": 0.14,
        },
        "post_hoc": "Dunn's test with Bonferroni correction",
    },
    "linear_regression": {
        "name": "Linear Regression",
        "family": "parametric",
        "use_case": "Model relationship between continuous predictor(s) and outcome",
        "assumptions": [
            "Linearity of relationship",
            "Independence of residuals",
            "Homoscedasticity of residuals",
            "Normal distribution of residuals",
            "No multicollinearity (if multiple predictors)",
        ],
        "effect_size": "R\u00b2 (coefficient of determination)",
        "effect_interpretation": {
            "small": 0.02,
            "medium": 0.13,
            "large": 0.26,
        },
    },
    "logistic_regression": {
        "name": "Logistic Regression",
        "family": "parametric",
        "use_case": "Predict binary outcome from one or more predictors",
        "assumptions": [
            "Binary dependent variable",
            "Independence of observations",
            "Linearity of log-odds",
            "No multicollinearity",
            "Adequate sample size (10-20 events per predictor)",
        ],
        "effect_size": "Odds Ratio (OR)",
        "effect_interpretation": {
            "small": 1.5,
            "medium": 2.5,
            "large": 4.0,
        },
    },
}


def recommend_tests(desc: DataDescription) -> dict:
    """Select appropriate statistical tests based on data characteristics."""
    primary: list[dict] = []
    alternatives: list[dict] = []

    is_normal = desc.normal_distribution is not False
    big_enough = desc.sample_size >= 30

    if desc.data_type == "continuous":
        if desc.groups == 2:
            if desc.paired:
                if is_normal or big_enough:
                    primary.append(_build_rec("paired_t_test", "primary"))
                    alternatives.append(_build_rec("wilcoxon_signed_rank", "alternative"))
                else:
                    primary.append(_build_rec("wilcoxon_signed_rank", "primary"))
                    alternatives.append(_build_rec("paired_t_test", "alternative (if normality holds)"))
            else:
                if is_normal or big_enough:
                    primary.append(_build_rec("independent_t_test", "primary"))
                    alternatives.append(_build_rec("mann_whitney_u", "alternative"))
                else:
                    primary.append(_build_rec("mann_whitney_u", "primary"))
                    alternatives.append(_build_rec("independent_t_test", "alternative (if normality holds)"))
        elif desc.groups >= 3:
            if desc.paired:
                if is_normal or big_enough:
                    primary.append(_build_rec("repeated_measures_anova", "primary"))
                else:
                    primary.append(_build_rec("kruskal_wallis", "primary (Friedman preferred for paired)"))
            else:
                if is_normal or big_enough:
                    primary.append(_build_rec("one_way_anova", "primary"))
                    alternatives.append(_build_rec("kruskal_wallis", "alternative"))
                else:
                    primary.append(_build_rec("kruskal_wallis", "primary"))
                    alternatives.append(_build_rec("one_way_anova", "alternative (if normality holds)"))

        alternatives.append(_build_rec("linear_regression", "consider for predictive modeling"))

    elif desc.data_type == "ordinal":
        if desc.groups == 2:
            if desc.paired:
                primary.append(_build_rec("wilcoxon_signed_rank", "primary"))
            else:
                primary.append(_build_rec("mann_whitney_u", "primary"))
        else:
            primary.append(_build_rec("kruskal_wallis", "primary"))

    elif desc.data_type in ("nominal", "count"):
        primary.append(_build_rec("chi_square_independence", "primary"))
        if desc.data_type == "nominal":
            alternatives.append(_build_rec("logistic_regression", "consider for predictive modeling"))

    assumptions_to_check = _assumptions_checklist(desc, primary)

    return {
        "data_summary": {
            "sample_size": desc.sample_size,
            "groups": desc.groups,
            "data_type": desc.data_type,
            "paired": desc.paired,
            "assumed_normal": is_normal,
        },
        "recommended_tests": primary,
        "alternative_tests": alternatives,
        "assumptions_checklist": assumptions_to_check,
        "p_value_guidance": _p_value_guidance(),
        "reporting_template": _reporting_template(primary),
    }


def _build_rec(test_key: str, role: str) -> dict:
    test = TEST_CATALOG[test_key]
    return {
        "test_key": test_key,
        "name": test["name"],
        "role": role,
        "family": test["family"],
        "use_case": test["use_case"],
        "assumptions": test["assumptions"],
        "effect_size_metric": test["effect_size"],
        "effect_size_benchmarks": test["effect_interpretation"],
        "post_hoc": test.get("post_hoc"),
    }


def _assumptions_checklist(desc: DataDescription, primary: list[dict]) -> list[dict]:
    checks = []

    if any(t["family"] == "parametric" for t in primary):
        checks.append({
            "check": "Normality",
            "methods": ["Shapiro-Wilk test (n < 50)", "K-S test", "Q-Q plot visual inspection"],
            "scipy_call": "scipy.stats.shapiro(data)",
            "note": "Less critical when n >= 30 (Central Limit Theorem).",
        })
        checks.append({
            "check": "Homogeneity of variance",
            "methods": ["Levene's test"],
            "scipy_call": "scipy.stats.levene(group1, group2)",
            "note": "If violated, use Welch's t-test or Games-Howell post-hoc.",
        })

    checks.append({
        "check": "Independence",
        "methods": ["Study design review", "Durbin-Watson test for autocorrelation"],
        "scipy_call": None,
        "note": "Violated in clustered, longitudinal, or repeated-measures data.",
    })

    if desc.data_type in ("nominal", "count"):
        checks.append({
            "check": "Expected cell counts",
            "methods": ["Verify all expected frequencies >= 5"],
            "scipy_call": "scipy.stats.chi2_contingency(table)",
            "note": "Use Fisher's exact test if expected counts < 5.",
        })

    return checks


def _p_value_guidance() -> dict:
    return {
        "threshold": 0.05,
        "interpretation": (
            "A p-value below alpha (typically 0.05) suggests the observed effect "
            "is unlikely under the null hypothesis. However, p-values do NOT measure "
            "the probability that the hypothesis is true, the size of the effect, "
            "or the practical importance of the result."
        ),
        "best_practices": [
            "Always report exact p-values (e.g., p = 0.032, not p < 0.05).",
            "Report confidence intervals alongside p-values.",
            "Report effect sizes — statistical significance ≠ practical significance.",
            "Consider pre-registering analyses to avoid p-hacking.",
            "For multiple comparisons, apply corrections (Bonferroni, FDR).",
        ],
    }


def _reporting_template(primary: list[dict]) -> str:
    if not primary:
        return ""
    test = primary[0]
    name = test["name"]
    es = test["effect_size_metric"]
    return (
        f"A {name} was conducted to examine [research question]. "
        f"Results indicated [significant/non-significant] differences, "
        f"[test statistic] = [value], p = [value], {es} = [value]. "
        f"This corresponds to a [small/medium/large] effect per established benchmarks."
    )
