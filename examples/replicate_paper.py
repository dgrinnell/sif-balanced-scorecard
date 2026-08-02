"""Replicate the analytical pipeline of Bayona et al. (2026) on synthetic data.

Generates a synthetic company panel calibrated to the paper's Table 6, fits
the Model 6 count regressions, and compares recovered coefficients to the
published ones. Run:

    python examples/replicate_paper.py
"""

from sif_scorecard.models import replicate_model6
from sif_scorecard.risk import (
    expected_sifs_per_1000_fte,
    projected_heca_gain_from_pjsb,
    sif_reduction,
)
from sif_scorecard.synthetic import generate_companies

PAPER_COEFS = {  # Table 8, HECA predictor (log-rate change per point)
    "FA": -0.02, "MT": -0.01, "JT": 0.04, "DA": -0.01, "FT": -0.08, "SIF": -0.03,
}


def main() -> None:
    panel = generate_companies(n_companies=200, seed=7)

    print("=== Synthetic panel (calibrated to Table 6) ===")
    print(panel[["pjsb", "heca", "trir", "sbli"]].describe().round(3))
    print()

    print("=== Model 6 replication: injury counts ~ HECA / PJSB ===")
    for result in replicate_model6(panel):
        line = result.summary_line()
        published = PAPER_COEFS.get(result.outcome)
        if result.predictor == "heca" and published is not None:
            line += f"   (paper: {published:+.2f})"
        print(line)
    print()

    print("=== Fig. 7 risk curve anchors ===")
    for heca in (0.0, 0.3, 0.5, 0.7, 0.9):
        print(
            f"  HECA {heca:.1f} -> {expected_sifs_per_1000_fte(heca):.2f} "
            "expected SIFs per 1,000 FTE"
        )
    print()

    print("=== What-if: raise PJSB quality by 10 points ===")
    heca_gain = projected_heca_gain_from_pjsb(0.10)
    reduction = sif_reduction(0.53, 0.53 + heca_gain)
    print(
        f"  +10 PJSB pts -> +{heca_gain * 100:.1f} HECA pts -> "
        f"{reduction * 100:.0f}% fewer expected SIFs"
    )


if __name__ == "__main__":
    main()
