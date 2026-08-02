import numpy as np
import pytest

from sif_scorecard.reliability import (
    assessor_gate,
    cohens_kappa,
    icc_2k,
    interpret_agreement,
)


def test_kappa_perfect_agreement():
    a = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1]
    assert cohens_kappa(a, a) == pytest.approx(1.0)


def test_kappa_chance_agreement_near_zero():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 2, 2000)
    b = rng.integers(0, 2, 2000)
    assert abs(cohens_kappa(a, b)) < 0.06


def test_kappa_known_value():
    # Classic 2x2 example: 20 items, observed agreement 0.85, expected 0.53.
    a = [1] * 10 + [0] * 10
    b = [1] * 9 + [0] * 1 + [0] * 8 + [1] * 2
    k = cohens_kappa(a, b)
    assert 0.6 < k < 0.8  # substantial


def test_kappa_all_same_category():
    assert cohens_kappa([1, 1, 1], [1, 1, 1]) == 1.0


def test_icc_high_agreement():
    subjects = np.linspace(0.2, 0.9, 10)
    rng = np.random.default_rng(1)
    ratings = np.column_stack(
        [subjects + rng.normal(0, 0.02, 10) for _ in range(3)]
    )
    assert icc_2k(ratings) > 0.9


def test_icc_no_agreement():
    rng = np.random.default_rng(2)
    ratings = rng.random((10, 3))
    assert icc_2k(ratings) < 0.6


def test_interpretation_bands():
    assert interpret_agreement(0.1) == "poor"
    assert interpret_agreement(0.3) == "fair"
    assert interpret_agreement(0.5) == "moderate"
    assert interpret_agreement(0.7) == "substantial"
    assert interpret_agreement(0.9) == "near-perfect"


def test_assessor_gate_matches_study_inclusion_rule():
    assert assessor_gate(0.53).qualified  # e.g. study company 2
    assert not assessor_gate(0.36).qualified  # e.g. study company 15 (excluded)
