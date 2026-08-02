"""Three-lens SIF scorecard dashboard.

Streamlit app presenting the balanced measurement framework from Bayona et al.
(2026): leading (PJSB quality), monitoring (HECA), and lagging (TRIR/SBLI)
indicators side by side, with the empirical SIF risk curve and a what-if
projection.

Run from the repo root:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sif_scorecard.risk import (  # noqa: E402
    HECA_COACHING_THRESHOLD,
    expected_sifs_per_1000_fte,
    projected_heca_gain_from_pjsb,
    risk_band,
    sif_reduction,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "synthetic_companies.csv"

# Palette: validated categorical pair + reserved status colors (light mode);
# passes CVD separation, normal-vision floor, and 3:1 surface contrast.
BLUE = "#2a78d6"  # series 1 / sequential hue
ORANGE = "#eb6834"  # series 2
CRITICAL = "#d03b3b"  # status: critical (always paired with a text label)
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, tickfont=dict(color=INK_MUTED)),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, tickfont=dict(color=INK_MUTED)),
)


@st.cache_data
def load_panel() -> pd.DataFrame:
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    from sif_scorecard.synthetic import generate_companies

    return generate_companies(n_companies=31, seed=42)


def main() -> None:
    st.set_page_config(page_title="SIF Balanced Scorecard", layout="wide")
    panel = load_panel()

    st.title("SIF Balanced Scorecard")
    st.caption(
        "Leading / monitoring / lagging safety measurement, after Bayona, "
        "Hallowell, Bhandari & Raheemy (2026), *J. Safety Research* 98. "
        "**All data shown is synthetic.**"
    )

    company_id = st.sidebar.selectbox("Company", panel["company_id"])
    row = panel.loc[panel["company_id"] == company_id].iloc[0]
    band = risk_band(row["heca"])

    st.sidebar.markdown("---")
    st.sidebar.subheader("What-if: improve pre-job briefs")
    pjsb_gain_pts = st.sidebar.slider(
        "PJSB quality improvement (points)", 0, 30, 10,
        help="Model 1: each +1 PJSB point is associated with +0.49 HECA points.",
    )

    # --- Three-lens tiles ---------------------------------------------------
    lens1, lens2, lens3 = st.columns(3)
    with lens1:
        st.subheader("Leading — input")
        st.caption("How safe *will* the job be?")
        st.metric(
            "PJSB quality",
            f"{row['pjsb'] * 100:.0f}%",
            help="Pre-Job Safety Brief quality: weighted share of the 15 "
            "CSRA scorecard elements observed in pre-job briefs (crew "
            "present, hazards and controls discussed, stop-work expectations, "
            "emergency plans...). Max 57 weighted points = 100%.",
        )
    with lens2:
        st.subheader("Monitoring — condition")
        st.caption("How safe *is* the job?")
        st.metric(
            "HECA score",
            f"{row['heca'] * 100:.0f}%",
            help="Share of high-energy hazards with a Direct Control in place.",
        )
        if row["heca"] < HECA_COACHING_THRESHOLD:
            st.error(f"⚠ Below 30% coaching threshold — {band.guidance}")
        else:
            st.caption(f"Band: **{band.name}** — {band.guidance}")
    with lens3:
        st.subheader("Lagging — output")
        st.caption("How safe *was* the job?")
        a, b = st.columns(2)
        a.metric(
            "TRIR",
            f"{row['trir']:.2f}",
            help="Total Recordable Incident Rate: OSHA-recordable injuries "
            "(medical treatment, restricted work, days away, fatalities) per "
            "200,000 worker-hours (~100 FTE-years). All injuries count "
            "equally, regardless of severity.",
        )
        b.metric(
            "SBLI",
            f"{row['sbli']:.2f}",
            help="Severity-Based Lagging Indicator: like TRIR, but injuries "
            "are weighted by severity (first aid x100, medical treatment "
            "x500, restricted work x750, days away x1500), so one serious "
            "case moves the rate far more than a minor one.",
        )

    st.markdown("---")

    # --- Risk curve ---------------------------------------------------------
    left, right = st.columns([3, 2])
    with left:
        heca_grid = np.linspace(0.0, 1.0, 101)
        curve = [expected_sifs_per_1000_fte(h) for h in heca_grid]
        fig = go.Figure()
        fig.add_vrect(
            x0=0, x1=HECA_COACHING_THRESHOLD * 100,
            fillcolor=CRITICAL, opacity=0.07, line_width=0,
        )
        fig.add_annotation(
            x=15, y=max(curve) * 0.97, text="coaching zone (<30%)",
            showarrow=False, font=dict(color=CRITICAL, size=12),
        )
        fig.add_trace(
            go.Scatter(
                x=heca_grid * 100, y=curve, mode="lines",
                line=dict(color=BLUE, width=2), name="Expected SIFs",
                hovertemplate="HECA %{x:.0f}%: %{y:.2f} SIFs per 1,000 FTE<extra></extra>",
            )
        )
        y_now = expected_sifs_per_1000_fte(row["heca"])
        fig.add_trace(
            go.Scatter(
                x=[row["heca"] * 100], y=[y_now], mode="markers+text",
                marker=dict(color=BLUE, size=12), text=[company_id],
                textposition="top right", textfont=dict(color=INK),
                hovertemplate=f"{company_id}: HECA %{{x:.0f}}%, "
                "%{y:.2f} expected SIFs<extra></extra>",
                showlegend=False,
            )
        )
        fig.update_layout(
            title="Expected SIFs per 1,000 FTE vs. HECA (paper Fig. 7)",
            xaxis_title="Baseline HECA score (%)",
            yaxis_title="Expected SIFs per 1,000 FTE",
            showlegend=False, height=420, **LAYOUT,
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Projection")
        heca_gain = projected_heca_gain_from_pjsb(pjsb_gain_pts / 100)
        target_heca = min(row["heca"] + heca_gain, 1.0)
        reduction = sif_reduction(row["heca"], target_heca)
        st.metric("Projected HECA", f"{target_heca * 100:.0f}%",
                  delta=f"+{heca_gain * 100:.1f} pts")
        st.metric("Expected SIF change", f"{-reduction * 100:.0f}%",
                  delta=f"{reduction * 100:.0f}% reduction", delta_color="normal")
        st.caption(
            "Pathway: PJSB → HECA (Model 1, +0.49 pts/pt) → SIFs (Table 8, "
            "−3%/HECA pt). Correlational evidence, not a causal guarantee."
        )

    # --- Leading/monitoring vs lagging correlations -------------------------
    st.subheader("Do short-term measures predict outcomes?")
    st.caption(
        "Each panel plots one short-term measure against one lagging outcome "
        "across all companies, with a least-squares trend line — the "
        "cross-lens links the paper validated (Models 2–3 and Finding 3). "
        "*r* is the Pearson correlation; company-level, correlational "
        "evidence."
    )
    panel_rates = panel.assign(
        sif_rate=panel["sif"] * 200_000 / panel["worker_hours"]
    )
    pairs = [
        ("pjsb", "trir", "PJSB vs TRIR", "PJSB quality (%)", "TRIR", 100),
        ("heca", "trir", "HECA vs TRIR", "HECA (%)", "TRIR", 100),
        ("heca", "sif_rate", "HECA vs SIF rate", "HECA (%)",
         "SIFs per 200k hrs", 100),
    ]
    titles = []
    for x_col, y_col, name, *_ in pairs:
        r = panel_rates[x_col].corr(panel_rates[y_col])
        titles.append(f"{name}  (r = {r:+.2f})")
    fig3 = make_subplots(rows=1, cols=3, subplot_titles=titles,
                         horizontal_spacing=0.08)
    for i, (x_col, y_col, _name, x_title, y_title, scale) in enumerate(pairs, 1):
        x = panel_rates[x_col] * scale
        y = panel_rates[y_col]
        fig3.add_trace(
            go.Scatter(
                x=x, y=y, mode="markers",
                marker=dict(color=BLUE, size=9,
                            line=dict(color=SURFACE, width=2)),
                customdata=panel_rates["company_id"],
                hovertemplate="%{customdata}: "
                f"{x_title} %{{x:.0f}}, {y_title} %{{y:.2f}}<extra></extra>",
                showlegend=False,
            ),
            row=1, col=i,
        )
        slope, intercept = np.polyfit(x, y, 1)
        x_line = np.array([x.min(), x.max()])
        fig3.add_trace(
            go.Scatter(
                x=x_line, y=slope * x_line + intercept, mode="lines",
                line=dict(color="#184f95", width=2), hoverinfo="skip",
                showlegend=False,
            ),
            row=1, col=i,
        )
        fig3.update_xaxes(title_text=x_title, row=1, col=i,
                          gridcolor=GRID, tickfont=dict(color=INK_MUTED))
        fig3.update_yaxes(title_text=y_title if i != 2 else None, row=1, col=i,
                          gridcolor=GRID, tickfont=dict(color=INK_MUTED))
    fig3.update_layout(
        height=380, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif",
                  color=INK),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig3.update_annotations(font_size=13)
    st.plotly_chart(fig3, use_container_width=True)

    # --- Peer scatter -------------------------------------------------------
    st.subheader("Peer comparison: PJSB quality vs. HECA")
    fig2 = go.Figure()
    for name, color in (("client", BLUE), ("contractor", ORANGE)):
        sub = panel[panel["type"] == name]
        fig2.add_trace(
            go.Scatter(
                x=sub["pjsb"] * 100, y=sub["heca"] * 100,
                mode="markers", name=name.capitalize(),
                marker=dict(color=color, size=10,
                            line=dict(color=SURFACE, width=2)),
                customdata=sub["company_id"],
                hovertemplate="%{customdata}: PJSB %{x:.0f}%, "
                "HECA %{y:.0f}%<extra></extra>",
            )
        )
    fig2.add_hline(
        y=HECA_COACHING_THRESHOLD * 100, line=dict(color=CRITICAL, width=1, dash="dot"),
        annotation_text="30% coaching threshold",
        annotation_font_color=CRITICAL,
    )
    fig2.update_layout(
        xaxis_title="PJSB quality (%)", yaxis_title="HECA (%)",
        height=420, legend=dict(orientation="h", y=1.08), **LAYOUT,
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Data table (all companies)"):
        st.dataframe(panel, use_container_width=True)


if __name__ == "__main__":
    main()
