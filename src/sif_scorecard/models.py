"""Count-regression models linking short-term measures to injury outcomes.

Reproduces the analytical approach of Bayona et al. (2026), Model 6: injury
counts are mostly zeros with a long tail, so ordinary linear regression on
rates is a poor fit. Poisson GLMs with a log(worker-hours) offset — and
zero-inflated Poisson for SIFs/fatalities — model the counts directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class CountModelResult:
    outcome: str
    predictor: str
    coef: float  # log-rate change per predictor percentage point
    se: float
    p_value: float
    pct_change_per_point: float  # (exp(coef) - 1) * 100
    model_type: str

    def summary_line(self) -> str:
        return (
            f"{self.outcome:>4s} ~ {self.predictor}: coef={self.coef:+.4f} "
            f"(SE {self.se:.4f}, p={self.p_value:.3g}) -> "
            f"{self.pct_change_per_point:+.1f}% per point [{self.model_type}]"
        )


def fit_poisson(
    df: pd.DataFrame,
    outcome: str,
    predictor: str = "heca",
    hours_col: str = "worker_hours",
) -> CountModelResult:
    """Poisson GLM: outcome count ~ predictor, offset log(worker_hours).

    The predictor is expressed in percentage points (0-100) so the coefficient
    reads as "log-rate change per point," matching the paper's Table 8.
    """
    x_pct = df[predictor].to_numpy(dtype=float) * 100.0
    exog = sm.add_constant(x_pct)
    offset = np.log(df[hours_col].to_numpy(dtype=float))
    model = sm.GLM(
        df[outcome].to_numpy(), exog, family=sm.families.Poisson(), offset=offset
    )
    fit = model.fit()
    coef, se, p = fit.params[1], fit.bse[1], fit.pvalues[1]
    return CountModelResult(
        outcome=outcome.upper(),
        predictor=predictor,
        coef=float(coef),
        se=float(se),
        p_value=float(p),
        pct_change_per_point=(float(np.exp(coef)) - 1.0) * 100.0,
        model_type="Poisson GLM",
    )


def fit_zip(
    df: pd.DataFrame,
    outcome: str,
    predictor: str = "heca",
    hours_col: str = "worker_hours",
) -> CountModelResult:
    """Zero-inflated Poisson for excess-zero outcomes (SIFs, fatalities).

    Falls back to plain Poisson if ZIP fails to converge (small samples with
    few non-zero outcomes are common in real safety panels).
    """
    x_pct = df[predictor].to_numpy(dtype=float) * 100.0
    exog = sm.add_constant(x_pct)
    offset = np.log(df[hours_col].to_numpy(dtype=float))
    try:
        model = sm.ZeroInflatedPoisson(
            df[outcome].to_numpy(),
            exog,
            exog_infl=np.ones((len(df), 1)),
            offset=offset,
        )
        fit = model.fit(disp=False, maxiter=200)
        if not fit.mle_retvals.get("converged", False):
            raise RuntimeError("ZIP did not converge")
        # Params are ordered [inflate_const, const, x1]; the slope is last.
        idx = len(fit.params) - 1
        coef = float(fit.params[idx])
        se = float(fit.bse[idx])
        p = float(fit.pvalues[idx])
        model_type = "Zero-inflated Poisson"
    except Exception:
        return fit_poisson(df, outcome, predictor, hours_col)
    return CountModelResult(
        outcome=outcome.upper(),
        predictor=predictor,
        coef=coef,
        se=se,
        p_value=p,
        pct_change_per_point=(float(np.exp(coef)) - 1.0) * 100.0,
        model_type=model_type,
    )


def replicate_model6(df: pd.DataFrame) -> list[CountModelResult]:
    """Fit the paper's Model 6 family: each injury type ~ PJSB and ~ HECA.

    Uses ZIP for sif/ft (excess zeros) and Poisson GLM otherwise.
    """
    results: list[CountModelResult] = []
    for predictor in ("pjsb", "heca"):
        for outcome in ("fa", "mt", "jt", "da"):
            results.append(fit_poisson(df, outcome, predictor))
        for outcome in ("ft", "sif"):
            results.append(fit_zip(df, outcome, predictor))
    return results
