# Power BI measures (DAX)

Connect to the two SharePoint lists (and your injury/hours source), then add
these measures. Layout mirrors the paper's Fig. 1: three columns — Leading /
Monitoring / Lagging — plus the risk curve.

```dax
// ---- Leading: PJSB quality -------------------------------------------
PJSB Quality % =
AVERAGE ( 'PJSB Assessments'[QualityPct] )

PJSB Quality (90d) =
CALCULATE (
    [PJSB Quality %],
    DATESINPERIOD ( 'Date'[Date], MAX ( 'Date'[Date] ), -90, DAY )
)

// ---- Monitoring: pooled HECA -----------------------------------------
HECA % =
VAR HighEnergy =
    CALCULATE (
        COUNTROWS ( 'HECA Observations' ),
        'HECA Observations'[HighEnergy] = TRUE ()
    )
VAR Controlled =
    CALCULATE (
        COUNTROWS ( 'HECA Observations' ),
        'HECA Observations'[HighEnergy] = TRUE (),
        'HECA Observations'[DirectControlPresent] = TRUE ()
    )
RETURN
    DIVIDE ( Controlled, HighEnergy ) * 100

HECA Below Coaching Threshold =
IF ( [HECA %] < 30, "⚠ COACHING ZONE", "OK" )

// ---- Lagging: TRIR and SBLI ------------------------------------------
TRIR =
DIVIDE (
    ( [MT Count] + [JT Count] + [DA Count] + [FT Count] ) * 200000,
    [Worker Hours]
)

SBLI =
DIVIDE (
    ( 100 * [FA Count] + 500 * [MT Count]
      + 750 * [JT Count] + 1500 * [DA Count] ) * 200,
    [Worker Hours]
)

// ---- Risk projection (paper Fig. 7 / Table 8) ------------------------
Expected SIFs per 1000 FTE =
2.5 * EXP ( -0.03 * [HECA %] )

// ---- Baseline protocol progress --------------------------------------
PJSB Baseline Progress =
VAR n =
    CALCULATE (
        COUNTROWS ( 'PJSB Assessments' ),
        DATESINPERIOD ( 'Date'[Date], MAX ( 'Date'[Date] ), -90, DAY )
    )
RETURN
    MIN ( n, 15 ) & " / 15 assessments (90 days)"

HECA Baseline Progress =
VAR n =
    CALCULATE (
        DISTINCTCOUNT ( 'HECA Observations'[TaskID] ),
        DATESINPERIOD ( 'Date'[Date], MAX ( 'Date'[Date] ), -90, DAY )
    )
RETURN
    MIN ( n, 15 ) & " / 15 task assessments (90 days)"
```

Count measures (`FA Count`, `MT Count`, …, `Worker Hours`) are simple sums
over your injury/hours source, filtered by classification.

**Page layout suggestions**

- Row 1: three KPI cards — PJSB Quality (90d), HECA % (with the coaching-zone
  conditional formatting + label, never color alone), TRIR & SBLI.
- Row 2: PJSB item-level bar chart (miss rate per scorecard item — this is
  the coaching agenda) and uncontrolled-energy-source bar chart.
- Row 3: the Expected-SIFs curve as a line chart over HECA 0–100 with a dot
  at the current pooled HECA.
- Slicers: date range and Site, one row above the charts.
