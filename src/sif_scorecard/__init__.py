"""sif-scorecard: a balanced leading/monitoring/lagging safety measurement kit.

Implements the measurement framework validated in Bayona, Hallowell, Bhandari
& Raheemy (2026), "Balanced approach to serious injury and fatality
prevention," Journal of Safety Research 98, 175-189.
"""

from .heca import (
    HIGH_ENERGY_THRESHOLD_JOULES,
    HazardObservation,
    HECAResult,
    aggregate_heca,
    heca_score,
)
from .lagging import sbli, sif_rate, trir
from .pjsb import MAX_WEIGHTED_SCORE, RUBRIC, PJSBResult, score_from_flags, score_pjsb
from .reliability import (
    RELIABILITY_GATE,
    assessor_gate,
    cohens_kappa,
    icc_2k,
    interpret_agreement,
)
from .risk import (
    HECA_COACHING_THRESHOLD,
    expected_sifs,
    expected_sifs_per_1000_fte,
    projected_heca_gain_from_pjsb,
    risk_band,
    sif_reduction,
)

__version__ = "0.1.0"

__all__ = [
    "HIGH_ENERGY_THRESHOLD_JOULES",
    "HazardObservation",
    "HECAResult",
    "aggregate_heca",
    "heca_score",
    "sbli",
    "sif_rate",
    "trir",
    "MAX_WEIGHTED_SCORE",
    "RUBRIC",
    "PJSBResult",
    "score_from_flags",
    "score_pjsb",
    "RELIABILITY_GATE",
    "assessor_gate",
    "cohens_kappa",
    "icc_2k",
    "interpret_agreement",
    "HECA_COACHING_THRESHOLD",
    "expected_sifs",
    "expected_sifs_per_1000_fte",
    "projected_heca_gain_from_pjsb",
    "risk_band",
    "sif_reduction",
]
