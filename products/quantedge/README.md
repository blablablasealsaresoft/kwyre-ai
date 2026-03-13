# QuantEdge

**AI-Powered Quantitative Finance**

> Institutional-grade quantitative analytics delivered through a modern API. Options pricing, portfolio optimization, risk management, and alpha signal generation — all in one platform.

Built by [Mint Rail LLC](https://mintrail.com).

---

## Features

### Options Pricing
Black-Scholes pricing engine with full Greeks computation (delta, gamma, theta, vega, rho) for European calls and puts.

### Portfolio Optimization
Markowitz mean-variance optimization with configurable constraints. Computes optimal asset weights, expected return, portfolio volatility, and Sharpe ratio.

### Risk Management
Value-at-Risk (VaR) and Conditional VaR (CVaR) via historical simulation and parametric (normal) methods. Includes maximum drawdown calculation and Monte Carlo simulation support.

### Alpha Signal Generation
Momentum and mean-reversion signal generators for systematic trading strategies.

### Backtesting Engine
Run strategies against historical return series with configurable initial capital, producing equity curves, trade logs, and performance metrics.

### Real-Time Market Data
WebSocket endpoint for streaming simulated market data with sub-second latency.

---

## Tech Stack

- **Python 3.11+**
- **FastAPI** — async API framework
- **NumPy / SciPy** — numerical computing and optimization
- **pandas** — time-series data handling
- **Pydantic** — request/response validation
- **uvicorn** — ASGI server

---

## Quickstart

```bash
cd products/quantedge
pip install -r requirements.txt
uvicorn server.app:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Visit `/docs` for interactive Swagger documentation.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/price/options` | Black-Scholes options pricing with Greeks |
| `POST` | `/v1/portfolio/optimize` | Markowitz mean-variance optimization |
| `POST` | `/v1/risk/var` | VaR / CVaR calculation |
| `POST` | `/v1/signals/alpha` | Alpha signal generation |
| `POST` | `/v1/backtest/run` | Strategy backtesting |
| `WS` | `/ws/market` | Real-time market data stream |

### Example: Price an Option

```bash
curl -X POST http://localhost:8000/v1/price/options \
  -H "Content-Type: application/json" \
  -d '{
    "spot": 100,
    "strike": 105,
    "rate": 0.05,
    "time_to_expiry": 0.25,
    "volatility": 0.2,
    "option_type": "call"
  }'
```

Response:

```json
{
  "price": 2.4634,
  "delta": 0.3842,
  "gamma": 0.0354,
  "theta": -0.0452,
  "vega": 0.1769,
  "rho": 0.0873
}
```

### Example: Optimize a Portfolio

```bash
curl -X POST http://localhost:8000/v1/portfolio/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "expected_returns": [0.12, 0.10, 0.07],
    "covariance_matrix": [
      [0.04, 0.006, 0.002],
      [0.006, 0.09, 0.009],
      [0.002, 0.009, 0.01]
    ],
    "risk_free_rate": 0.03,
    "allow_short_selling": false
  }'
```

### Example: Calculate VaR

```bash
curl -X POST http://localhost:8000/v1/risk/var \
  -H "Content-Type: application/json" \
  -d '{
    "returns": [0.01, -0.02, 0.03, -0.01, 0.005, -0.03, 0.02],
    "confidence_level": 0.95,
    "method": "historical"
  }'
```

---

## Static Site

The `site/` directory contains a static landing page with a Bloomberg-terminal aesthetic. Deploy to any static hosting provider or Cloudflare Pages using the included `wrangler.toml`.

---

## License

Proprietary — Mint Rail LLC. All rights reserved.
