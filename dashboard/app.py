"""Three-lens SIF scorecard dashboard.

Two modes:

* **My site data** — upload your own PJSB assessment and HECA observation
  exports (the schemas the M365 capture forms produce) and get your site's
  leading/monitoring/lagging scorecard, the coaching agenda, and the risk
  projection.
* **Demo** — an anonymous synthetic 31-company panel calibrated to the
  study's published statistics, for exploring the framework itself.

Framework: Bayona, Hallowell, Bhandari & Raheemy (2026), *Journal of Safety
Research* 98, 175-189.

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

from sif_scorecard.ingest import (  # noqa: E402
    HECAUpload,
    IngestError,
    PJSBUpload,
    classify_table,
    heca_template,
    list_sheets,
    load_heca_file,
    load_pjsb_file,
    pjsb_template,
    profile_table,
    read_table,
    suggest_column,
)
from sif_scorecard.triage import (  # noqa: E402
    TIER_NAMES,
    assign_tier,
    documented_heca,
)
from sif_scorecard.lagging import sbli, trir  # noqa: E402
from sif_scorecard.risk import (  # noqa: E402
    BASELINE_MIN_ASSESSMENTS,
    HECA_COACHING_THRESHOLD,
    expected_sifs_per_1000_fte,
    projected_heca_gain_from_pjsb,
    risk_band,
    sif_reduction,
)

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "synthetic_companies.csv"

# Validated categorical pair + reserved status colors (light surface).
BLUE = "#2a78d6"
ORANGE = "#eb6834"
CRITICAL = "#d03b3b"
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

FONT = "system-ui, -apple-system, Segoe UI, sans-serif"
LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family=FONT, color=INK),
    margin=dict(l=10, r=10, t=40, b=10),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, tickfont=dict(color=INK_MUTED)),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, tickfont=dict(color=INK_MUTED)),
)

PJSB_HELP = (
    "Pre-Job Safety Brief quality: weighted share of the 15 CSRA scorecard "
    "elements observed in pre-job briefs (crew present, hazards and controls "
    "discussed, stop-work expectations, emergency plans...). Max 57 weighted "
    "points = 100%."
)
HECA_HELP = (
    "High-Energy Control Assessment: share of observed high-energy hazards "
    "(>1,500 J - the ones that can kill) that have a Direct Control in place, "
    "such as LOTO, a hard barrier, or fall arrest. Standard PPE, training, and "
    "procedures do not count."
)
TRIR_HELP = (
    "Total Recordable Incident Rate: OSHA-recordable injuries (medical "
    "treatment, restricted work, days away, fatalities) per 200,000 "
    "worker-hours (~100 FTE-years). All injuries count equally, regardless "
    "of severity."
)
SBLI_HELP = (
    "Severity-Based Lagging Indicator: like TRIR, but injuries are weighted "
    "by severity (first aid x100, medical treatment x500, restricted work "
    "x750, days away x1500), so one serious case moves the rate far more "
    "than a minor one."
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


@st.cache_data
def load_panel() -> pd.DataFrame:
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    from sif_scorecard.synthetic import generate_companies

    return generate_companies(n_companies=31, seed=42)


def read_upload(file) -> pd.DataFrame:
    """Read an uploaded CSV/Excel file, tolerating non-UTF-8 exports."""
    name = file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    try:
        return pd.read_csv(file)
    except UnicodeDecodeError:
        file.seek(0)
        return pd.read_csv(file, encoding="latin-1")


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def three_lens_tiles(
    pjsb: float | None,
    heca: float | None,
    trir_value: float | None,
    sbli_value: float | None,
) -> None:
    """Render the leading / monitoring / lagging tile row."""
    lens1, lens2, lens3 = st.columns(3)
    with lens1:
        st.subheader("Leading — input")
        st.caption("How safe *will* the job be?")
        st.metric(
            "PJSB quality",
            f"{pjsb * 100:.0f}%" if pjsb is not None else "—",
            help=PJSB_HELP,
        )
    with lens2:
        st.subheader("Monitoring — condition")
        st.caption("How safe *is* the job?")
        st.metric(
            "HECA score",
            f"{heca * 100:.0f}%" if heca is not None else "—",
            help=HECA_HELP,
        )
        if heca is not None:
            band = risk_band(heca)
            if heca < HECA_COACHING_THRESHOLD:
                st.error(f"⚠ Below 30% coaching threshold — {band.guidance}")
            else:
                st.caption(f"Band: **{band.name}** — {band.guidance}")
    with lens3:
        st.subheader("Lagging — output")
        st.caption("How safe *was* the job?")
        a, b = st.columns(2)
        a.metric(
            "TRIR",
            f"{trir_value:.2f}" if trir_value is not None else "—",
            help=TRIR_HELP,
        )
        b.metric(
            "SBLI",
            f"{sbli_value:.2f}" if sbli_value is not None else "—",
            help=SBLI_HELP,
        )


def risk_curve_figure(heca: float, label: str) -> go.Figure:
    """Fig. 7 exponential risk curve with the site/company plotted on it."""
    grid = np.linspace(0.0, 1.0, 101)
    curve = [expected_sifs_per_1000_fte(h) for h in grid]
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
            x=grid * 100, y=curve, mode="lines",
            line=dict(color=BLUE, width=2),
            hovertemplate="HECA %{x:.0f}%: %{y:.2f} SIFs per 1,000 FTE<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[heca * 100], y=[expected_sifs_per_1000_fte(heca)],
            mode="markers+text", marker=dict(color=BLUE, size=12),
            text=[label], textposition="top right", textfont=dict(color=INK),
            hovertemplate=f"{label}: HECA %{{x:.0f}}%, "
            "%{y:.2f} expected SIFs<extra></extra>",
        )
    )
    fig.update_layout(
        title="Expected SIFs per 1,000 FTE vs. HECA (paper Fig. 7)",
        xaxis_title="Baseline HECA score (%)",
        yaxis_title="Expected SIFs per 1,000 FTE",
        showlegend=False, height=420, **LAYOUT,
    )
    return fig


def projection_panel(heca: float, pjsb_gain_pts: int) -> None:
    """What-if: PJSB improvement -> HECA gain -> SIF reduction."""
    st.subheader("Projection")
    heca_gain = projected_heca_gain_from_pjsb(pjsb_gain_pts / 100)
    target = min(heca + heca_gain, 1.0)
    reduction = sif_reduction(heca, target)
    st.metric("Projected HECA", f"{target * 100:.0f}%",
              delta=f"+{heca_gain * 100:.1f} pts")
    st.metric("Expected SIF change", f"{-reduction * 100:.0f}%",
              delta=f"{reduction * 100:.0f}% reduction")
    st.caption(
        "Pathway: PJSB → HECA (Model 1, +0.49 pts/pt) → SIFs (Table 8, "
        "−3%/HECA pt). Correlational evidence, not a causal guarantee."
    )


# --------------------------------------------------------------------------
# site-data mode
# --------------------------------------------------------------------------


def sidebar_site_inputs() -> dict:
    """Uploaders, injury counts, and templates. Returns the collected inputs."""
    st.sidebar.subheader("1. Upload field data")
    pjsb_file = st.sidebar.file_uploader(
        "PJSB assessments (one row per brief)",
        type=["csv", "xlsx", "xls"], key="pjsb_up",
    )
    heca_file = st.sidebar.file_uploader(
        "HECA observations (one row per hazard)",
        type=["csv", "xlsx", "xls"], key="heca_up",
    )
    with st.sidebar.expander("Need the file format?"):
        st.caption(
            "These match the SharePoint/Forms schemas in "
            "`m365-implementation/`. Column names are matched loosely — "
            "Item01–Item15, Q1–Q15, or the statement text all work."
        )
        st.download_button("Download PJSB template", csv_bytes(pjsb_template()),
                           "pjsb_template.csv", "text/csv")
        st.download_button("Download HECA template", csv_bytes(heca_template()),
                           "heca_template.csv", "text/csv")

    st.sidebar.subheader("2. Injury counts (optional)")
    st.sidebar.caption("For TRIR and SBLI. Leave hours at 0 to skip.")
    hours = st.sidebar.number_input("Worker-hours in period", 0, step=10_000,
                                    value=0)
    counts = {}
    cols = st.sidebar.columns(2)
    for i, (key, label) in enumerate(
        [("fa", "First aid"), ("mt", "Medical trt"), ("jt", "Restricted"),
         ("da", "Days away"), ("ft", "Fatalities")]
    ):
        counts[key] = cols[i % 2].number_input(label, 0, step=1, value=0)

    st.sidebar.subheader("3. What-if")
    gain = st.sidebar.slider(
        "PJSB quality improvement (points)", 0, 30, 10,
        help="Model 1: each +1 PJSB point is associated with +0.49 HECA points.",
    )
    return {
        "pjsb_file": pjsb_file, "heca_file": heca_file,
        "hours": hours, "counts": counts, "pjsb_gain": gain,
    }


def baseline_progress(pjsb: PJSBUpload | None, heca: HECAUpload | None) -> None:
    """Track the study's minimum sample (15 + 15) before scores are stable."""
    n_pjsb = pjsb.n_assessments if pjsb else 0
    n_heca = (heca.n_tasks or heca.result.n_hazards) if heca else 0
    target = BASELINE_MIN_ASSESSMENTS
    left, right = st.columns(2)
    for col, n, label in (
        (left, n_pjsb, "PJSB assessments"),
        (right, n_heca, "HECA task assessments"),
    ):
        with col:
            col.progress(min(n / target, 1.0), text=f"{label}: {n} / {target}")
    if n_pjsb < target or n_heca < target:
        st.info(
            f"**Baseline not yet stable.** The study's protocol is ≥{target} "
            f"pre-job brief assessments and ≥{target} HECA task assessments on "
            "randomly sampled crews within about 3 months. Until then, use "
            "these numbers for coaching — not for reporting or benchmarking."
        )


def coaching_agenda(pjsb: PJSBUpload) -> None:
    """Item-level miss rates: what to fix in tomorrow's brief."""
    st.subheader("Coaching agenda — which scorecard elements get missed")
    misses = pjsb.item_miss_rates
    misses = misses[misses["miss_rate"] > 0].head(10)
    if misses.empty:
        st.success("No missed elements across the uploaded assessments.")
        return
    labels = [
        f"{r.item}. {r.statement[:52]}{'…' if len(r.statement) > 52 else ''}"
        f" (wt {r.weight}){' ⚑ SIF-critical' if r.sif_critical else ''}"
        for r in misses.itertuples()
    ]
    fig = go.Figure(
        go.Bar(
            x=misses["miss_rate"] * 100, y=labels, orientation="h",
            marker=dict(
                color=[CRITICAL if c else BLUE for c in misses["sif_critical"]],
                line=dict(color=SURFACE, width=2),
            ),
            hovertemplate="%{y}<br>missed in %{x:.0f}% of briefs<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="% of briefs missing this element",
        height=90 + 34 * len(misses),
        yaxis=dict(autorange="reversed", tickfont=dict(color=INK, size=12),
                   gridcolor=GRID),
        xaxis=dict(gridcolor=GRID, tickfont=dict(color=INK_MUTED)),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    flagged = misses[misses["sif_critical"]]
    if not flagged.empty:
        items = ", ".join(str(i) for i in flagged["item"])
        st.error(
            f"⚑ SIF-critical element(s) {items} are being missed. Items 5, 7 "
            "and 8 (hazards identified, controls identified, life-threatening "
            "hazards emphasized) carry the highest weights because they are "
            "the strongest differentiators of serious-injury outcomes. Start "
            "coaching here."
        )


def uncontrolled_sources(heca: HECAUpload) -> None:
    """Where the uncontrolled high-energy exposure is concentrated."""
    if heca.uncontrolled_by_source.empty:
        return
    st.subheader("Uncontrolled high-energy exposure by energy source")
    data = heca.uncontrolled_by_source.head(10)
    fig = go.Figure(
        go.Bar(
            x=data.values, y=list(data.index), orientation="h",
            marker=dict(color=ORANGE, line=dict(color=SURFACE, width=2)),
            hovertemplate="%{y}: %{x} hazards without a Direct Control"
            "<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="Hazards observed without a Direct Control",
        height=90 + 34 * len(data),
        yaxis=dict(autorange="reversed", tickfont=dict(color=INK, size=12),
                   gridcolor=GRID),
        xaxis=dict(gridcolor=GRID, tickfont=dict(color=INK_MUTED)),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK),
        margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "These are the energy sources to target first — each row is an "
        "observed hazard that could kill or maim with nothing directly "
        "controlling it."
    )


def render_site_mode() -> None:
    inputs = sidebar_site_inputs()
    st.caption(
        "Upload your own field data to score your site. Files stay in this "
        "browser session — nothing is stored or sent anywhere."
    )

    pjsb_upload: PJSBUpload | None = None
    heca_upload: HECAUpload | None = None
    for file, loader, name in (
        (inputs["pjsb_file"], load_pjsb_file, "PJSB"),
        (inputs["heca_file"], load_heca_file, "HECA"),
    ):
        if file is None:
            continue
        try:
            result = loader(read_upload(file))
        except IngestError as exc:
            st.error(f"**{name} file:** {exc}")
            continue
        except Exception as exc:  # unreadable file, bad encoding, etc.
            st.error(f"**{name} file:** could not be read — {exc}")
            continue
        if name == "PJSB":
            pjsb_upload = result
        else:
            heca_upload = result

    if pjsb_upload is None and heca_upload is None:
        st.info(
            "**Start here:** upload a PJSB assessment export, a HECA "
            "observation export, or both, using the sidebar. Templates for "
            "both are in the sidebar's *Need the file format?* section — they "
            "match the Microsoft Forms / SharePoint schemas documented in "
            "`m365-implementation/`, so a Forms export drops straight in."
        )
        return

    hours = inputs["hours"]
    counts = inputs["counts"]
    trir_value = sbli_value = None
    if hours > 0:
        trir_value = trir(counts["mt"], counts["jt"], counts["da"], counts["ft"],
                          hours)
        sbli_value = sbli(counts["fa"], counts["mt"], counts["jt"], counts["da"],
                          hours)

    three_lens_tiles(
        pjsb_upload.mean_quality if pjsb_upload else None,
        heca_upload.score if heca_upload else None,
        trir_value, sbli_value,
    )

    st.markdown("---")
    baseline_progress(pjsb_upload, heca_upload)

    if heca_upload is not None:
        st.markdown("---")
        left, right = st.columns([3, 2])
        with left:
            st.plotly_chart(
                risk_curve_figure(heca_upload.score, "Your site"),
                use_container_width=True,
            )
        with right:
            projection_panel(heca_upload.score, inputs["pjsb_gain"])
        if heca_upload.n_excluded_low_energy:
            st.caption(
                f"{heca_upload.n_excluded_low_energy} low-energy row(s) were "
                "excluded from HECA — the score is defined only over "
                "high-energy hazards."
            )

    if pjsb_upload is not None:
        st.markdown("---")
        coaching_agenda(pjsb_upload)

    if heca_upload is not None:
        st.markdown("---")
        uncontrolled_sources(heca_upload)

    if pjsb_upload is not None:
        with st.expander("Scored assessments"):
            st.dataframe(pjsb_upload.assessments, use_container_width=True)


# --------------------------------------------------------------------------
# guided mode: any hazard file
# --------------------------------------------------------------------------

TIER_COLORS = {1: CRITICAL, 2: ORANGE, 3: BLUE, 4: INK_MUTED}


def render_guided_mode() -> None:
    st.caption(
        "Upload **any** hazard-shaped file — a JHA register, inspection log, "
        "risk register, LOTO list. The app reads it, proposes an energy and "
        "control classification for each row **with the phrase that produced "
        "it**, and lets you correct every call before anything is scored. No "
        "AI model is involved: same file in, same classification out."
    )
    upload = st.sidebar.file_uploader(
        "Hazard file", type=["csv", "xlsx", "xls"], key="guided_up"
    )
    if upload is None:
        st.info(
            "**Upload a file in the sidebar to begin** (on a narrow screen, "
            "open it with the **»** arrow at the top left). Works with the "
            "spreadsheets you already have — no reformatting. The app finds "
            "the header row even when the export stacks a title above it, "
            "handles legacy encodings, and flags columns that look like "
            "personal data before anything is displayed."
        )
        return

    # --- read, with sheet choice for workbooks ---------------------------
    try:
        sheets = list_sheets(upload)
        sheet = None
        if len(sheets) > 1:
            sheet = st.sidebar.selectbox("Sheet", sheets)
        table = read_table(upload, sheet_name=sheet)
        profile = profile_table(table, sheet or upload.name)
    except IngestError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Could not read that file — {exc}")
        return

    st.success(
        f"Read **{profile.n_rows} rows** and {len(profile.columns)} columns"
        + (f" from sheet *{sheet}*" if sheet else "")
        + (f" (header found on row {profile.header_row + 1})"
           if profile.header_row else "")
    )

    # --- privacy ----------------------------------------------------------
    keep_pii = False
    if profile.pii_columns:
        st.warning(
            "**Possible personal data.** These columns look like they name "
            f"people: {', '.join(f'`{c}`' for c in profile.pii_columns)}. "
            "They are dropped from everything shown and downloaded below "
            "unless you say otherwise — injury records identify individuals, "
            "and a triage register does not need them."
        )
        keep_pii = st.checkbox("Keep these columns anyway", value=False)
    if profile.pii_columns and not keep_pii:
        table = table.drop(columns=profile.pii_columns, errors="ignore")

    with st.expander("Preview the file as read"):
        st.dataframe(table.head(8), use_container_width=True)

    # --- column mapping ---------------------------------------------------
    st.subheader("1. Map your columns")
    st.caption(
        "Only the hazard description is required. The more you map, the "
        "better the first pass."
    )
    columns = [str(c) for c in table.columns]
    options = ["(none)"] + columns

    def pick(label: str, role: str, required: bool = False) -> str | None:
        guess = suggest_column(columns, role)
        if required:
            index = columns.index(guess) if guess in columns else 0
            return st.selectbox(label, columns, index=index)
        index = options.index(guess) if guess in options else 0
        choice = st.selectbox(label, options, index=index)
        return None if choice == "(none)" else choice

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        description_col = pick("Hazard description *", "description", True)
        controls_col = pick("Existing controls", "controls")
    with col_b:
        energy_col = pick("Hazard category / energy", "energy_source")
        location_col = pick("Location / area", "location")
    with col_c:
        frequency_col = pick("Frequency", "frequency")
        workers_col = pick("People exposed", "workers")

    # --- classify ---------------------------------------------------------
    try:
        proposed = classify_table(
            table, description_col, controls_col=controls_col,
            energy_col=energy_col, location_col=location_col,
            frequency_col=frequency_col, workers_col=workers_col,
        )
    except IngestError as exc:
        st.error(str(exc))
        return

    st.subheader("2. Review and correct the classification")
    counts = proposed["high_energy"].value_counts()
    a, b, c = st.columns(3)
    a.metric("Proposed high-energy", int(counts.get("yes", 0)))
    b.metric("Uncertain — needs your call", int(counts.get("uncertain", 0)))
    c.metric("Low-energy", int(counts.get("no", 0)))
    st.caption(
        "**Nothing here is a finding yet.** Every row shows the phrase that "
        "drove its classification — edit the `high_energy`, `direct_control` "
        "and `verification` cells directly. Rows the rules could not judge "
        "are marked *uncertain* rather than guessed, which is the honest "
        "default: unknown magnitude routes to field verification."
    )
    reviewed = st.data_editor(
        proposed,
        use_container_width=True,
        height=380,
        column_config={
            "high_energy": st.column_config.SelectboxColumn(
                "high_energy", options=["yes", "no", "uncertain"], required=True
            ),
            "direct_control": st.column_config.CheckboxColumn("direct_control"),
            "verification": st.column_config.SelectboxColumn(
                "verification",
                options=["verified", "unverified", "failed", "absent"],
                required=True,
            ),
            "why_energy": st.column_config.TextColumn("why_energy", width="medium"),
            "why_control": st.column_config.TextColumn("why_control", width="medium"),
        },
        disabled=["hazard", "location", "why_energy", "why_control"],
        key="review_editor",
    )

    # --- score ------------------------------------------------------------
    rows = []
    for record in reviewed.to_dict("records"):
        high = {"yes": True, "no": False}.get(record["high_energy"], None)
        tiered = assign_tier(
            high, bool(record["direct_control"]), record["verification"],
            record["exposure_freq"], record["workers_exposed"],
        )
        rows.append({**record, "high_energy_bool": high, "tier": tiered.tier,
                     "rule": tiered.rule, "exposure_weight": tiered.exposure_weight})
    scored = pd.DataFrame(rows)

    st.subheader("3. Your ranked SIF exposure register")
    heca_rows = [
        {"high_energy": r["high_energy_bool"], "direct_control": r["direct_control"],
         "verification": r["verification"]}
        for r in rows
    ]
    heca_value = documented_heca(heca_rows)
    m1, m2, m3 = st.columns(3)
    m1.metric("Tier 1 — act now", int((scored["tier"] == 1).sum()))
    m2.metric("Tier 2 — verify", int((scored["tier"] == 2).sum()))
    m3.metric(
        "Documented HECA",
        f"{heca_value:.0%}" if heca_value is not None else "—",
        help=HECA_HELP,
    )

    if heca_value is not None:
        left, right = st.columns([3, 2])
        with left:
            st.plotly_chart(risk_curve_figure(heca_value, "Your site"),
                            use_container_width=True)
        with right:
            projection_panel(heca_value, 10)

    for tier in (1, 2, 3, 4):
        group = scored[scored["tier"] == tier].sort_values(
            "exposure_weight", ascending=False
        )
        if group.empty:
            continue
        with st.expander(f"{TIER_NAMES[tier]} — {len(group)} row(s)",
                         expanded=(tier == 1)):
            st.dataframe(
                group[["hazard", "location", "energy_source", "control_type",
                       "rule", "exposure_weight"]],
                use_container_width=True, hide_index=True,
            )

    st.markdown("---")
    st.download_button(
        "⬇ Download normalized hazards.csv",
        csv_bytes(scored.drop(columns=["high_energy_bool"])),
        "hazards.csv", "text/csv",
    )
    st.caption(
        "This normalized file is the input format for a full SIF triage — "
        "hand it to an analyst, or keep it as the register of record. "
        "Classifications are a keyword first pass reviewed by you; documents "
        "are not field conditions, so verify Tier 1 and Tier 2 rows on site."
    )


# --------------------------------------------------------------------------
# demo mode
# --------------------------------------------------------------------------


def render_demo_mode() -> None:
    panel = load_panel()
    company_id = st.sidebar.selectbox("Company", panel["company_id"])
    row = panel.loc[panel["company_id"] == company_id].iloc[0]
    st.sidebar.markdown("---")
    st.sidebar.subheader("What-if: improve pre-job briefs")
    gain = st.sidebar.slider(
        "PJSB quality improvement (points)", 0, 30, 10,
        help="Model 1: each +1 PJSB point is associated with +0.49 HECA points.",
    )
    st.caption(
        "Synthetic 31-company panel calibrated to the study's published "
        "statistics. **All data shown here is synthetic** — switch to *My "
        "site data* in the sidebar to score your own."
    )

    three_lens_tiles(row["pjsb"], row["heca"], row["trir"], row["sbli"])
    st.markdown("---")

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(risk_curve_figure(row["heca"], company_id),
                        use_container_width=True)
    with right:
        projection_panel(row["heca"], gain)

    st.subheader("Do short-term measures predict outcomes?")
    st.caption(
        "Each panel plots one short-term measure against one lagging outcome "
        "across all companies, with a least-squares trend line — the "
        "cross-lens links the paper validated (Models 2–3 and Finding 3). "
        "*r* is the Pearson correlation; company-level, correlational "
        "evidence."
    )
    rates = panel.assign(sif_rate=panel["sif"] * 200_000 / panel["worker_hours"])
    pairs = [
        ("pjsb", "trir", "PJSB vs TRIR", "PJSB quality (%)", "TRIR"),
        ("heca", "trir", "HECA vs TRIR", "HECA (%)", "TRIR"),
        ("heca", "sif_rate", "HECA vs SIF rate", "HECA (%)", "SIFs per 200k hrs"),
    ]
    titles = [
        f"{name}  (r = {rates[x].corr(rates[y]):+.2f})"
        for x, y, name, *_ in pairs
    ]
    fig = make_subplots(rows=1, cols=3, subplot_titles=titles,
                        horizontal_spacing=0.08)
    for i, (x_col, y_col, _n, x_title, y_title) in enumerate(pairs, 1):
        x = rates[x_col] * 100
        y = rates[y_col]
        fig.add_trace(
            go.Scatter(
                x=x, y=y, mode="markers",
                marker=dict(color=BLUE, size=9,
                            line=dict(color=SURFACE, width=2)),
                customdata=rates["company_id"],
                hovertemplate="%{customdata}: "
                f"{x_title} %{{x:.0f}}, {y_title} %{{y:.2f}}<extra></extra>",
                showlegend=False,
            ),
            row=1, col=i,
        )
        slope, intercept = np.polyfit(x, y, 1)
        line_x = np.array([x.min(), x.max()])
        fig.add_trace(
            go.Scatter(x=line_x, y=slope * line_x + intercept, mode="lines",
                       line=dict(color="#184f95", width=2), hoverinfo="skip",
                       showlegend=False),
            row=1, col=i,
        )
        fig.update_xaxes(title_text=x_title, row=1, col=i, gridcolor=GRID,
                         tickfont=dict(color=INK_MUTED))
        fig.update_yaxes(title_text=y_title if i != 2 else None, row=1, col=i,
                         gridcolor=GRID, tickfont=dict(color=INK_MUTED))
    fig.update_layout(
        height=380, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK), margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_annotations(font_size=13)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Peer comparison: PJSB quality vs. HECA")
    fig2 = go.Figure()
    for name, color in (("client", BLUE), ("contractor", ORANGE)):
        sub = panel[panel["type"] == name]
        fig2.add_trace(
            go.Scatter(
                x=sub["pjsb"] * 100, y=sub["heca"] * 100, mode="markers",
                name=name.capitalize(),
                marker=dict(color=color, size=10,
                            line=dict(color=SURFACE, width=2)),
                customdata=sub["company_id"],
                hovertemplate="%{customdata}: PJSB %{x:.0f}%, "
                "HECA %{y:.0f}%<extra></extra>",
            )
        )
    fig2.add_hline(
        y=HECA_COACHING_THRESHOLD * 100,
        line=dict(color=CRITICAL, width=1, dash="dot"),
        annotation_text="30% coaching threshold", annotation_font_color=CRITICAL,
    )
    fig2.update_layout(
        xaxis_title="PJSB quality (%)", yaxis_title="HECA (%)", height=420,
        legend=dict(orientation="h", y=1.08), **LAYOUT,
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Data table (all companies)"):
        st.dataframe(panel, use_container_width=True)


# --------------------------------------------------------------------------


def main() -> None:
    # The sidebar holds every control, so it must not start collapsed —
    # otherwise a first-time visitor is told to upload a file in a sidebar
    # they cannot see.
    st.set_page_config(
        page_title="SIF Balanced Scorecard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("SIF Balanced Scorecard")
    st.caption(
        "Leading / monitoring / lagging safety measurement, after Bayona, "
        "Hallowell, Bhandari & Raheemy (2026), *J. Safety Research* 98."
    )
    mode = st.sidebar.radio(
        "Data source",
        ["Any hazard file (guided)", "PJSB / HECA exports", "Demo — synthetic panel"],
        index=0,
        help="Start with 'Any hazard file' if you have a JHA register, "
        "inspection log, or risk register. Use 'PJSB / HECA exports' if you "
        "are already capturing scorecard and hazard-observation data.",
    )
    st.sidebar.markdown("---")
    if mode.startswith("Any"):
        render_guided_mode()
    elif mode.startswith("PJSB"):
        render_site_mode()
    else:
        render_demo_mode()
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "🔒 Files are processed in this session's memory and are not stored "
        "or sent anywhere. For confidential injury records, run the app "
        "locally: `streamlit run dashboard/app.py`."
    )


if __name__ == "__main__":
    main()
