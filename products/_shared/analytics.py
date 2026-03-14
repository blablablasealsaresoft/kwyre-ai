"""
Shared Predictive Analytics — Monte Carlo, regression, time series utilities.

Used by QuantEdge, NFL PlayCaller, MarchMind, and other products needing
statistical forecasting and predictive modeling.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ForecastResult:
    mean_path: list[float]
    upper_bound: list[float]
    lower_bound: list[float]
    confidence: float
    simulations: int
    horizon: int
    percentiles: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class RegressionResult:
    coefficients: list[float]
    intercept: float
    r_squared: float
    predictions: list[float]
    residuals: list[float]


def monte_carlo_forecast(
    prices: list[float],
    horizon: int = 30,
    simulations: int = 1000,
    confidence: float = 0.95,
) -> ForecastResult:
    """GBM-based Monte Carlo price simulation."""
    arr = np.array(prices, dtype=float)
    log_returns = np.diff(np.log(arr))
    mu = float(log_returns.mean())
    sigma = float(log_returns.std())

    if sigma == 0:
        sigma = 0.01

    last_price = float(arr[-1])
    dt = 1.0

    all_paths = np.zeros((simulations, horizon))
    for i in range(simulations):
        path = [last_price]
        for _ in range(horizon):
            shock = np.random.normal(0, 1)
            price = path[-1] * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * shock)
            path.append(price)
        all_paths[i] = path[1:]

    mean_path = np.mean(all_paths, axis=0)
    alpha = (1 - confidence) / 2
    lower = np.percentile(all_paths, alpha * 100, axis=0)
    upper = np.percentile(all_paths, (1 - alpha) * 100, axis=0)

    return ForecastResult(
        mean_path=[round(float(v), 2) for v in mean_path],
        upper_bound=[round(float(v), 2) for v in upper],
        lower_bound=[round(float(v), 2) for v in lower],
        confidence=confidence,
        simulations=simulations,
        horizon=horizon,
        percentiles={
            "p10": [round(float(v), 2) for v in np.percentile(all_paths, 10, axis=0)],
            "p25": [round(float(v), 2) for v in np.percentile(all_paths, 25, axis=0)],
            "p50": [round(float(v), 2) for v in np.percentile(all_paths, 50, axis=0)],
            "p75": [round(float(v), 2) for v in np.percentile(all_paths, 75, axis=0)],
            "p90": [round(float(v), 2) for v in np.percentile(all_paths, 90, axis=0)],
        },
    )


def linear_regression(x: list[float], y: list[float]) -> RegressionResult:
    """Simple OLS linear regression."""
    xa = np.array(x, dtype=float)
    ya = np.array(y, dtype=float)
    n = len(xa)

    x_mean = xa.mean()
    y_mean = ya.mean()

    ss_xy = float(np.sum((xa - x_mean) * (ya - y_mean)))
    ss_xx = float(np.sum((xa - x_mean) ** 2))

    if ss_xx == 0:
        return RegressionResult(
            coefficients=[0.0], intercept=float(y_mean),
            r_squared=0.0, predictions=[float(y_mean)] * n,
            residuals=[float(v - y_mean) for v in ya],
        )

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    predictions = [float(slope * xi + intercept) for xi in xa]
    residuals = [float(ya[i] - predictions[i]) for i in range(n)]

    ss_res = sum(r**2 for r in residuals)
    ss_tot = float(np.sum((ya - y_mean) ** 2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return RegressionResult(
        coefficients=[round(slope, 6)],
        intercept=round(intercept, 6),
        r_squared=round(r_squared, 6),
        predictions=[round(p, 4) for p in predictions],
        residuals=[round(r, 4) for r in residuals],
    )


def moving_average(values: list[float], window: int = 20) -> list[float | None]:
    """Simple moving average with None padding for incomplete windows."""
    result: list[float | None] = [None] * min(window - 1, len(values))
    arr = np.array(values, dtype=float)
    for i in range(window - 1, len(arr)):
        result.append(round(float(arr[i - window + 1 : i + 1].mean()), 4))
    return result


def exponential_moving_average(values: list[float], span: int = 20) -> list[float]:
    """EMA with the given span."""
    alpha = 2 / (span + 1)
    ema = [float(values[0])]
    for v in values[1:]:
        ema.append(alpha * v + (1 - alpha) * ema[-1])
    return [round(v, 4) for v in ema]


def bollinger_bands(
    values: list[float], window: int = 20, num_std: float = 2.0
) -> dict[str, list[float | None]]:
    """Bollinger Bands."""
    arr = np.array(values, dtype=float)
    n = len(arr)
    middle: list[float | None] = []
    upper: list[float | None] = []
    lower: list[float | None] = []

    for i in range(n):
        if i < window - 1:
            middle.append(None)
            upper.append(None)
            lower.append(None)
        else:
            w = arr[i - window + 1 : i + 1]
            m = float(w.mean())
            s = float(w.std())
            middle.append(round(m, 4))
            upper.append(round(m + num_std * s, 4))
            lower.append(round(m - num_std * s, 4))

    return {"middle": middle, "upper": upper, "lower": lower}


def regime_detection(
    returns: list[float], window: int = 60, vol_threshold: float = 0.02
) -> list[dict]:
    """Simple volatility-based regime detection."""
    arr = np.array(returns, dtype=float)
    regimes = []

    for i in range(window, len(arr)):
        w = arr[i - window : i]
        vol = float(w.std())
        mean_ret = float(w.mean())

        if vol > vol_threshold:
            regime = "high_volatility"
        elif mean_ret > 0.001:
            regime = "bull"
        elif mean_ret < -0.001:
            regime = "bear"
        else:
            regime = "sideways"

        regimes.append({
            "index": i,
            "regime": regime,
            "volatility": round(vol, 6),
            "mean_return": round(mean_ret, 6),
        })

    return regimes


def win_probability(
    score_diff: int,
    time_remaining_seconds: int,
    possession: bool = False,
    sport: str = "nfl",
) -> float:
    """Logistic model win probability estimate."""
    if sport == "nfl":
        total_seconds = 3600
        time_factor = time_remaining_seconds / total_seconds
        possession_bonus = 3.0 if possession else 0.0
        effective_lead = score_diff + possession_bonus

        k = 0.15 + 0.35 * (1 - time_factor)
        prob = 1 / (1 + math.exp(-k * effective_lead))
    else:
        prob = 1 / (1 + math.exp(-0.2 * score_diff))

    return round(min(max(prob, 0.01), 0.99), 4)


def confidence_interval(
    values: list[float], confidence: float = 0.95
) -> dict[str, float]:
    """Compute confidence interval for a sample."""
    arr = np.array(values, dtype=float)
    n = len(arr)
    mean = float(arr.mean())
    se = float(arr.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0

    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(confidence, 1.96)

    return {
        "mean": round(mean, 6),
        "lower": round(mean - z * se, 6),
        "upper": round(mean + z * se, 6),
        "std_error": round(se, 6),
        "confidence": confidence,
        "n": n,
    }
