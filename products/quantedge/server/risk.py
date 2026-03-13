"""
Risk analytics: VaR, CVaR, Monte Carlo simulation, drawdown analysis.
"""

import numpy as np


def historical_var(
    returns: list[float],
    confidence_level: float = 0.95,
) -> dict:
    """
    Historical simulation VaR and CVaR.

    Sorts observed returns and picks the percentile cutoff.
    CVaR is the mean of losses beyond the VaR threshold.
    """
    r = np.array(returns)
    alpha = 1 - confidence_level

    var = float(-np.percentile(r, alpha * 100))
    losses_beyond = r[r <= -var]
    cvar = float(-losses_beyond.mean()) if len(losses_beyond) > 0 else var
    mdd = _max_drawdown(r)

    return {
        "var": round(var, 6),
        "cvar": round(cvar, 6),
        "max_drawdown": round(mdd, 6),
        "method": "historical",
        "confidence_level": confidence_level,
        "observations": len(r),
    }


def parametric_var(
    returns: list[float],
    confidence_level: float = 0.95,
) -> dict:
    """
    Parametric (variance-covariance) VaR and CVaR assuming normal distribution.
    """
    from scipy.stats import norm

    r = np.array(returns)
    mu = float(r.mean())
    sigma = float(r.std(ddof=1))

    z = norm.ppf(1 - confidence_level)
    var = -(mu + z * sigma)

    pdf_z = norm.pdf(z)
    cvar = -(mu - sigma * pdf_z / (1 - confidence_level))
    mdd = _max_drawdown(r)

    return {
        "var": round(var, 6),
        "cvar": round(cvar, 6),
        "max_drawdown": round(mdd, 6),
        "method": "parametric",
        "confidence_level": confidence_level,
        "mean_return": round(mu, 6),
        "std_return": round(sigma, 6),
    }


def monte_carlo_var(
    returns: list[float],
    confidence_level: float = 0.95,
    simulations: int = 10_000,
    horizon: int = 1,
) -> dict:
    """
    Monte Carlo VaR: simulate future portfolio paths from fitted distribution.
    """
    r = np.array(returns)
    mu = float(r.mean())
    sigma = float(r.std(ddof=1))

    rng = np.random.default_rng(42)
    sim_returns = rng.normal(mu, sigma, size=(simulations, horizon))
    cumulative = sim_returns.sum(axis=1)

    alpha = 1 - confidence_level
    var = float(-np.percentile(cumulative, alpha * 100))
    losses_beyond = cumulative[cumulative <= -var]
    cvar = float(-losses_beyond.mean()) if len(losses_beyond) > 0 else var

    return {
        "var": round(var, 6),
        "cvar": round(cvar, 6),
        "method": "monte_carlo",
        "confidence_level": confidence_level,
        "simulations": simulations,
        "horizon_days": horizon,
    }


def _max_drawdown(returns: np.ndarray) -> float:
    """Compute maximum drawdown from a return series."""
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    return float(-drawdowns.min()) if len(drawdowns) > 0 else 0.0
