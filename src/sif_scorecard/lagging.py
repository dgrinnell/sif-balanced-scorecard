"""Lagging (output) indicators: TRIR and the Severity-Based Lagging Indicator.

Formulas follow Bayona et al. (2026), Eq. 1-2, which in turn follow OSHA
recordkeeping conventions and Hallowell & Oguz Erkal (2024) for the SBLI.

Injury count abbreviations (OSHA Form 300/300A aligned):
    FA  - first-aid injuries (not OSHA recordable)
    MT  - medical treatment cases (recordable, no transfer/lost time)
    JT  - job transfer or restricted work cases
    DA  - days-away-from-work cases
    FT  - fatalities
    SIF - serious injuries and fatalities (death, near-death, or permanent
          impairment; overlaps other categories and is tracked separately)
"""

from __future__ import annotations

# SBLI severity weights (Hallowell & Oguz Erkal, 2024; Bayona et al., 2026 Eq. 2)
SBLI_WEIGHTS = {"FA": 100, "MT": 500, "JT": 750, "DA": 1500}

# OSHA normalization: incidents per 200,000 worker-hours (~100 FTE-years)
OSHA_HOURS_BASE = 200_000


def trir(mt: int, jt: int, da: int, ft: int, worker_hours: float) -> float:
    """Total Recordable Incident Rate per 200,000 worker-hours.

    TRIR = (MT + JT + DA + FT) * 200,000 / worker_hours

    First-aid injuries are excluded (not OSHA recordable).
    """
    _validate(worker_hours, mt=mt, jt=jt, da=da, ft=ft)
    return (mt + jt + da + ft) * OSHA_HOURS_BASE / worker_hours


def sbli(fa: int, mt: int, jt: int, da: int, worker_hours: float) -> float:
    """Severity-Based Lagging Indicator (Bayona et al., 2026, Eq. 2).

    SBLI = (100*FA + 500*MT + 750*JT + 1500*DA) * 200 / worker_hours

    Unlike TRIR, injuries are weighted by relative severity, so one
    days-away case moves the rate 15x more than one first-aid case.
    """
    _validate(worker_hours, fa=fa, mt=mt, jt=jt, da=da)
    weighted = (
        SBLI_WEIGHTS["FA"] * fa
        + SBLI_WEIGHTS["MT"] * mt
        + SBLI_WEIGHTS["JT"] * jt
        + SBLI_WEIGHTS["DA"] * da
    )
    return weighted * 200 / worker_hours


def sif_rate(sif: int, worker_hours: float, per_hours: float = OSHA_HOURS_BASE) -> float:
    """SIF rate normalized per `per_hours` worker-hours (default 200,000)."""
    _validate(worker_hours, sif=sif)
    return sif * per_hours / worker_hours


def _validate(worker_hours: float, **counts: int) -> None:
    if worker_hours <= 0:
        raise ValueError("worker_hours must be positive")
    for name, value in counts.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
