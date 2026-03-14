"""
Predictive analytics engine for Kwyre AI inference servers.

Provides statistical forecasting, pattern analysis, risk assessment,
and document analytics — importable by any serve_*.py backend.

Dependencies: numpy (required), scipy (optional, enables distribution
fitting and advanced statistical tests).  Both are already in
requirements.txt / requirements-inference.txt.
"""

from __future__ import annotations

import math
import re
import warnings
from collections import Counter, defaultdict
from typing import Any

import numpy as np

_SCIPY_AVAILABLE = False
try:
    from scipy import stats as sp_stats
    from scipy.optimize import minimize_scalar
    _SCIPY_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# TimeSeriesPredictor
# ---------------------------------------------------------------------------

class TimeSeriesPredictor:
    """Stateless univariate time-series forecasting toolkit.

    All methods are pure functions — no internal state is mutated,
    making the class safe for concurrent use across threads.
    """

    # -- Holt-Winters exponential smoothing --------------------------------

    @staticmethod
    def _holt_winters(
        data: list[float],
        season_len: int,
        horizon: int,
        alpha: float = 0.3,
        beta: float = 0.1,
        gamma: float = 0.3,
    ) -> list[float]:
        """Additive Holt-Winters triple exponential smoothing."""
        n = len(data)
        if n < 2 * season_len:
            return TimeSeriesPredictor._double_exp(data, horizon, alpha, beta)

        # --- initialisation ---
        level = np.mean(data[:season_len])
        trend = (np.mean(data[season_len : 2 * season_len])
                 - np.mean(data[:season_len])) / season_len
        seasonals = [data[i] - level for i in range(season_len)]

        for i in range(n):
            val = data[i]
            prev_level = level
            level = alpha * (val - seasonals[i % season_len]) + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend
            seasonals[i % season_len] = (
                gamma * (val - level) + (1 - gamma) * seasonals[i % season_len]
            )

        forecasts: list[float] = []
        for h in range(1, horizon + 1):
            forecasts.append(level + h * trend + seasonals[(n + h - 1) % season_len])
        return forecasts

    @staticmethod
    def _double_exp(
        data: list[float],
        horizon: int,
        alpha: float = 0.3,
        beta: float = 0.1,
    ) -> list[float]:
        """Holt's double exponential smoothing (trend, no seasonality)."""
        level = data[0]
        trend = data[1] - data[0] if len(data) > 1 else 0.0
        for val in data:
            prev_level = level
            level = alpha * val + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend
        return [level + h * trend for h in range(1, horizon + 1)]

    # -- Linear regression with confidence intervals -----------------------

    @staticmethod
    def _linear_regression(
        data: list[float], horizon: int, confidence: float = 0.95
    ) -> dict[str, Any]:
        n = len(data)
        x = np.arange(n, dtype=np.float64)
        y = np.asarray(data, dtype=np.float64)
        x_mean, y_mean = x.mean(), y.mean()

        ss_xy = np.sum((x - x_mean) * (y - y_mean))
        ss_xx = np.sum((x - x_mean) ** 2)
        slope = ss_xy / ss_xx if ss_xx != 0 else 0.0
        intercept = y_mean - slope * x_mean

        y_pred = slope * x + intercept
        residuals = y - y_pred
        se = np.sqrt(np.sum(residuals ** 2) / max(n - 2, 1))

        if _SCIPY_AVAILABLE:
            t_crit = sp_stats.t.ppf((1 + confidence) / 2, max(n - 2, 1))
        else:
            t_crit = 1.96  # approximate for large n

        future_x = np.arange(n, n + horizon, dtype=np.float64)
        forecast = (slope * future_x + intercept).tolist()

        margin = t_crit * se * np.sqrt(
            1 + 1 / n + (future_x - x_mean) ** 2 / ss_xx
        )
        return {
            "forecast": forecast,
            "lower": (slope * future_x + intercept - margin).tolist(),
            "upper": (slope * future_x + intercept + margin).tolist(),
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(1 - np.sum(residuals ** 2) / max(np.sum((y - y_mean) ** 2), 1e-12)),
        }

    # -- Moving average ----------------------------------------------------

    @staticmethod
    def _moving_average(data: list[float], window: int = 5) -> list[float]:
        arr = np.asarray(data, dtype=np.float64)
        if len(arr) < window:
            return arr.tolist()
        kernel = np.ones(window) / window
        return np.convolve(arr, kernel, mode="valid").tolist()

    # -- Anomaly detection -------------------------------------------------

    @staticmethod
    def _detect_anomalies(
        data: list[float], z_thresh: float = 2.5, iqr_factor: float = 1.5
    ) -> dict[str, Any]:
        arr = np.asarray(data, dtype=np.float64)
        mean, std = float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else (float(arr.mean()), 0.0)

        z_scores = np.abs((arr - mean) / std) if std > 0 else np.zeros_like(arr)
        z_anomalies = np.where(z_scores > z_thresh)[0].tolist()

        q1, q3 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
        iqr = q3 - q1
        iqr_anomalies = np.where((arr < q1 - iqr_factor * iqr) | (arr > q3 + iqr_factor * iqr))[0].tolist()

        both = sorted(set(z_anomalies) & set(iqr_anomalies))

        return {
            "z_score_indices": z_anomalies,
            "iqr_indices": iqr_anomalies,
            "consensus_indices": both,
            "mean": mean,
            "std": std,
            "q1": q1,
            "q3": q3,
        }

    # -- Public API --------------------------------------------------------

    def predict(
        self,
        data: list[float],
        horizon: int = 5,
        season_len: int | None = None,
        window: int = 5,
    ) -> dict[str, Any]:
        """Generate forecasts, confidence bounds, trend, and anomalies.

        Parameters
        ----------
        data : list[float]
            Historical observations (at least 3 values).
        horizon : int
            Number of future steps to forecast.
        season_len : int | None
            Seasonal period length.  ``None`` disables Holt-Winters
            and falls back to double exponential smoothing.
        window : int
            Moving-average window size.

        Returns
        -------
        dict with keys: hw_forecast, regression, moving_average,
        anomalies, summary.
        """
        if len(data) < 3:
            return {"error": "need at least 3 data points"}

        effective_season = season_len or max(2, len(data) // 4)

        hw = self._holt_winters(data, effective_season, horizon)
        reg = self._linear_regression(data, horizon)
        ma = self._moving_average(data, window)
        anom = self._detect_anomalies(data)

        ensemble = [
            (h + r) / 2 for h, r in zip(hw, reg["forecast"])
        ]

        return {
            "hw_forecast": hw,
            "regression": reg,
            "moving_average": ma,
            "anomalies": anom,
            "ensemble_forecast": ensemble,
            "horizon": horizon,
            "n_observations": len(data),
        }


# ---------------------------------------------------------------------------
# PatternAnalyzer
# ---------------------------------------------------------------------------

class PatternAnalyzer:
    """Stateless pattern / regime / distribution analysis."""

    @staticmethod
    def _autocorrelation(data: list[float], max_lag: int | None = None) -> list[float]:
        arr = np.asarray(data, dtype=np.float64)
        n = len(arr)
        max_lag = max_lag or min(n // 2, 40)
        mean = arr.mean()
        var = np.sum((arr - mean) ** 2)
        if var == 0:
            return [1.0] + [0.0] * (max_lag - 1)
        acf: list[float] = []
        for lag in range(max_lag):
            c = np.sum((arr[: n - lag] - mean) * (arr[lag:] - mean)) / var
            acf.append(float(c))
        return acf

    @staticmethod
    def _detect_regimes(
        data: list[float], min_segment: int = 10
    ) -> list[dict[str, Any]]:
        """Sliding-window mean/variance shift detection (CUSUM-inspired)."""
        arr = np.asarray(data, dtype=np.float64)
        n = len(arr)
        if n < 2 * min_segment:
            return [{"start": 0, "end": n, "mean": float(arr.mean()), "std": float(arr.std())}]

        change_points: list[int] = [0]
        global_mean = arr.mean()

        cusum = np.zeros(n)
        for i in range(1, n):
            cusum[i] = cusum[i - 1] + (arr[i] - global_mean)

        cusum_range = cusum.max() - cusum.min()
        threshold = cusum_range * 0.3 if cusum_range > 0 else 1.0

        for i in range(min_segment, n - min_segment):
            left_mean = arr[max(0, i - min_segment) : i].mean()
            right_mean = arr[i : min(n, i + min_segment)].mean()
            if abs(left_mean - right_mean) > threshold / min_segment:
                if not change_points or i - change_points[-1] >= min_segment:
                    change_points.append(i)
        change_points.append(n)

        regimes: list[dict[str, Any]] = []
        for s, e in zip(change_points, change_points[1:]):
            seg = arr[s:e]
            regimes.append({
                "start": int(s),
                "end": int(e),
                "mean": float(seg.mean()),
                "std": float(seg.std()),
            })
        return regimes

    @staticmethod
    def _correlation_matrix(columns: list[list[float]]) -> dict[str, Any]:
        mat = np.array(columns, dtype=np.float64)
        if mat.shape[0] < 2:
            return {"error": "need at least 2 variables"}
        corr = np.corrcoef(mat)
        return {
            "matrix": corr.tolist(),
            "shape": list(corr.shape),
        }

    @staticmethod
    def _fit_distributions(data: list[float]) -> dict[str, Any]:
        arr = np.asarray(data, dtype=np.float64)
        positive = arr[arr > 0]

        results: dict[str, Any] = {}

        results["normal"] = {"mean": float(arr.mean()), "std": float(arr.std(ddof=1))}

        if _SCIPY_AVAILABLE:
            _, normal_p = sp_stats.normaltest(arr) if len(arr) >= 20 else (0, 1.0)
            results["normal"]["p_value"] = float(normal_p)

            if len(positive) >= 8:
                ln_params = sp_stats.lognorm.fit(positive, floc=0)
                results["lognormal"] = {
                    "shape": float(ln_params[0]),
                    "loc": float(ln_params[1]),
                    "scale": float(ln_params[2]),
                }

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        p_params = sp_stats.pareto.fit(positive, floc=0)
                        results["pareto"] = {
                            "shape": float(p_params[0]),
                            "loc": float(p_params[1]),
                            "scale": float(p_params[2]),
                        }
                    except Exception:
                        results["pareto"] = {"error": "fit failed"}
        else:
            if len(positive) >= 2:
                log_data = np.log(positive)
                results["lognormal"] = {
                    "mu": float(log_data.mean()),
                    "sigma": float(log_data.std(ddof=1)),
                }

        return results

    def analyze(self, data: list[float], extra_columns: list[list[float]] | None = None) -> dict[str, Any]:
        """Identify patterns, fit distributions, and detect regime shifts.

        Parameters
        ----------
        data : list[float]
            Primary series.
        extra_columns : list[list[float]] | None
            Additional series for correlation analysis.

        Returns
        -------
        dict with keys: autocorrelation, regimes, distributions,
        correlation (if extra_columns supplied).
        """
        if len(data) < 4:
            return {"error": "need at least 4 data points"}

        result: dict[str, Any] = {
            "autocorrelation": self._autocorrelation(data),
            "regimes": self._detect_regimes(data),
            "distributions": self._fit_distributions(data),
        }
        if extra_columns:
            all_cols = [data] + extra_columns
            result["correlation"] = self._correlation_matrix(all_cols)
        return result


# ---------------------------------------------------------------------------
# RiskEngine
# ---------------------------------------------------------------------------

class RiskEngine:
    """Stateless financial risk metrics and Monte Carlo simulation."""

    @staticmethod
    def _var_historical(returns: np.ndarray, confidence: float) -> float:
        return float(np.percentile(returns, (1 - confidence) * 100))

    @staticmethod
    def _var_parametric(returns: np.ndarray, confidence: float) -> float:
        mu, sigma = float(returns.mean()), float(returns.std(ddof=1))
        if _SCIPY_AVAILABLE:
            z = sp_stats.norm.ppf(1 - confidence)
        else:
            z = -1.6449 if confidence >= 0.95 else -1.2816
        return mu + z * sigma

    @staticmethod
    def _cvar(returns: np.ndarray, confidence: float) -> float:
        """Conditional VaR (Expected Shortfall)."""
        var = float(np.percentile(returns, (1 - confidence) * 100))
        tail = returns[returns <= var]
        return float(tail.mean()) if len(tail) > 0 else var

    @staticmethod
    def _sharpe(returns: np.ndarray, risk_free: float = 0.0) -> float:
        excess = returns - risk_free
        std = float(excess.std(ddof=1))
        return float(excess.mean() / std) if std > 0 else 0.0

    @staticmethod
    def _sortino(returns: np.ndarray, risk_free: float = 0.0) -> float:
        excess = returns - risk_free
        downside = excess[excess < 0]
        down_std = float(np.sqrt(np.mean(downside ** 2))) if len(downside) > 0 else 0.0
        return float(excess.mean() / down_std) if down_std > 0 else 0.0

    @staticmethod
    def _max_drawdown(returns: np.ndarray) -> float:
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        return float(drawdowns.min()) if len(drawdowns) > 0 else 0.0

    @staticmethod
    def _monte_carlo(
        returns: np.ndarray,
        n_sims: int = 1000,
        horizon: int = 252,
        confidence: float = 0.95,
        rng_seed: int | None = None,
    ) -> dict[str, Any]:
        rng = np.random.default_rng(rng_seed)
        mu, sigma = float(returns.mean()), float(returns.std(ddof=1))
        sims = rng.normal(mu, sigma, size=(n_sims, horizon))
        final_values = np.prod(1 + sims, axis=1)
        return {
            "mean_return": float(final_values.mean() - 1),
            "median_return": float(np.median(final_values) - 1),
            "percentile_5": float(np.percentile(final_values, 5) - 1),
            "percentile_95": float(np.percentile(final_values, 95) - 1),
            "prob_loss": float(np.mean(final_values < 1)),
            "n_simulations": n_sims,
            "horizon": horizon,
        }

    def assess(
        self,
        returns: list[float],
        confidence: float = 0.95,
        risk_free: float = 0.0,
        mc_sims: int = 1000,
        mc_horizon: int = 252,
    ) -> dict[str, Any]:
        """Compute a full suite of risk metrics.

        Parameters
        ----------
        returns : list[float]
            Period returns (e.g. daily log-returns).
        confidence : float
            Confidence level for VaR / CVaR (default 95 %).
        risk_free : float
            Risk-free rate per period for ratio calculations.
        mc_sims : int
            Number of Monte Carlo paths.
        mc_horizon : int
            Simulation horizon in periods (default 252 ≈ 1 trading year).

        Returns
        -------
        dict with keys: var_historical, var_parametric, cvar,
        sharpe, sortino, max_drawdown, monte_carlo.
        """
        if len(returns) < 5:
            return {"error": "need at least 5 return observations"}

        arr = np.asarray(returns, dtype=np.float64)
        return {
            "var_historical": self._var_historical(arr, confidence),
            "var_parametric": self._var_parametric(arr, confidence),
            "cvar": self._cvar(arr, confidence),
            "sharpe": self._sharpe(arr, risk_free),
            "sortino": self._sortino(arr, risk_free),
            "max_drawdown": self._max_drawdown(arr),
            "monte_carlo": self._monte_carlo(arr, mc_sims, mc_horizon, confidence),
            "confidence": confidence,
            "n_observations": len(returns),
        }


# ---------------------------------------------------------------------------
# DocumentAnalytics
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might must can could and but or nor for yet so at by in of "
    "on to from with as into through during before after above below between out "
    "up down about over under again further then once that this these those it its "
    "he she they them their his her him we us our you your i me my not no all any "
    "each every both few more most some such than too very also just how what which "
    "who whom when where why while if because since until although though even still".split()
)

_POSITIVE_WORDS = frozenset(
    "good great excellent amazing wonderful fantastic positive happy joy success "
    "brilliant outstanding awesome superb love best perfect strong impressive "
    "remarkable powerful beneficial gain profit growth improve progress achieve "
    "efficient effective reliable robust innovative superior exceptional".split()
)

_NEGATIVE_WORDS = frozenset(
    "bad poor terrible awful negative sad failure loss worst weak risk danger "
    "problem error fault flaw decline drop crash fall decrease deficit damage "
    "broken failed lacking missing deficient harmful threat vulnerable unstable "
    "concern worry fear doubt struggle burden costly expensive inefficient".split()
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z']{1,}", text.lower())


class DocumentAnalytics:
    """Stateless corpus-level text analytics (keyword-based, no ML deps)."""

    @staticmethod
    def _entity_frequencies(texts: list[str]) -> dict[str, Any]:
        """Capitalized-phrase frequency across all documents."""
        freq: Counter[str] = Counter()
        for text in texts:
            for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text):
                entity = m.group(0)
                if entity.lower() not in _STOP_WORDS:
                    freq[entity] += 1
        return {
            "entities": freq.most_common(50),
            "unique_count": len(freq),
        }

    @staticmethod
    def _sentiment(texts: list[str]) -> dict[str, Any]:
        doc_scores: list[dict[str, Any]] = []
        for idx, text in enumerate(texts):
            tokens = _tokenize(text)
            n = len(tokens) or 1
            pos = sum(1 for t in tokens if t in _POSITIVE_WORDS)
            neg = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
            score = (pos - neg) / n
            doc_scores.append({
                "doc_index": idx,
                "score": round(score, 4),
                "positive_hits": pos,
                "negative_hits": neg,
            })
        scores = [d["score"] for d in doc_scores]
        return {
            "per_document": doc_scores,
            "corpus_mean": round(float(np.mean(scores)), 4) if scores else 0.0,
        }

    @staticmethod
    def _tfidf_keyphrases(texts: list[str], top_n: int = 20) -> list[tuple[str, float]]:
        """Extract key single-word terms via TF-IDF."""
        n_docs = len(texts)
        if n_docs == 0:
            return []

        doc_tokens = [_tokenize(t) for t in texts]
        tf_per_doc: list[Counter[str]] = [Counter(toks) for toks in doc_tokens]

        df: Counter[str] = Counter()
        for tf in tf_per_doc:
            for term in tf:
                df[term] += 1

        tfidf_global: Counter[str] = Counter()
        for tf in tf_per_doc:
            n_terms = sum(tf.values()) or 1
            for term, count in tf.items():
                if term in _STOP_WORDS or len(term) < 3:
                    continue
                idf = math.log(1 + n_docs / (1 + df[term]))
                tfidf_global[term] += (count / n_terms) * idf

        return [(term, round(score, 4)) for term, score in tfidf_global.most_common(top_n)]

    @staticmethod
    def _cross_references(texts: list[str], min_phrase_len: int = 3) -> dict[str, Any]:
        """Find phrases shared across multiple documents."""
        phrase_docs: defaultdict[str, set[int]] = defaultdict(set)

        for idx, text in enumerate(texts):
            tokens = _tokenize(text)
            seen: set[str] = set()
            for i in range(len(tokens) - min_phrase_len + 1):
                phrase = " ".join(tokens[i : i + min_phrase_len])
                if phrase not in seen:
                    seen.add(phrase)
                    phrase_docs[phrase].add(idx)

        shared = {
            phrase: sorted(docs)
            for phrase, docs in phrase_docs.items()
            if len(docs) > 1
        }
        top = sorted(shared.items(), key=lambda kv: len(kv[1]), reverse=True)[:30]
        return {
            "shared_phrases": [(p, docs) for p, docs in top],
            "total_shared": len(shared),
        }

    def analyze_corpus(self, texts: list[str]) -> dict[str, Any]:
        """Run full document analytics suite on a list of texts.

        Parameters
        ----------
        texts : list[str]
            Raw document strings (one per document / chunk).

        Returns
        -------
        dict with keys: entities, sentiment, keyphrases, cross_references.
        """
        if not texts:
            return {"error": "empty corpus"}

        return {
            "entities": self._entity_frequencies(texts),
            "sentiment": self._sentiment(texts),
            "keyphrases": self._tfidf_keyphrases(texts),
            "cross_references": self._cross_references(texts),
            "n_documents": len(texts),
        }


# ---------------------------------------------------------------------------
# Router — single entry-point for the inference servers
# ---------------------------------------------------------------------------

_ts = TimeSeriesPredictor()
_pa = PatternAnalyzer()
_re = RiskEngine()
_da = DocumentAnalytics()


def route_analytics(query: str, data: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an analytics request to the appropriate engine.

    Parameters
    ----------
    query : str
        Routing key — one of ``"predict"`` / ``"forecast"`` / ``"timeseries"``,
        ``"pattern"`` / ``"patterns"`` / ``"analyze"``,
        ``"risk"`` / ``"var"`` / ``"portfolio"``,
        ``"document"`` / ``"documents"`` / ``"corpus"`` / ``"text"``.
    data : dict
        Payload whose schema depends on *query*:

        - **predict/forecast**: ``{"values": list[float], "horizon": int, ...}``
        - **pattern/analyze**: ``{"values": list[float], "extra_columns": ...}``
        - **risk/var**: ``{"returns": list[float], "confidence": float, ...}``
        - **document/corpus**: ``{"texts": list[str]}``

    Returns
    -------
    dict   Result payload (always JSON-serialisable).
    """
    q = query.strip().lower()

    try:
        if q in ("forecast", "predict", "timeseries"):
            return _ts.predict(
                data.get("values", []),
                horizon=data.get("horizon", 5),
                season_len=data.get("season_len"),
                window=data.get("window", 5),
            )

        if q in ("pattern", "patterns", "analyze"):
            return _pa.analyze(
                data.get("values", []),
                extra_columns=data.get("extra_columns"),
            )

        if q in ("risk", "var", "portfolio"):
            return _re.assess(
                data.get("returns", []),
                confidence=data.get("confidence", 0.95),
                risk_free=data.get("risk_free", 0.0),
                mc_sims=data.get("mc_sims", 1000),
                mc_horizon=data.get("mc_horizon", 252),
            )

        if q in ("document", "documents", "corpus", "text"):
            return _da.analyze_corpus(data.get("texts", []))

        return {"error": f"unknown analytics query: {query!r}"}

    except Exception as exc:
        return {"error": str(exc)}
