"""SIF risk projection from the empirical coefficients in Bayona et al. (2026).

The paper's GLM (Table 8, Model 6) found that each percentage-point increase
in a company's baseline HECA score reduces the expected number of SIFs by ~3%
(coefficient -0.03, p = 0.02), and its Fig. 7 charts the implied exponential
risk curve at a fixed exposure of 2M worker-hours (~1,000 FTE-years):

    HECA 0.0  -> ~2.5 expected SIFs per 1,000 FTE
    HECA 0.5  -> ~0.5
    HECA 0.9  -> <0.15

The linear Model 1 found each percentage-point increase in PJSB quality is
associated with a +0.49 point increase in HECA (p = 0.04).

IMPORTANT: these are correlational, company-level associations from 31 North
American utility/construction firms — not causal guarantees. Use them for
prioritization and what-if framing, not for certifying a site as "safe."
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Published coefficients ------------------------------------------------
HECA_SIF_LOG_COEF: float = -0.03  # per HECA percentage point (Table 8)
PJSB_TO_HECA_COEF: float = 0.49  # HECA points per PJSB point (Model 1)
BASELINE_SIFS_PER_1000_FTE: float = 2.5  # at HECA = 0 (Fig. 7)
FTE_HOURS_PER_YEAR: float = 2_000.0

# --- Operating thresholds recommended by the paper -------------------------
HECA_COACHING_THRESHOLD: float = 0.30  # below this, "a SIF becomes a likely event"
BASELINE_MIN_ASSESSMENTS: int = 15  # >=15 PJSB and >=15 HECA observations
BASELINE_MAX_MONTHS: int = 3  # collected within a short period (<=3 months)


def expected_sifs_per_1000_fte(heca: float) -> float:
    """Expected SIF count per 1,000 FTE-years at a given HECA score.

    Args:
        heca: HECA score in [0, 1].
    """
    _check_unit(heca, "heca")
    return BASELINE_SIFS_PER_1000_FTE * math.exp(HECA_SIF_LOG_COEF * heca * 100)


def expected_sifs(heca: float, worker_hours: float) -> float:
    """Expected SIF count for an organization's actual exposure hours."""
    if worker_hours <= 0:
        raise ValueError("worker_hours must be positive")
    fte_years = worker_hours / FTE_HOURS_PER_YEAR
    return expected_sifs_per_1000_fte(heca) * fte_years / 1000.0


def sif_reduction(heca_current: float, heca_target: float) -> float:
    """Fractional reduction in expected SIFs from improving HECA.

    Returns e.g. 0.45 meaning a 45% reduction in expected SIF count.
    """
    _check_unit(heca_current, "heca_current")
    _check_unit(heca_target, "heca_target")
    ratio = math.exp(HECA_SIF_LOG_COEF * (heca_target - heca_current) * 100)
    return 1.0 - ratio


def projected_heca_gain_from_pjsb(pjsb_gain: float) -> float:
    """Projected HECA gain from a PJSB quality gain (both on the 0-1 scale).

    Model 1: +1 PJSB point -> +0.49 HECA points, holding hours constant.
    """
    return PJSB_TO_HECA_COEF * pjsb_gain


@dataclass(frozen=True)
class RiskBand:
    name: str
    heca_min: float
    guidance: str


RISK_BANDS: tuple[RiskBand, ...] = (
    RiskBand(
        "critical",
        0.0,
        "HECA below 30%: a SIF becomes a likely event. Provide immediate "
        "coaching to crews and close gaps in Direct Controls.",
    ),
    RiskBand(
        "elevated",
        HECA_COACHING_THRESHOLD,
        "Meaningful uncontrolled high-energy exposure remains. Target the "
        "most frequent uncontrolled energy sources.",
    ),
    RiskBand(
        "managed",
        0.60,
        "Majority of high-energy hazards carry Direct Controls. Sustain "
        "verification and pre-job brief quality.",
    ),
    RiskBand(
        "strong",
        0.80,
        "Strong control coverage; expected SIF rate is a small fraction of "
        "the uncontrolled baseline. Guard against drift.",
    ),
)


def risk_band(heca: float) -> RiskBand:
    """Classify a HECA score into an operating band."""
    _check_unit(heca, "heca")
    band = RISK_BANDS[0]
    for candidate in RISK_BANDS:
        if heca >= candidate.heca_min:
            band = candidate
    return band


def _check_unit(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
