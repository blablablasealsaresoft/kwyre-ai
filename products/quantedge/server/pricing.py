"""
Black-Scholes options pricing engine with full Greeks computation.
"""

import math
from scipy.stats import norm


def black_scholes(
    spot: float,
    strike: float,
    rate: float,
    time_to_expiry: float,
    volatility: float,
    option_type: str = "call",
) -> dict:
    """
    Compute Black-Scholes price and Greeks for a European option.

    Parameters
    ----------
    spot : float
        Current price of the underlying asset.
    strike : float
        Option strike price.
    rate : float
        Risk-free interest rate (annualized, e.g. 0.05 for 5%).
    time_to_expiry : float
        Time to expiration in years (e.g. 0.25 for 3 months).
    volatility : float
        Annualized volatility of the underlying (e.g. 0.2 for 20%).
    option_type : str
        "call" or "put".

    Returns
    -------
    dict
        price, delta, gamma, theta, vega, rho
    """
    if time_to_expiry <= 0:
        intrinsic = max(spot - strike, 0.0) if option_type == "call" else max(strike - spot, 0.0)
        return {
            "price": intrinsic,
            "delta": 1.0 if (option_type == "call" and spot > strike) else (-1.0 if option_type == "put" and strike > spot else 0.0),
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
        }

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    nd1 = norm.cdf(d1)
    nd2 = norm.cdf(d2)
    n_neg_d1 = norm.cdf(-d1)
    n_neg_d2 = norm.cdf(-d2)
    pdf_d1 = norm.pdf(d1)

    discount = math.exp(-rate * time_to_expiry)

    if option_type == "call":
        price = spot * nd1 - strike * discount * nd2
        delta = nd1
        theta = (
            -(spot * pdf_d1 * volatility) / (2 * sqrt_t)
            - rate * strike * discount * nd2
        )
        rho = strike * time_to_expiry * discount * nd2
    else:
        price = strike * discount * n_neg_d2 - spot * n_neg_d1
        delta = nd1 - 1.0
        theta = (
            -(spot * pdf_d1 * volatility) / (2 * sqrt_t)
            + rate * strike * discount * n_neg_d2
        )
        rho = -strike * time_to_expiry * discount * n_neg_d2

    gamma = pdf_d1 / (spot * volatility * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t

    return {
        "price": round(price, 6),
        "delta": round(delta, 6),
        "gamma": round(gamma, 6),
        "theta": round(theta / 365, 6),  # per-day theta
        "vega": round(vega / 100, 6),    # per 1% vol move
        "rho": round(rho / 100, 6),      # per 1% rate move
    }
