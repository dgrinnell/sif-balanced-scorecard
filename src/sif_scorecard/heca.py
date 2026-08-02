"""High-Energy Control Assessment (HECA).

HECA is the proportion of observed high-energy hazards (>1,500 J of physical
energy) that have a corresponding Direct Control in place at the time of
observation (Oguz Erkal & Hallowell, 2023; Bayona et al., 2026).

A Direct Control is a safeguard that:
    1. is directly targeted to the high-energy source;
    2. mitigates the energy to acceptable levels such that a serious injury or
       fatality (SIF) is no longer the most likely outcome; and
    3. works even if there is an unintentional human error unrelated to the
       installation, use, and verification of the control.

Examples of Direct Controls: hard physical barriers, de-energization with
lockout-tagout (LOTO), fall arrest systems, and specialty PPE such as blast
suits. Standard PPE (hard hats, gloves, safety glasses) and administrative
controls are NOT Direct Controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

HIGH_ENERGY_THRESHOLD_JOULES: float = 1500.0

# Common high-energy hazard archetypes used in utility/construction field
# assessments (per EEI's "Power to Prevent" program and CSRA protocols).
HIGH_ENERGY_HAZARD_EXAMPLES: tuple[str, ...] = (
    "Fall from elevation greater than 4 feet",
    "Suspended load",
    "Mobile equipment with workers on foot",
    "Heavy rotating equipment",
    "Motor vehicle incident (occupant)",
    "High-temperature exposure (steam, hot fluids >150 F)",
    "Fire with sustained fuel source",
    "Explosion / arc flash",
    "Electrical contact with source >= 50 volts",
    "Excavation or trench collapse",
    "High-pressure release (hydraulic, pneumatic, steam)",
    "Struck by falling object from height",
)


@dataclass(frozen=True)
class HazardObservation:
    """One high-energy hazard observed during a task assessment."""

    description: str
    direct_control_present: bool
    energy_source: str = ""  # e.g. "gravity", "electrical", "mechanical"


@dataclass(frozen=True)
class HECAResult:
    """Result of a High-Energy Control Assessment."""

    n_hazards: int
    n_controlled: int
    score: float  # controlled / total, in [0, 1]
    uncontrolled: tuple[HazardObservation, ...]

    @property
    def exposure_gap(self) -> int:
        """Number of high-energy hazards without a Direct Control."""
        return self.n_hazards - self.n_controlled


def heca_score(observations: Iterable[HazardObservation]) -> HECAResult:
    """Compute the HECA score for one task assessment.

    Args:
        observations: high-energy hazard observations for a single crew/task.
            Low-energy hazards must be excluded upstream (they are out of
            scope for HECA by definition).

    Returns:
        HECAResult. Raises ValueError if no hazards were observed: a task with
        zero high-energy hazards has no defined HECA score and should be
        recorded as "no high-energy exposure" rather than 0% or 100%.
    """
    obs = tuple(observations)
    if not obs:
        raise ValueError(
            "HECA is undefined for zero observed high-energy hazards; record "
            "the task as having no high-energy exposure instead."
        )
    controlled = sum(1 for o in obs if o.direct_control_present)
    uncontrolled = tuple(o for o in obs if not o.direct_control_present)
    return HECAResult(
        n_hazards=len(obs),
        n_controlled=controlled,
        score=controlled / len(obs),
        uncontrolled=uncontrolled,
    )


def aggregate_heca(results: Iterable[HECAResult]) -> float:
    """Pooled HECA across assessments: total controlled / total hazards.

    Pooling weights each hazard equally (rather than averaging per-task
    scores), matching the ratio definition in the source studies.
    """
    results = tuple(results)
    total = sum(r.n_hazards for r in results)
    if total == 0:
        raise ValueError("No hazards across assessments; pooled HECA undefined.")
    return sum(r.n_controlled for r in results) / total
