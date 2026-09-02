import pytest

from sif_scorecard.classify import classify_control, classify_energy
from sif_scorecard.triage import (
    assign_tier,
    documented_heca,
    exposure_weight,
    verified_heca,
)


# --- energy classification ------------------------------------------------


@pytest.mark.parametrize(
    "text,source",
    [
        ("Work near roof edge, approx 20 ft", "gravity-fall"),
        ("2-ton die moved over walkway by crane", "gravity-load"),
        ("Forklifts and pickers share aisle during loading", "motion"),
        ("Operators clear jams at conveyor head pulley", "mechanical"),
        ("Racking breakers in 480V MCC room", "electrical"),
        ("Steam trap replacement on 150 psi header", "pressure"),
        ("Nitinol wire quenched in molten salt bath", "temperature"),
        ("Confined space entry after nitrogen purge", "chemical-explosive"),
        ("Excavation approx 6 ft for utility tie-in", "excavation"),
    ],
)
def test_high_energy_sources_recognized(text, source):
    result = classify_energy(text)
    assert result.high_energy is True
    assert result.source == source
    assert result.matched  # the phrase that triggered it is reported


@pytest.mark.parametrize(
    "text",
    [
        "Repetitive lifting of 30 lb cases",
        "Slips on dusty floor near the bench",
        "Office ergonomics at workstation",
        "Cut finger on box seam while inspecting",
    ],
)
def test_low_energy_recognized(text):
    result = classify_energy(text)
    assert result.high_energy is False
    assert result.source == "low-energy"


def test_pit_abbreviation_does_not_match_lowercase_pit():
    # "PIT" is powered-industrial-truck; "pump pit access" is not.
    assert classify_energy("PIT operation near pedestrians").source == "motion"
    assert classify_energy("Vibration table pump pit access").source != "motion"


def test_unmatched_text_is_uncertain_not_guessed():
    result = classify_energy("Review of documentation for the new process")
    assert result.high_energy is None
    assert result.label == "uncertain"


def test_empty_text_is_uncertain():
    assert classify_energy("").high_energy is None
    assert classify_energy(None).high_energy is None


def test_high_energy_wins_over_low_energy_mention():
    # A record naming both must not be downgraded to the ordinary exposure.
    result = classify_energy("Manual handling of parts near the crane pick")
    assert result.high_energy is True
    assert result.source == "gravity-load"


def test_reason_quotes_the_trigger_phrase():
    result = classify_energy("Racking breakers in 480V MCC room")
    assert result.matched.lower() in result.reason.lower()


# --- control classification -----------------------------------------------


@pytest.mark.parametrize(
    "text,expected_type",
    [
        ("LOTO procedure LP-102 applied", "LOTO / de-energization"),
        ("De-energize and verify zero energy", "LOTO / de-energization"),
        ("Light curtain certified in June", "Machine guarding / interlock"),
        ("Bollards and barrier rail at the door", "Hard physical barrier"),
        ("Full body harness with anchor point", "Fall arrest / restraint"),
        ("Trench box installed before entry", "Trench protection"),
        ("Cat 4 PPE arc flash suit required", "Specialty engineered PPE"),
    ],
)
def test_direct_controls_recognized(text, expected_type):
    result = classify_control(text)
    assert result.is_direct is True
    assert result.control_type == expected_type


@pytest.mark.parametrize(
    "text,label",
    [
        ("Operators trained annually", "non-direct: training / qualification"),
        ("Written procedure and permit required", "non-direct: procedure / permit"),
        ("High-vis vests and safety glasses", "non-direct: standard PPE"),
        ("5 mph signs and a painted stop line", "non-direct: warning / awareness"),
        ("Chemical fume hood", "non-direct: local ventilation"),
        ("Monthly supervisor inspection", "non-direct: administrative / supervision"),
    ],
)
def test_non_direct_controls_named_not_credited(text, label):
    result = classify_control(text)
    assert result.is_direct is False
    assert result.control_type == label


def test_direct_control_wins_when_mixed_with_ppe():
    result = classify_control("LOTO EP-201, arc flash suit, gloves, training")
    assert result.is_direct is True


def test_no_control_text_scores_absent():
    for text in ["", None, "   "]:
        result = classify_control(text)
        assert result.is_direct is False
        assert result.control_type == "none"


def test_unrecognized_control_text_scores_absent():
    result = classify_control("see attached document")
    assert result.is_direct is False
    assert result.control_type == "none"


# --- tiering --------------------------------------------------------------


def test_tier1_uncontrolled_high_energy():
    result = assign_tier(True, False)
    assert result.tier == 1
    assert "no Direct Control" in result.rule


def test_tier1_failed_verification_overrides_documentation():
    result = assign_tier(True, True, "failed")
    assert result.tier == 1
    assert "failed" in result.rule


def test_tier2_unverified_and_uncertain():
    assert assign_tier(True, True, "unverified").tier == 2
    assert assign_tier(None, False).tier == 2  # unknown energy -> verify


def test_tier3_verified():
    assert assign_tier(True, True, "verified").tier == 3


def test_tier4_low_energy():
    assert assign_tier(False, False).tier == 4


def test_exposure_weight_ranks_by_frequency_and_headcount():
    assert exposure_weight("daily", 12) == 48
    assert exposure_weight("rare", 2) == 2
    assert exposure_weight(None, None) == 1  # unknowns default low
    assert exposure_weight("weekly", "bad") == 3


def test_heca_over_definite_rows_only():
    rows = [
        {"high_energy": True, "direct_control": True, "verification": "verified"},
        {"high_energy": True, "direct_control": True, "verification": "unverified"},
        {"high_energy": True, "direct_control": False, "verification": "absent"},
        {"high_energy": None, "direct_control": False},  # excluded
        {"high_energy": False, "direct_control": False},  # excluded
    ]
    assert documented_heca(rows) == pytest.approx(2 / 3)
    assert verified_heca(rows) == pytest.approx(1 / 3)


def test_failed_verification_not_counted_as_documented():
    rows = [{"high_energy": True, "direct_control": True, "verification": "failed"}]
    assert documented_heca(rows) == 0.0


def test_heca_none_when_no_high_energy_rows():
    assert documented_heca([{"high_energy": False, "direct_control": False}]) is None
