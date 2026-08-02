# Quickstart for EHS professionals (no Copilot experience needed)

This is the copy-paste version of the M365 implementation. No coding, no IT
project, no Power BI. You need: a Microsoft 365 account, Excel, Microsoft
Forms, and ideally an M365 Copilot license. Total setup: about one afternoon.

Everything technical below is pre-written — your job is pasting.

---

## Step 1 — Create the "PJSB Coach" agent (15 minutes)

1. Open **Copilot** (office.com → Copilot, or the Teams Copilot app).
2. Click **Create agent** (sometimes under "Agents" in the right sidebar).
3. Skip the chat-style "Describe" screen and click the **Configure** tab.
4. Name: `PJSB Coach`.
5. Description: `Scores pre-job safety briefs against the CSRA 15-item
   scorecard and coaches supervisors.`
6. Into the **Instructions** box, paste the entire text block from
   [copilot-agent/instructions.md](copilot-agent/instructions.md)
   (everything inside the fenced block).
7. Click **Create**, then **share the agent link** with your supervisors.

**No Copilot license?** Paste the same instructions block at the start of a
chat in the free Copilot (copilot.microsoft.com) or any AI chat app, then
paste the brief notes underneath. Same result, slightly more pasting.

**Daily use:** after the morning brief, a supervisor pastes their notes or
the Teams meeting transcript to PJSB Coach and gets back a score out of
100%, the missed items, and one coaching tip. Under a minute.

---

## Step 2 — Two Microsoft Forms (30 minutes)

### Form A: "Pre-Job Brief Scorecard"

First two questions: **Crew/meeting name** (text) and **Date** (date).
Then 15 **Yes/No** questions, worded exactly:

1. Everyone performing the job was present at the meeting.
2. The discussion was held as close to the work as reasonably possible.
3. Work steps required to complete the job were identified and discussed.
4. Necessary tools and equipment were identified and discussed.
5. Hazards associated with the job were identified and discussed.
6. Hazards posed by the environment or surrounding work were identified and discussed.
7. Controls for each hazard were identified and discussed.
8. All life-threatening hazards and their controls were emphasized.
9. Hazards and necessary controls were documented.
10. All required permits were obtained and reviewed.
11. Potential changes were identified and discussed and a plan to address change was created.
12. The importance of stopping work to address an unexpected change, disruption, or hazard was discussed.
13. Emergency response plans were reviewed, including individual roles and responsibilities.
14. Crew actively demonstrated their understanding of their work steps, hazards, and controls.
15. All crew members participated in the discussion by identifying hazards and controls.

### Form B: "High-Energy Hazard Check" (one submission per hazard)

1. **Task / location** — text
2. **Date** — date
3. **Hazard description** — text
4. **Energy source** — choice: Gravity (falls >4 ft, dropped/suspended
   loads) · Motion (mobile equipment, vehicles) · Mechanical (rotating
   equipment) · Electrical (≥50 V) · Pressure (hydraulic, pneumatic, steam)
   · Temperature (steam, hot fluids) · Chemical/Explosive · Excavation
5. **Is this a high-energy hazard (could it kill or maim)?** — Yes/No
6. **Is a Direct Control present?** — Yes/No
   *(Direct Control = LOTO, hard barrier, fall arrest, blast suit —
   something targeted at the energy that works even if a person makes a
   mistake. Hard hats, gloves, and "being careful" do not count.)*

Both forms: click **Responses → Open in Excel** once, and Forms keeps an
Excel Online workbook updated automatically. Save both workbooks in your
EHS Teams channel's Files tab so the whole team sees them.

---

## Step 3 — Two Excel formulas (10 minutes)

**Brief quality score** — in Form A's workbook, first empty column, row 2
(assuming the 15 Yes/No answers sit in columns G through U — adjust the
range if your form has different lead columns):

```
=SUMPRODUCT(--(G2:U2="Yes"), {4,4,4,3,5,4,5,5,3,3,4,4,3,3,3})/57
```

Format the column as a percentage and fill down. This is the official CSRA
weighting (max 57 points).

**HECA** — in Form B's workbook, in a summary cell (assuming "high-energy?"
answers are in column G and "Direct Control present?" in column H):

```
=COUNTIFS(H:H,"Yes",G:G,"Yes")/COUNTIF(G:G,"Yes")
```

Format as a percentage. Then select that cell → **Conditional formatting →
red fill when the value is below 0.30**. Red means: the research found a
serious injury or fatality becomes a *likely* event — coach the crew and
close the control gap the same day.

---

## Step 4 — Only after the habit sticks (optional)

- **Automatic Teams alert:** Power Automate → Templates → search
  *"Forms response Teams"* → pick "Post a message to Teams when a new
  Forms response is submitted" → fill in your form and channel. Pure
  point-and-click.
- Whenever you're stuck, **ask Copilot itself**: *"Walk me through posting
  a Teams message automatically when someone submits my Microsoft Form."*
- The full build-out (SharePoint lists, weekly digests, Power BI, automatic
  transcript scoring) is documented in [README.md](README.md) — that's the
  multi-site version, not the starting point.

---

## The operating rules that make the numbers useful

- **Trust averages only after ~15 brief scores and ~15 task checks**
  (roughly 90 days at a daily/weekly cadence). Before that, use the data
  for coaching, not reporting.
- **HECA below 30% = act today**, not at the monthly review.
- **Items 5, 7, 8 missed** (hazards, controls, life-threatening emphasis)
  → that's tomorrow's brief topic. One item at a time, highest weight
  first.
- **Never attach individual consequences to scores.** The moment scores
  become a performance rating, people stop reporting honestly and the
  data dies. Scores rate briefs, not people.
