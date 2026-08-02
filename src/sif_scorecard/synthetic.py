"""Synthetic company-panel generator calibrated to Bayona et al. (2026), Table 6.

Generates a realistic org-level dataset (one row per company) with the same
structure as the study's 31-company panel: baseline PJSB quality, baseline
HECA, worker-hours, and six injury-count variables, plus computed TRIR/SBLI.

Calibration targets (Table 6, 22-month study window):
    PJSB quality: mean 0.62, SD 0.15, range 0.25-0.89
    HECA:         mean 0.53, SD 0.21, range 0.17-0.92
    Worker-hours: mean 11.6M, SD 16.7M (heavily right-skewed)
    Injury pools: 4,992 FA; 1,092 MT; 715 JT; 982 DA; 4 FT; 106 SIF
                  across 361M worker-hours

Structural relationships baked in (Table 7/8, Fig. 5, Fig. 7):
    - HECA ~ 0.49 * PJSB + noise (Model 1)
    - Utility clients score higher than contractors (Fig. 5, ~+22.5 HECA pts)
    - E[SIF] follows the exponential decay in HECA (Fig. 7), scaled to hours
    - Less-severe counts decline ~2%/HECA point (Table 8), with wide noise

All data is synthetic. No real company data is included in this repository.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .lagging import sbli, trir
from .risk import expected_sifs

# Per-million-hour base rates implied by Table 6 pooled totals, at mean HECA.
_BASE_RATES_PER_M_HOURS = {"FA": 13.8, "MT": 3.0, "JT": 2.0, "DA": 2.7}
_SEVERITY_DECAY_PER_HECA_PT = -0.02  # Table 8 non-SIF coefficient magnitude
_MEAN_HECA_PCT = 53.0
_CLIENT_HECA_LIFT = 0.145  # ~+22.5 total pts vs contractors incl. PJSB pathway
_CLIENT_PJSB_LIFT = 0.08


def generate_companies(
    n_companies: int = 31,
    months: int = 22,
    client_share: float = 0.35,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Generate a synthetic company panel.

    Args:
        n_companies: number of organizations to simulate.
        months: exposure window in months (study used 22).
        client_share: fraction of companies that are utility clients (vs
            contractors).
        seed: RNG seed for reproducibility.

    Returns:
        DataFrame with one row per company: type, worker_hours, pjsb, heca,
        fa, mt, jt, da, ft, sif, trir, sbli.
    """
    rng = np.random.default_rng(seed)
    is_client = rng.random(n_companies) < client_share

    # PJSB quality: truncated normal around the observed distribution.
    pjsb = rng.normal(0.62 - 0.03 + _CLIENT_PJSB_LIFT * is_client, 0.13)
    pjsb = np.clip(pjsb, 0.20, 0.95)

    # HECA: linear in PJSB (Model 1 coefficient) + firm-type lift + noise.
    heca = (
        0.17
        + 0.49 * pjsb
        + _CLIENT_HECA_LIFT * is_client
        + rng.normal(0.0, 0.12, n_companies)
    )
    heca = np.clip(heca, 0.10, 0.95)

    # Worker-hours: lognormal for the heavy right skew; scaled to the window.
    worker_hours = rng.lognormal(mean=15.6, sigma=1.3, size=n_companies)
    worker_hours = np.clip(worker_hours, 4e4, 8e7) * (months / 22.0)

    heca_pct = heca * 100
    m_hours = worker_hours / 1e6

    counts: dict[str, np.ndarray] = {}
    for injury, base in _BASE_RATES_PER_M_HOURS.items():
        lam = (
            base
            * np.exp(_SEVERITY_DECAY_PER_HECA_PT * (heca_pct - _MEAN_HECA_PCT))
            * m_hours
        )
        # Gamma-Poisson mixture (negative binomial) for realistic overdispersion.
        lam_disp = rng.gamma(shape=2.0, scale=lam / 2.0)
        counts[injury] = rng.poisson(lam_disp)

    # SIFs: zero-inflated Poisson with mean from the Fig. 7 risk curve.
    sif_lambda = np.array(
        [expected_sifs(h, wh) for h, wh in zip(heca, worker_hours)]
    )
    structural_zero = rng.random(n_companies) < 0.25
    sif = np.where(structural_zero, 0, rng.poisson(sif_lambda))

    # Fatalities: rare subset of SIFs.
    ft = rng.binomial(sif, 0.04)

    df = pd.DataFrame(
        {
            "company_id": [f"C{i + 1:03d}" for i in range(n_companies)],
            "type": np.where(is_client, "client", "contractor"),
            "worker_hours": worker_hours.round(0),
            "pjsb": pjsb.round(3),
            "heca": heca.round(3),
            "fa": counts["FA"],
            "mt": counts["MT"],
            "jt": counts["JT"],
            "da": counts["DA"],
            "ft": ft,
            "sif": sif,
        }
    )
    df["trir"] = [
        round(trir(r.mt, r.jt, r.da, r.ft, r.worker_hours), 2)
        for r in df.itertuples()
    ]
    df["sbli"] = [
        round(sbli(r.fa, r.mt, r.jt, r.da, r.worker_hours), 2)
        for r in df.itertuples()
    ]
    return df


def generate_pjsb_observations(
    company_quality: float, n_observations: int = 15, seed: int | None = None
) -> pd.DataFrame:
    """Simulate item-level PJSB field observations for one company.

    Each of the 15 scorecard items is marked present with a probability that
    tracks the company's overall quality, with the heavier-weighted "hazard"
    items slightly more likely to be present (crews rarely skip hazard talk
    entirely; participation and change-management items fail most often).
    """
    from .pjsb import RUBRIC

    rng = np.random.default_rng(seed)
    rows = []
    for obs in range(n_observations):
        for item in RUBRIC:
            # Higher-weight items are core habits; low-weight items drift more.
            tilt = 0.05 * (item.weight - 4)
            p = np.clip(company_quality + tilt + rng.normal(0, 0.08), 0.02, 0.98)
            rows.append(
                {
                    "observation": obs + 1,
                    "item": item.number,
                    "weight": item.weight,
                    "present": bool(rng.random() < p),
                }
            )
    return pd.DataFrame(rows)
