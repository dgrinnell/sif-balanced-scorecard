# Power Automate flows

Three flows connect capture to the scorecard. All are standard-connector only
(SharePoint, Teams, Office 365) — no premium licensing required unless noted.

## Flow 1 — Score on save (automated)

**Trigger:** When an item is created or modified in `PJSB Assessments`.

1. Compose the weighted score from the 15 Yes/No columns:

   ```
   WeightedScore =
       4*Item01 + 4*Item02 + 4*Item03 + 3*Item04 + 5*Item05
     + 4*Item06 + 5*Item07 + 5*Item08 + 3*Item09 + 3*Item10
     + 4*Item11 + 4*Item12 + 3*Item13 + 3*Item14 + 3*Item15
   ```

   (In the expression editor, use `if(triggerBody()?['Item01'], 4, 0) + …`.)
2. Update `WeightedScore` and `QualityPct = round(100 * WeightedScore / 57)`.
3. Condition: if `Item05`, `Item07`, or `Item08` is No (the SIF-critical
   items), post an adaptive card to the site's EHS Teams channel:
   "Yesterday's brief for *{Title}* skipped hazard/control discussion —
   coaching opportunity."

## Flow 2 — HECA threshold alert (scheduled, daily)

**Trigger:** Recurrence, daily 06:00.

1. Get `HECA Observations` rows from the trailing 30 days, `HighEnergy = Yes`.
2. Group by `Site` (Select + union trick, or a child flow per site).
3. For each site: `HECA = controlled / total`.
4. If HECA < **0.30** and total ≥ 5 hazards: post a Teams adaptive card to the
   site channel and email the site EHS lead — "Site HECA is {pct}%, below the
   30% threshold at which a SIF becomes a likely event (Bayona et al., 2026).
   Most frequent uncontrolled energy source: {top}."

## Flow 3 — Baseline progress + weekly digest (scheduled, Monday 07:00)

1. Count trailing-90-day rows: PJSB assessments and HECA task groups
   (distinct `TaskID`).
2. If either count < **15**, include a "baseline not yet stable" banner —
   the study's minimum sample is 15 + 15 within ~3 months.
3. Post a weekly digest card to the EHS channel: PJSB quality trend
   (this week vs. 4-week average), pooled HECA, top 3 missed scorecard
   items, top uncontrolled energy sources, and a deep link to the Power BI
   scorecard.

## Optional Flow 0 — Transcript hand-off

When a Teams meeting tagged "pre-job brief" ends, fetch the transcript
(Graph `onlineMeetings/{id}/transcripts`, premium/Graph connector), and post
it to the supervisor's chat with the PJSB Coach agent for scoring, or parse
the agent's CSV log line into `PJSB Assessments` directly.
