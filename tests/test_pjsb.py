import pytest

from sif_scorecard.pjsb import MAX_WEIGHTED_SCORE, RUBRIC, score_from_flags, score_pjsb


def test_rubric_matches_csra_scorecard():
    assert len(RUBRIC) == 15
    assert MAX_WEIGHTED_SCORE == 57
    weights = [item.weight for item in RUBRIC]
    assert weights == [4, 4, 4, 3, 5, 4, 5, 5, 3, 3, 4, 4, 3, 3, 3]
    # The three 5-point items are the hazard/control/SIF-emphasis core.
    assert [i.number for i in RUBRIC if i.weight == 5] == [5, 7, 8]


def test_perfect_brief():
    result = score_pjsb({i: True for i in range(1, 16)})
    assert result.weighted_score == 57
    assert result.quality == 1.0
    assert result.simple_proportion == 1.0
    assert result.missing_items == ()


def test_empty_brief():
    result = score_pjsb({i: False for i in range(1, 16)})
    assert result.weighted_score == 0
    assert result.quality == 0.0
    assert len(result.missing_items) == 15


def test_partial_brief_weighted_vs_simple():
    # Present: all except the three 5-point items (5, 7, 8).
    responses = {i: i not in (5, 7, 8) for i in range(1, 16)}
    result = score_pjsb(responses)
    assert result.weighted_score == 57 - 15
    assert result.quality == pytest.approx(42 / 57)
    assert result.simple_proportion == pytest.approx(12 / 15)
    # Missing items sorted highest-weight first.
    assert [i.number for i in result.missing_items] == [5, 7, 8]


def test_missing_item_raises():
    with pytest.raises(ValueError, match="missing"):
        score_pjsb({i: True for i in range(1, 15)})


def test_unexpected_item_raises():
    responses = {i: True for i in range(1, 16)}
    responses[16] = True
    with pytest.raises(ValueError, match="unexpected"):
        score_pjsb(responses)


def test_score_from_flags():
    assert score_from_flags([True] * 15).quality == 1.0
    with pytest.raises(ValueError):
        score_from_flags([True] * 14)
