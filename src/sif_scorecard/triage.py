"""Tier assignment for a reviewed hazard table.

The same boolean rules the SIF triage method uses, so a ranked register is
reproducible: identical input rows always produce an identical ordering, and
each tier is a rule rather than a judgment.

    Tier 1  high-energy AND (no Direct Control OR verification failed)
    Tier 2  high-energy, control documented but unverified — plus every
            uncertain-energy row (unknown magnitude routes to verification)
    Tier 3  high-energy with a verified Direct Control
    Tier 4  low-energy — deprioritized for SIF prevention, not ignored

Within a tier, rows rank by exposure weight = frequency factor x workers
exposed, so the same gap affecting a crew of twelve daily outranks one
affecting one person a year.
"""

from __future__ import annotations

from dataclasses import dataclass

FREQUENCY_WEIGHT: dict[str, int] = {
    "daily": 4, "weekly": 3, "monthly": 2, "quarterly": 1, "rare": 1,
}

TIER_NAMES: dict[int, str] = {
    1: "Tier 1 — Act now (uncontrolled high-energy)",
    2: "Tier 2 — Verify (unverified control or unknown energy)",
    3: "Tier 3 — Sustain (verified Direct Control)",
    4: "Deprioritized for SIF prevention (low-energy)",
}


@dataclass(frozen=True)
class TieredHazard:
    tier: int
    exposure_weight: int
    rule: str


def exposure_weight(frequency: str | None, workers: int | float | None) -> int:
    """Frequency factor x workers exposed; unknowns default to the low end."""
    factor = FREQUENCY_WEIGHT.get(str(frequency or "").strip().lower(), 1)
    try:
        count = max(1, int(workers or 1))
    except (TypeError, ValueError):
        count = 1
    return factor * count


def assign_tier(
    high_energy: bool | None,
    direct_control: bool,
    verification: str | None = None,
    frequency: str | None = None,
    workers: int | float | None = None,
) -> TieredHazard:
    """Apply the tier rules to one hazard row.

    Args:
        high_energy: True / False / None (None == uncertain).
        direct_control: whether a Direct Control is documented.
        verification: "verified", "unverified", "failed", or None.
        frequency, workers: for the exposure weight.
    """
    state = str(verification or "").strip().lower()
    weight = exposure_weight(frequency, workers)

    if high_energy is None:
        return TieredHazard(2, weight, "energy magnitude uncertain — verify in field")
    if high_energy is False:
        return TieredHazard(4, weight, "low-energy — not a SIF mechanism")
    if not direct_control:
        return TieredHazard(1, weight, "no Direct Control documented")
    if state == "failed":
        return TieredHazard(
            1, weight, "control documented but verification failed"
        )
    if state == "verified":
        return TieredHazard(3, weight, "Direct Control verified")
    return TieredHazard(2, weight, "control documented but unverified")


def documented_heca(rows: list[dict]) -> float | None:
    """Share of definite high-energy rows with a documented, non-failed control."""
    definite = [r for r in rows if r.get("high_energy") is True]
    if not definite:
        return None
    controlled = sum(
        1 for r in definite
        if r.get("direct_control")
        and str(r.get("verification", "")).lower() != "failed"
    )
    return controlled / len(definite)


def verified_heca(rows: list[dict]) -> float | None:
    """Share of definite high-energy rows with a *verified* Direct Control."""
    definite = [r for r in rows if r.get("high_energy") is True]
    if not definite:
        return None
    verified = sum(
        1 for r in definite
        if r.get("direct_control")
        and str(r.get("verification", "")).lower() == "verified"
    )
    return verified / len(definite)
