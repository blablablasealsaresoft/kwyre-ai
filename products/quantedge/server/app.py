"""
QuantEdge API — AI-Powered Quantitative Finance
"""

import asyncio
import json
import math
import random
import sys
import os

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .pricing import black_scholes
from .portfolio import optimize_portfolio
from .risk import historical_var, parametric_var, monte_carlo_var

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from products._shared.ai_engine import AIEngine
from products._shared.analytics import monte_carlo_forecast, regime_detection, bollinger_bands, confidence_interval

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


# ── AI Engine ─────────────────────────────────────────────────────────────────

ai = AIEngine(
    default_system=(
        "You are QuantEdge AI, an elite quantitative finance analyst. "
        "Provide institutional-grade market analysis with specific data points, "
        "probability assessments, and actionable trade recommendations. "
        "Use proper financial terminology."
    ),
)


# ── AI Request Models ─────────────────────────────────────────────────────────

class MarketCommentaryRequest(BaseModel):
    prices: list[float] = Field(..., min_length=2, description="Recent price series")
    symbol: str = Field("SPY", description="Ticker symbol")
    timeframe: str = Field("1D", description="Timeframe for context, e.g. 1D, 1W, 1M")


class TradeIdeasRequest(BaseModel):
    holdings: list[dict] = Field(..., description="Current portfolio holdings [{symbol, weight, return}]")
    market_conditions: str = Field("neutral", description="Current market outlook")
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    cash_available: float = Field(0.0, ge=0, description="Cash available for new positions")


class RiskNarrativeRequest(BaseModel):
    returns: list[float] = Field(..., min_length=2, description="Historical return series")
    confidence_level: float = Field(0.95, gt=0, lt=1)
    portfolio_value: float = Field(100_000, gt=0, description="Total portfolio value in USD")
    holdings: list[dict] = Field(default_factory=list, description="Portfolio holdings for context")


class ForecastRequest(BaseModel):
    prices: list[float] = Field(..., min_length=5, description="Historical price series")
    horizon: int = Field(30, gt=0, le=365, description="Forecast horizon in days")
    simulations: int = Field(1000, gt=100, le=50000)
    confidence: float = Field(0.95, gt=0, lt=1)


class RegimeRequest(BaseModel):
    returns: list[float] = Field(..., min_length=61, description="Daily return series")
    window: int = Field(60, gt=10)
    vol_threshold: float = Field(0.02, gt=0)


class BandsRequest(BaseModel):
    prices: list[float] = Field(..., min_length=5, description="Price series")
    window: int = Field(20, gt=2)
    num_std: float = Field(2.0, gt=0)


# ── AI-Powered Endpoints ─────────────────────────────────────────────────────

@app.post("/v1/ai/market-commentary")
async def ai_market_commentary(req: MarketCommentaryRequest):
    prices = np.array(req.prices)
    current = float(prices[-1])
    returns = np.diff(prices) / prices[:-1]
    mean_ret = float(returns.mean())
    vol = float(returns.std())
    total_ret = float((prices[-1] - prices[0]) / prices[0])
    high = float(prices.max())
    low = float(prices.min())

    metrics = {
        "symbol": req.symbol,
        "current_price": round(current, 2),
        "period_return": round(total_ret * 100, 2),
        "mean_daily_return": round(mean_ret * 100, 4),
        "daily_volatility": round(vol * 100, 4),
        "annualized_volatility": round(vol * math.sqrt(252) * 100, 2),
        "period_high": round(high, 2),
        "period_low": round(low, 2),
        "data_points": len(req.prices),
    }

    prompt = (
        f"Generate a professional market commentary for {req.symbol}.\n\n"
        f"Data ({req.timeframe} timeframe, {len(req.prices)} data points):\n"
        f"- Current price: ${current:.2f}\n"
        f"- Period return: {total_ret*100:.2f}%\n"
        f"- Daily volatility: {vol*100:.4f}% (annualized: {vol*math.sqrt(252)*100:.2f}%)\n"
        f"- Period high: ${high:.2f}, Low: ${low:.2f}\n"
        f"- Trend: {'Bullish' if mean_ret > 0 else 'Bearish'} bias with "
        f"{'high' if vol > 0.02 else 'moderate' if vol > 0.01 else 'low'} volatility\n\n"
        f"Provide: 1) Market overview, 2) Technical assessment, 3) Key levels, 4) Near-term outlook."
    )

    response = await ai.complete(prompt)
    result = {"metrics": metrics}
    if response.ok:
        result["commentary"] = response.text
        result["ai_model"] = response.model
    else:
        result["commentary"] = None
        result["ai_note"] = response.error or "AI analysis unavailable"
    return result


@app.post("/v1/ai/trade-ideas")
async def ai_trade_ideas(req: TradeIdeasRequest):
    holdings_summary = "\n".join(
        f"  - {h.get('symbol', '?')}: {h.get('weight', 0)*100:.1f}% weight, "
        f"{h.get('return', 0)*100:.2f}% return"
        for h in req.holdings
    )
    total_weight = sum(h.get("weight", 0) for h in req.holdings)

    prompt = (
        f"Generate actionable trade ideas for a {req.risk_tolerance} investor.\n\n"
        f"Current Portfolio ({len(req.holdings)} positions, {total_weight*100:.1f}% invested):\n"
        f"{holdings_summary}\n\n"
        f"Market Conditions: {req.market_conditions}\n"
        f"Cash Available: ${req.cash_available:,.2f}\n\n"
        f"Provide: 1) Portfolio assessment, 2) 3-5 specific trade ideas with entry/exit levels, "
        f"3) Position sizing suggestions, 4) Risk management notes."
    )

    context = {
        "total_positions": len(req.holdings),
        "total_weight": round(total_weight, 4),
        "risk_tolerance": req.risk_tolerance,
        "market_conditions": req.market_conditions,
        "cash_available": req.cash_available,
    }

    response = await ai.complete(prompt)
    result = {"context": context}
    if response.ok:
        result["trade_ideas"] = response.text
        result["ai_model"] = response.model
    else:
        result["trade_ideas"] = None
        result["ai_note"] = response.error or "AI analysis unavailable"
    return result


@app.post("/v1/ai/risk-narrative")
async def ai_risk_narrative(req: RiskNarrativeRequest):
    returns = np.array(req.returns)
    sorted_rets = np.sort(returns)
    n = len(returns)

    var_idx = int(n * (1 - req.confidence_level))
    var_value = float(-sorted_rets[var_idx]) if var_idx < n else 0.0
    tail = sorted_rets[:var_idx + 1]
    cvar_value = float(-tail.mean()) if len(tail) > 0 else var_value

    mean_ret = float(returns.mean())
    vol = float(returns.std())
    sharpe = (mean_ret / vol * math.sqrt(252)) if vol > 0 else 0.0

    equity = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(equity)
    max_dd = float(((running_max - equity) / running_max).max())

    dollar_var = var_value * req.portfolio_value
    dollar_cvar = cvar_value * req.portfolio_value

    risk_metrics = {
        "var": round(var_value, 6),
        "cvar": round(cvar_value, 6),
        "dollar_var": round(dollar_var, 2),
        "dollar_cvar": round(dollar_cvar, 2),
        "max_drawdown": round(max_dd, 6),
        "annualized_vol": round(vol * math.sqrt(252), 6),
        "sharpe_ratio": round(sharpe, 4),
        "confidence_level": req.confidence_level,
        "portfolio_value": req.portfolio_value,
    }

    holdings_info = ""
    if req.holdings:
        holdings_info = "\nPortfolio holdings:\n" + "\n".join(
            f"  - {h.get('symbol', '?')}: {h.get('weight', 0)*100:.1f}%"
            for h in req.holdings
        )

    prompt = (
        f"Generate a plain-English risk narrative for a ${req.portfolio_value:,.0f} portfolio.\n\n"
        f"Risk Metrics ({req.confidence_level*100:.0f}% confidence):\n"
        f"- Value at Risk (VaR): {var_value*100:.2f}% (${dollar_var:,.0f})\n"
        f"- Conditional VaR (CVaR): {cvar_value*100:.2f}% (${dollar_cvar:,.0f})\n"
        f"- Max Drawdown: {max_dd*100:.2f}%\n"
        f"- Annualized Volatility: {vol*math.sqrt(252)*100:.2f}%\n"
        f"- Sharpe Ratio: {sharpe:.4f}\n"
        f"{holdings_info}\n\n"
        f"Provide: 1) Risk summary in plain English for a non-technical stakeholder, "
        f"2) What the VaR/CVaR means in practical terms, "
        f"3) Stress scenario analysis, 4) Risk mitigation recommendations."
    )

    response = await ai.complete(prompt)
    result = {"risk_metrics": risk_metrics}
    if response.ok:
        result["narrative"] = response.text
        result["ai_model"] = response.model
    else:
        result["narrative"] = None
        result["ai_note"] = response.error or "AI analysis unavailable"
    return result


# ── Predictive Analytics Endpoints ───────────────────────────────────────────

@app.post("/v1/predict/forecast")
async def predict_forecast(req: ForecastRequest):
    result = monte_carlo_forecast(
        prices=req.prices,
        horizon=req.horizon,
        simulations=req.simulations,
        confidence=req.confidence,
    )
    ci = confidence_interval(req.prices)
    return {
        "mean_path": result.mean_path,
        "upper_bound": result.upper_bound,
        "lower_bound": result.lower_bound,
        "percentiles": result.percentiles,
        "confidence": result.confidence,
        "simulations": result.simulations,
        "horizon": result.horizon,
        "current_price": req.prices[-1],
        "forecast_end_mean": result.mean_path[-1],
        "price_confidence_interval": ci,
    }


@app.post("/v1/predict/regime")
async def predict_regime(req: RegimeRequest):
    regimes = regime_detection(
        returns=req.returns,
        window=req.window,
        vol_threshold=req.vol_threshold,
    )

    regime_counts: dict[str, int] = {}
    for r in regimes:
        regime_counts[r["regime"]] = regime_counts.get(r["regime"], 0) + 1

    current_regime = regimes[-1]["regime"] if regimes else "unknown"

    return {
        "regimes": regimes,
        "current_regime": current_regime,
        "regime_summary": regime_counts,
        "total_periods": len(regimes),
        "window": req.window,
        "vol_threshold": req.vol_threshold,
    }


@app.post("/v1/predict/bands")
async def predict_bands(req: BandsRequest):
    bands = bollinger_bands(
        values=req.prices,
        window=req.window,
        num_std=req.num_std,
    )

    current_price = req.prices[-1]
    upper_val = bands["upper"][-1]
    lower_val = bands["lower"][-1]
    middle_val = bands["middle"][-1]

    if upper_val is not None and lower_val is not None and middle_val is not None:
        bandwidth = (upper_val - lower_val) / middle_val if middle_val != 0 else 0
        pct_b = (current_price - lower_val) / (upper_val - lower_val) if (upper_val - lower_val) != 0 else 0.5
    else:
        bandwidth = 0
        pct_b = 0.5

    return {
        "middle": bands["middle"],
        "upper": bands["upper"],
        "lower": bands["lower"],
        "current_price": current_price,
        "bandwidth": round(bandwidth, 6),
        "percent_b": round(pct_b, 6),
        "window": req.window,
        "num_std": req.num_std,
        "signal": "overbought" if pct_b > 1.0 else "oversold" if pct_b < 0.0 else "neutral",
    }
