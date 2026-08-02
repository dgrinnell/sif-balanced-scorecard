import pytest

from sif_scorecard.risk import (
    HECA_COACHING_THRESHOLD,
    expected_sifs,
    expected_sifs_per_1000_fte,
    projected_heca_gain_from_pjsb,
    risk_band,
    sif_reduction,
)


def test_curve_matches_paper_fig7_anchors():
    # Fig. 7: HECA 0 -> ~2.5, HECA 0.5 -> ~0.5, HECA 0.9 -> <0.15 (per 1000 FTE)
    assert expected_sifs_per_1000_fte(0.0) == pytest.approx(2.5)
    assert expected_sifs_per_1000_fte(0.5) == pytest.approx(0.56, abs=0.07)
    assert expected_sifs_per_1000_fte(0.9) < 0.18


def test_expected_sifs_scales_with_hours():
    # 2M worker-hours ~ 1000 FTE-years, so this should equal the per-1000-FTE value.
    assert expected_sifs(0.5, 2_000_000) == pytest.approx(
        expected_sifs_per_1000_fte(0.5)
    )
    assert expected_sifs(0.5, 4_000_000) == pytest.approx(
        2 * expected_sifs_per_1000_fte(0.5)
    )


def test_sif_reduction_three_pct_per_point():
    # +1 HECA percentage point -> ~3% fewer expected SIFs.
    assert sif_reduction(0.50, 0.51) == pytest.approx(0.0296, abs=0.001)
    # Improvement -> positive reduction; regression -> negative.
    assert sif_reduction(0.50, 0.80) > 0
    assert sif_reduction(0.80, 0.50) < 0


def test_pjsb_pathway():
    # Model 1: +10 PJSB points -> +4.9 HECA points.
    assert projected_heca_gain_from_pjsb(0.10) == pytest.approx(0.049)


def test_risk_bands():
    assert risk_band(0.10).name == "critical"
    assert risk_band(HECA_COACHING_THRESHOLD).name == "elevated"
    assert risk_band(0.70).name == "managed"
    assert risk_band(0.92).name == "strong"


def test_bounds_validation():
    with pytest.raises(ValueError):
        expected_sifs_per_1000_fte(1.5)
    with pytest.raises(ValueError):
        sif_reduction(-0.1, 0.5)
