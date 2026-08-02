"""Assessor calibration statistics: Cohen's kappa and ICC.

The source study only accepted field data from assessors whose agreement met
kappa or ICC > 0.40 (moderate, per Landis & Koch, 1977). These utilities let
an organization run the same gate on its own observers before trusting their
PJSB / HECA scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

RELIABILITY_GATE: float = 0.40  # minimum kappa/ICC to accept an assessor's data


def cohens_kappa(rater_a: Sequence[int], rater_b: Sequence[int]) -> float:
    """Cohen's kappa for two raters over categorical (e.g. binary) items.

    Args:
        rater_a, rater_b: equal-length sequences of category labels
            (e.g. 0/1 for absent/present on the 15 PJSB items).
    """
    a = np.asarray(rater_a)
    b = np.asarray(rater_b)
    if a.shape != b.shape or a.ndim != 1 or a.size == 0:
        raise ValueError("rater_a and rater_b must be equal-length 1-D sequences")

    categories = np.union1d(a, b)
    n = a.size
    p_observed = float(np.mean(a == b))
    p_expected = float(
        sum((np.mean(a == c)) * (np.mean(b == c)) for c in categories)
    )
    if np.isclose(p_expected, 1.0):
        # Raters (and chance) agree perfectly on a single category; kappa is
        # undefined. Report 1.0 if observed agreement is also perfect.
        return 1.0 if np.isclose(p_observed, 1.0) else 0.0
    return (p_observed - p_expected) / (1.0 - p_expected)


def icc_2k(ratings: np.ndarray) -> float:
    """ICC(2,k): two-way random effects, absolute agreement, average of k raters.

    This matches the study's use of average-rater ICC for multi-assessor
    companies (typically 2-5 raters).

    Args:
        ratings: array of shape (n_subjects, k_raters); each cell is one
            rater's score for one subject (e.g. a task's HECA score).
    """
    x = np.asarray(ratings, dtype=float)
    if x.ndim != 2 or x.shape[0] < 2 or x.shape[1] < 2:
        raise ValueError("ratings must be (n_subjects >= 2, k_raters >= 2)")

    n, k = x.shape
    grand = x.mean()
    subject_means = x.mean(axis=1)
    rater_means = x.mean(axis=0)

    ss_subjects = k * np.sum((subject_means - grand) ** 2)
    ss_raters = n * np.sum((rater_means - grand) ** 2)
    ss_total = np.sum((x - grand) ** 2)
    ss_error = ss_total - ss_subjects - ss_raters

    ms_subjects = ss_subjects / (n - 1)
    ms_raters = ss_raters / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    denom = ms_subjects + (ms_raters - ms_error) / n
    if np.isclose(denom, 0.0):
        return 0.0
    return float((ms_subjects - ms_error) / denom)


@dataclass(frozen=True)
class ReliabilityVerdict:
    statistic: str
    value: float
    interpretation: str
    qualified: bool


def interpret_agreement(value: float) -> str:
    """Landis & Koch (1977) qualitative bands (also used for ICC in the study)."""
    if value < 0.20:
        return "poor"
    if value < 0.40:
        return "fair"
    if value < 0.60:
        return "moderate"
    if value < 0.80:
        return "substantial"
    return "near-perfect"


def assessor_gate(value: float, statistic: str = "kappa") -> ReliabilityVerdict:
    """Apply the study's inclusion gate (> 0.40) to a reliability estimate."""
    return ReliabilityVerdict(
        statistic=statistic,
        value=value,
        interpretation=interpret_agreement(value),
        qualified=value > RELIABILITY_GATE,
    )
