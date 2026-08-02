import pytest

from sif_scorecard.heca import HazardObservation, aggregate_heca, heca_score


def _obs(controlled: bool, desc: str = "Suspended load") -> HazardObservation:
    return HazardObservation(description=desc, direct_control_present=controlled)


def test_all_controlled():
    result = heca_score([_obs(True), _obs(True)])
    assert result.score == 1.0
    assert result.exposure_gap == 0
    assert result.uncontrolled == ()


def test_partial_control():
    result = heca_score([_obs(True), _obs(False, "Fall from 12 ft"), _obs(True)])
    assert result.score == pytest.approx(2 / 3)
    assert result.exposure_gap == 1
    assert result.uncontrolled[0].description == "Fall from 12 ft"


def test_zero_hazards_is_undefined():
    with pytest.raises(ValueError, match="undefined"):
        heca_score([])


def test_aggregate_pools_by_hazard_not_by_task():
    # Task A: 1/1 controlled. Task B: 1/4 controlled.
    a = heca_score([_obs(True)])
    b = heca_score([_obs(True), _obs(False), _obs(False), _obs(False)])
    pooled = aggregate_heca([a, b])
    # Pooled = 2/5, not the mean of task scores (0.625).
    assert pooled == pytest.approx(0.4)
