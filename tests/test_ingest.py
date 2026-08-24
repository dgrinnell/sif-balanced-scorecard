import pandas as pd
import pytest

from sif_scorecard.ingest import (
    IngestError,
    find_item_columns,
    heca_template,
    load_heca_file,
    load_pjsb_file,
    pjsb_template,
    to_bool,
)
from sif_scorecard.pjsb import RUBRIC


# --- boolean tolerance ----------------------------------------------------


@pytest.mark.parametrize(
    "value", ["Yes", "yes", "Y", "TRUE", True, 1, "1", "x", "✓", "Complete"]
)
def test_affirmative_spellings(value):
    assert to_bool(value) is True


@pytest.mark.parametrize(
    "value", ["No", "n", "FALSE", False, 0, "0", "", None, "N/A", float("nan")]
)
def test_negative_spellings(value):
    assert to_bool(value) is False


def test_qualified_yes_is_affirmative():
    assert to_bool("Yes - verified by supervisor") is True


def test_unknown_text_scores_absent():
    # Field rule: no affirmative evidence means the element was not present.
    assert to_bool("supervisor was unsure") is False


# --- column detection -----------------------------------------------------


def test_finds_item_columns_by_various_names():
    cols = [f"Item{i:02d}" for i in range(1, 16)]
    assert set(find_item_columns(cols)) == set(range(1, 16))
    assert set(find_item_columns([f"Q{i}" for i in range(1, 16)])) == set(range(1, 16))
    assert set(find_item_columns([str(i) for i in range(1, 16)])) == set(range(1, 16))


def test_finds_item_columns_by_statement_text():
    cols = [item.statement for item in RUBRIC]
    assert set(find_item_columns(cols)) == set(range(1, 16))


def test_ignores_unrelated_columns():
    cols = ["Crew", "Date", "Submitted by"] + [f"Item{i:02d}" for i in range(1, 16)]
    found = find_item_columns(cols)
    assert set(found) == set(range(1, 16))
    assert "Crew" not in found.values()


# --- PJSB ingest ----------------------------------------------------------


def _pjsb_frame(rows):
    return pd.DataFrame(
        [{f"Item{i:02d}": v for i, v in enumerate(r, start=1)} for r in rows]
    )


def test_pjsb_scoring_uses_official_weights():
    perfect = _pjsb_frame([["Yes"] * 15])
    result = load_pjsb_file(perfect)
    assert result.n_assessments == 1
    assert result.assessments["weighted_score"].iloc[0] == 57
    assert result.mean_quality == pytest.approx(1.0)


def test_pjsb_partial_scoring():
    # Miss items 5, 7, 8 (the three 5-point items) -> 42/57
    flags = ["Yes"] * 15
    for i in (5, 7, 8):
        flags[i - 1] = "No"
    result = load_pjsb_file(_pjsb_frame([flags]))
    assert result.assessments["weighted_score"].iloc[0] == 42
    assert result.mean_quality == pytest.approx(42 / 57)


def test_pjsb_item_miss_rates_rank_worst_first():
    a = ["Yes"] * 15
    b = ["Yes"] * 15
    b[7] = "No"  # item 8 missed once
    b[0] = "No"  # item 1 missed once
    c = ["Yes"] * 15
    c[7] = "No"  # item 8 missed twice
    misses = load_pjsb_file(_pjsb_frame([a, b, c])).item_miss_rates
    top = misses.iloc[0]
    assert top["item"] == 8
    assert top["miss_rate"] == pytest.approx(2 / 3)
    assert bool(top["sif_critical"]) is True


def test_pjsb_missing_columns_raises_actionable_error():
    df = _pjsb_frame([["Yes"] * 15]).drop(columns=["Item04", "Item09"])
    with pytest.raises(IngestError, match=r"\[4, 9\]"):
        load_pjsb_file(df)


def test_pjsb_empty_file_raises():
    with pytest.raises(IngestError, match="no rows"):
        load_pjsb_file(pd.DataFrame())


def test_pjsb_template_round_trips():
    result = load_pjsb_file(pjsb_template())
    assert result.n_assessments == 1
    assert 0 < result.mean_quality < 1


# --- HECA ingest ----------------------------------------------------------


def test_heca_pools_over_hazards():
    df = pd.DataFrame(
        {
            "Hazard": ["a", "b", "c", "d"],
            "DirectControlPresent": ["Yes", "No", "No", "Yes"],
        }
    )
    upload = load_heca_file(df)
    assert upload.score == pytest.approx(0.5)
    assert upload.result.n_hazards == 4


def test_heca_excludes_low_energy_rows_and_reports_them():
    df = pd.DataFrame(
        {
            "Hazard": ["a", "b", "c"],
            "HighEnergy": ["Yes", "No", "Yes"],
            "DirectControlPresent": ["Yes", "No", "No"],
        }
    )
    upload = load_heca_file(df)
    assert upload.result.n_hazards == 2  # low-energy row excluded
    assert upload.n_excluded_low_energy == 1
    assert upload.score == pytest.approx(0.5)


def test_heca_uncontrolled_by_source():
    df = pd.DataFrame(
        {
            "Hazard": ["a", "b", "c"],
            "EnergySource": ["Gravity", "Gravity", "Electrical"],
            "DirectControlPresent": ["No", "No", "Yes"],
        }
    )
    upload = load_heca_file(df)
    assert upload.uncontrolled_by_source["Gravity"] == 2
    assert "Electrical" not in upload.uncontrolled_by_source


def test_heca_counts_distinct_tasks():
    df = pd.DataFrame(
        {
            "TaskID": ["T1", "T1", "T2"],
            "Hazard": ["a", "b", "c"],
            "DirectControlPresent": ["Yes", "No", "Yes"],
        }
    )
    assert load_heca_file(df).n_tasks == 2


def test_heca_alternate_control_column_names():
    for name in ["Direct Control Present", "Controlled", "control_in_place"]:
        df = pd.DataFrame({"Hazard": ["a"], name: ["Yes"]})
        assert load_heca_file(df).score == 1.0


def test_heca_missing_control_column_raises():
    with pytest.raises(IngestError, match="Direct Control column"):
        load_heca_file(pd.DataFrame({"Hazard": ["a"], "Notes": ["x"]}))


def test_heca_all_low_energy_raises_with_guidance():
    df = pd.DataFrame(
        {"HighEnergy": ["No", "No"], "DirectControlPresent": ["No", "Yes"]}
    )
    with pytest.raises(IngestError, match="no high-energy exposure"):
        load_heca_file(df)


def test_heca_template_round_trips():
    upload = load_heca_file(heca_template())
    assert upload.result.n_hazards == 2
    assert upload.score == pytest.approx(0.5)
