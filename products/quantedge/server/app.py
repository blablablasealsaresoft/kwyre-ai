"""
QuantEdge API — AI-Powered Quantitative Finance
"""

import asyncio
import json
import math
import random

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .pricing import black_scholes
from .portfolio import optimize_portfolio
from .risk import historical_var, parametric_var, monte_carlo_var

app = FastAPI(
    title="QuantEdge API",
    description="AI-Powered Quantitative Finance by Mint Rail LLC",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class OptionPriceRequest(BaseModel):
    spot: float = Field(..., gt=0, description="Current underlying price")
    strike: float = Field(..., gt=0, description="Strike price")
    rate: float = Field(..., description="Risk-free rate (annualized)")
    time_to_expiry: float = Field(..., gt=0, description="Years to expiration")
    volatility: float = Field(..., gt=0, description="Annualized volatility")
    option_type: str = Field("call", pattern="^(call|put)$")


class PortfolioOptRequest(BaseModel):
    expected_returns: list[float]
    covariance_matrix: list[list[float]]
    risk_free_rate: float = 0.0
    allow_short_selling: bool = False


class VaRRequest(BaseModel):
    returns: list[float] = Field(..., min_length=2)
    confidence_level: float = Field(0.95, gt=0, lt=1)
    method: str = Field("historical", pattern="^(historical|parametric|monte_carlo)$")
    simulations: int = Field(10_000, gt=100)
    horizon: int = Field(1, gt=0)


class AlphaSignalRequest(BaseModel):
    prices: list[float] = Field(..., min_length=5)
    lookback: int = Field(20, gt=1)
    strategy: str = Field("momentum", pattern="^(momentum|mean_reversion)$")


class BacktestRequest(BaseModel):
    returns: list[float] = Field(..., min_length=2)
    signal: list[float] | None = None
    initial_capital: float = Field(100_000, gt=0)
    strategy: str = Field("momentum", pattern="^(momentum|mean_reversion|buy_and_hold)$")
    lookback: int = Field(20, gt=1)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "quantedge", "version": "1.0.0"}


@app.post("/v1/price/options")
async def price_options(req: OptionPriceRequest):
    result = black_scholes(
        spot=req.spot,
        strike=req.strike,
        rate=req.rate,
        time_to_expiry=req.time_to_expiry,
        volatility=req.volatility,
        option_type=req.option_type,
    )
    return result


@app.post("/v1/portfolio/optimize")
async def portfolio_optimize(req: PortfolioOptRequest):
    n = len(req.expected_returns)
    if len(req.covariance_matrix) != n or any(len(row) != n for row in req.covariance_matrix):
        return {"error": "Covariance matrix dimensions must match expected_returns length"}
    result = optimize_portfolio(
        expected_returns=req.expected_returns,
        covariance_matrix=req.covariance_matrix,
        risk_free_rate=req.risk_free_rate,
        allow_short_selling=req.allow_short_selling,
    )
    return result


@app.post("/v1/risk/var")
async def risk_var(req: VaRRequest):
    if req.method == "historical":
        return historical_var(req.returns, req.confidence_level)
    elif req.method == "parametric":
        return parametric_var(req.returns, req.confidence_level)
    else:
        return monte_carlo_var(req.returns, req.confidence_level, req.simulations, req.horizon)


@app.post("/v1/signals/alpha")
async def alpha_signals(req: AlphaSignalRequest):
    prices = np.array(req.prices)
    lookback = min(req.lookback, len(prices) - 1)

    if req.strategy == "momentum":
        signals = []
        for i in range(lookback, len(prices)):
            ret = (prices[i] - prices[i - lookback]) / prices[i - lookback]
            signals.append({
                "index": i,
                "price": round(float(prices[i]), 4),
                "signal": round(float(np.sign(ret)), 1),
                "strength": round(float(abs(ret)), 6),
            })
        return {"strategy": "momentum", "lookback": lookback, "signals": signals}

    else:  # mean_reversion
        signals = []
        for i in range(lookback, len(prices)):
            window = prices[i - lookback : i]
            mean = window.mean()
            std = window.std()
            if std == 0:
                z = 0.0
            else:
                z = (prices[i] - mean) / std
            signals.append({
                "index": i,
                "price": round(float(prices[i]), 4),
                "signal": round(float(-np.sign(z)), 1),
                "strength": round(float(abs(z)), 6),
                "z_score": round(float(z), 6),
            })
        return {"strategy": "mean_reversion", "lookback": lookback, "signals": signals}


@app.post("/v1/backtest/run")
async def backtest_run(req: BacktestRequest):
    returns = np.array(req.returns)
    n = len(returns)
    lookback = min(req.lookback, n - 1)

    prices = np.cumprod(1 + returns) * req.initial_capital
    equity = [req.initial_capital]
    positions = []

    for i in range(1, n):
        if req.strategy == "buy_and_hold":
            pos = 1.0
        elif i < lookback:
            pos = 0.0
        elif req.strategy == "momentum":
            window_ret = (prices[i - 1] - prices[max(0, i - lookback)]) / prices[max(0, i - lookback)]
            pos = 1.0 if window_ret > 0 else 0.0
        else:  # mean_reversion
            window = prices[max(0, i - lookback) : i]
            if window.std() == 0:
                pos = 0.0
            else:
                z = (prices[i - 1] - window.mean()) / window.std()
                pos = -1.0 if z > 1.0 else (1.0 if z < -1.0 else 0.0)

        pnl = pos * returns[i] * equity[-1]
        equity.append(equity[-1] + pnl)
        positions.append({"day": i, "position": round(pos, 2), "equity": round(equity[-1], 2)})

    equity_arr = np.array(equity)
    total_return = (equity_arr[-1] - req.initial_capital) / req.initial_capital
    running_max = np.maximum.accumulate(equity_arr)
    drawdowns = (equity_arr - running_max) / running_max
    max_dd = float(-drawdowns.min())

    daily_returns = np.diff(equity_arr) / equity_arr[:-1]
    sharpe = float(daily_returns.mean() / daily_returns.std() * math.sqrt(252)) if daily_returns.std() > 0 else 0.0

    return {
        "strategy": req.strategy,
        "initial_capital": req.initial_capital,
        "final_equity": round(float(equity_arr[-1]), 2),
        "total_return": round(float(total_return), 6),
        "max_drawdown": round(max_dd, 6),
        "sharpe_ratio": round(sharpe, 4),
        "total_days": n,
        "trades": positions[-10:],  # last 10 for brevity
    }


# ── WebSocket: Simulated Market Data Stream ──────────────────────────────────

@app.websocket("/ws/market")
async def market_stream(ws: WebSocket):
    await ws.accept()
    symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "SPY"]
    prices = {s: 100.0 + random.uniform(0, 400) for s in symbols}

    try:
        while True:
            for sym in symbols:
                change_pct = random.gauss(0, 0.002)
                prices[sym] *= (1 + change_pct)
                tick = {
                    "symbol": sym,
                    "price": round(prices[sym], 2),
                    "change": round(change_pct * 100, 4),
                    "volume": random.randint(100, 50_000),
                    "bid": round(prices[sym] * 0.999, 2),
                    "ask": round(prices[sym] * 1.001, 2),
                }
                await ws.send_json(tick)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
