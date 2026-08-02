import numpy as np
import pytest

from sif_scorecard.models import fit_poisson, fit_zip, replicate_model6
from sif_scorecard.synthetic import generate_companies, generate_pjsb_observations


@pytest.fixture(scope="module")
def panel():
    return generate_companies(n_companies=200, seed=7)


def test_panel_shape_and_columns(panel):
    expected = {
        "company_id", "type", "worker_hours", "pjsb", "heca",
        "fa", "mt", "jt", "da", "ft", "sif", "trir", "sbli",
    }
    assert expected.issubset(panel.columns)
    assert len(panel) == 200
    assert panel["company_id"].is_unique


def test_calibration_roughly_matches_table6(panel):
    assert 0.55 < panel["pjsb"].mean() < 0.72
    assert 0.42 < panel["heca"].mean() < 0.65
    assert (panel["heca"] <= 0.95).all() and (panel["heca"] >= 0.10).all()
    # Heavy right skew in exposure hours.
    assert panel["worker_hours"].mean() > panel["worker_hours"].median()


def test_reproducibility():
    a = generate_companies(n_companies=20, seed=3)
    b = generate_companies(n_companies=20, seed=3)
    assert a.equals(b)


def test_structural_relationships(panel):
    # Model 1 direction: PJSB and HECA positively correlated.
    assert panel["pjsb"].corr(panel["heca"]) > 0.3
    # Finding 3 direction: higher HECA -> lower SIF rate.
    rate = panel["sif"] / panel["worker_hours"]
    assert np.corrcoef(panel["heca"], rate)[0, 1] < 0


def test_poisson_recovers_negative_heca_effect(panel):
    result = fit_poisson(panel, "sif", "heca")
    # True generating coefficient is -0.03 per point.
    assert -0.05 < result.coef < -0.01
    assert result.p_value < 0.05


def test_zip_runs_and_reports(panel):
    result = fit_zip(panel, "sif", "heca")
    assert result.outcome == "SIF"
    assert np.isfinite(result.coef)
    assert "Poisson" in result.model_type
    assert result.summary_line()


def test_replicate_model6_shape(panel):
    results = replicate_model6(panel)
    assert len(results) == 12  # 6 outcomes x 2 predictors


def test_pjsb_observation_generator():
    obs = generate_pjsb_observations(0.7, n_observations=15, seed=5)
    assert len(obs) == 15 * 15
    share_present = obs["present"].mean()
    assert 0.55 < share_present < 0.85
