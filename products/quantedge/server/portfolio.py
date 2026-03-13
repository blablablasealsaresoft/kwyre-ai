"""
Markowitz mean-variance portfolio optimization.
"""

import numpy as np
from scipy.optimize import minimize


def optimize_portfolio(
    expected_returns: list[float],
    covariance_matrix: list[list[float]],
    risk_free_rate: float = 0.0,
    allow_short_selling: bool = False,
) -> dict:
    """
    Find the maximum-Sharpe-ratio portfolio via mean-variance optimization.

    Parameters
    ----------
    expected_returns : list[float]
        Expected return for each asset.
    covariance_matrix : list[list[float]]
        N x N covariance matrix of asset returns.
    risk_free_rate : float
        Risk-free rate for Sharpe ratio calculation.
    allow_short_selling : bool
        If False, constrains all weights >= 0.

    Returns
    -------
    dict
        optimal_weights, expected_return, volatility, sharpe_ratio
    """
    mu = np.array(expected_returns)
    cov = np.array(covariance_matrix)
    n = len(mu)

    def neg_sharpe(weights):
        port_return = weights @ mu
        port_vol = np.sqrt(weights @ cov @ weights)
        if port_vol == 0:
            return 0.0
        return -(port_return - risk_free_rate) / port_vol

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = None if allow_short_selling else [(0.0, 1.0)] * n
    x0 = np.ones(n) / n

    result = minimize(
        neg_sharpe,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-12},
    )

    weights = result.x
    port_return = float(weights @ mu)
    port_vol = float(np.sqrt(weights @ cov @ weights))
    sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0.0

    return {
        "optimal_weights": [round(w, 6) for w in weights],
        "expected_return": round(port_return, 6),
        "volatility": round(port_vol, 6),
        "sharpe_ratio": round(sharpe, 6),
    }


def efficient_frontier(
    expected_returns: list[float],
    covariance_matrix: list[list[float]],
    points: int = 50,
    allow_short_selling: bool = False,
) -> list[dict]:
    """
    Compute the efficient frontier as a series of (return, volatility) points.
    """
    mu = np.array(expected_returns)
    cov = np.array(covariance_matrix)
    n = len(mu)

    target_returns = np.linspace(mu.min(), mu.max(), points)
    frontier = []

    for target in target_returns:
        def portfolio_vol(weights):
            return np.sqrt(weights @ cov @ weights)

        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
            {"type": "eq", "fun": lambda w, t=target: w @ mu - t},
        ]
        bounds = None if allow_short_selling else [(0.0, 1.0)] * n
        x0 = np.ones(n) / n

        result = minimize(
            portfolio_vol, x0, method="SLSQP",
            bounds=bounds, constraints=constraints,
        )

        if result.success:
            frontier.append({
                "expected_return": round(float(target), 6),
                "volatility": round(float(result.fun), 6),
                "weights": [round(w, 6) for w in result.x],
            })

    return frontier
