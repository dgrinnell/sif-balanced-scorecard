# SharePoint list schemas

Two lists on the EHS site hold all field data. Both are simple enough to
create by hand in five minutes, or via PnP provisioning.

## List 1: `PJSB Assessments`

One row per observed/scored pre-job safety brief.

| Column | Type | Notes |
|---|---|---|
| Title | Single line | Crew or meeting name |
| AssessmentDate | Date | Defaults to today |
| Assessor | Person | Who scored it (or "PJSB Coach agent") |
| Source | Choice | `Field observation` / `Teams transcript` / `Notes` |
| Item01 … Item15 | Yes/No | The 15 scorecard statements, in CSRA order |
| WeightedScore | Number | 0–57; calculated by Flow 1 (weights 4,4,4,3,5,4,5,5,3,3,4,4,3,3,3) |
| QualityPct | Number | WeightedScore / 57 × 100 |
| CrewSize | Number | Optional |
| Site | Choice | Your site/project taxonomy |

## List 2: `HECA Observations`

One row per **high-energy hazard** observed during a task assessment (not one
row per task — pooled HECA needs hazard-level rows).

| Column | Type | Notes |
|---|---|---|
| Title | Single line | Hazard description ("Suspended load — crane pick") |
| ObservationDate | Date | |
| Assessor | Person | Must have passed the κ/ICC > 0.40 calibration gate |
| TaskID | Single line | Groups hazards observed on the same task |
| EnergySource | Choice | Gravity / Motion / Mechanical / Electrical / Pressure / Temperature / Chemical / Explosive |
| HighEnergy | Yes/No | > 1,500 J judgment; only Yes rows count toward HECA |
| DirectControlPresent | Yes/No | The HECA numerator |
| DirectControlType | Choice | LOTO / Hard barrier / Fall arrest / Specialty PPE / Other / None |
| Site | Choice | Same taxonomy as List 1 |

**HECA for any slice** = count(DirectControlPresent = Yes) / count(HighEnergy = Yes).

## Optional List 3: `Injury Log`

If injury data doesn't already live in your incident system, a minimal list
with `InjuryDate`, `Classification` (FA / MT / JT / DA / FT), `SIF` (Yes/No),
and monthly `WorkerHours` rows enables the TRIR/SBLI measures in Power BI.
Companies with an existing EHS incident system should connect Power BI to
that instead.
