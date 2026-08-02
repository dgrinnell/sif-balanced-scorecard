import pytest

from sif_scorecard.lagging import sbli, sif_rate, trir


def test_trir_matches_paper_formula():
    # 2 MT + 1 JT + 1 DA + 0 FT over 400,000 hours -> 4 * 200000 / 400000 = 2.0
    assert trir(mt=2, jt=1, da=1, ft=0, worker_hours=400_000) == pytest.approx(2.0)


def test_trir_excludes_first_aid():
    # First aid is not an argument: recordables only.
    assert trir(mt=0, jt=0, da=0, ft=0, worker_hours=200_000) == 0.0


def test_sbli_severity_weighting():
    # One DA case should move SBLI 15x more than one FA case.
    base_hours = 2_000_000
    only_fa = sbli(fa=1, mt=0, jt=0, da=0, worker_hours=base_hours)
    only_da = sbli(fa=0, mt=0, jt=0, da=1, worker_hours=base_hours)
    assert only_da / only_fa == pytest.approx(15.0)


def test_sbli_formula_value():
    # (100*10 + 500*2 + 750*1 + 1500*1) * 200 / 500000 = 4250*200/500000 = 1.7
    assert sbli(fa=10, mt=2, jt=1, da=1, worker_hours=500_000) == pytest.approx(1.7)


def test_sif_rate():
    assert sif_rate(sif=3, worker_hours=600_000) == pytest.approx(1.0)


def test_validation():
    with pytest.raises(ValueError):
        trir(1, 1, 1, 0, worker_hours=0)
    with pytest.raises(ValueError):
        sbli(-1, 0, 0, 0, worker_hours=1000)
