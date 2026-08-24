"""Ingest a site's own PJSB and HECA exports.

Real EHS data arrives as Microsoft Forms exports, SharePoint list downloads,
or hand-kept spreadsheets — inconsistent column names, and booleans spelled
a dozen different ways. These loaders are deliberately tolerant about
formatting and strict about meaning: they will find the 15 scorecard items
whether the columns are called ``Item01``, ``Q1``, ``5``, or the statement
text itself, but they never guess a missing answer (a blank is scored
absent, matching the field rule that an element not observed was not
present).

The expected schemas match the SharePoint lists documented in
``m365-implementation/sharepoint/lists-schema.md``, so a Forms export drops
straight in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .heca import HazardObservation, HECAResult, heca_score
from .pjsb import MAX_WEIGHTED_SCORE, RUBRIC

# Spellings of "yes" seen across Forms, SharePoint, Excel, and paper-to-CSV.
TRUE_TOKENS = frozenset(
    {"yes", "y", "true", "t", "1", "1.0", "x", "✓", "✔", "present", "complete",
     "completed", "done", "pass", "passed", "ok"}
)
FALSE_TOKENS = frozenset(
    {"no", "n", "false", "f", "0", "0.0", "", "absent", "missing", "none",
     "incomplete", "fail", "failed", "n/a", "na", "-", "nan"}
)

_ITEM_NUMBER = re.compile(
    r"^\s*(?:item|itm|q|question|element|stmt|statement|#)?[\s_\-.#]*0*(\d{1,2})"
    r"\s*[.):]?\s*$",
    re.IGNORECASE,
)
_HECA_CONTROL = re.compile(
    r"direct[\s_]*control|control[\s_]*(present|in[\s_]*place)|has[\s_]*control"
    r"|controlled",
    re.IGNORECASE,
)
_HECA_HIGH_ENERGY = re.compile(
    r"high[\s_]*energy|1500|serious[\s_]*potential|sif[\s_]*potential",
    re.IGNORECASE,
)
_HECA_SOURCE = re.compile(
    r"energy[\s_]*(source|type)|hazard[\s_]*(type|category)", re.IGNORECASE
)
_HECA_DESC = re.compile(
    r"hazard|description|title|task|observation|finding", re.IGNORECASE
)


class IngestError(ValueError):
    """Raised when a file cannot be interpreted; message is user-facing."""


def to_bool(value: object) -> bool:
    """Interpret a spreadsheet cell as present/absent.

    Anything unrecognized is treated as absent rather than raising: a
    partially filled scorecard is a real thing, and the field rule is that
    an element without affirmative evidence was not present.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return False
        return value != 0
    token = str(value).strip().lower()
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    # Unknown non-empty text: treat a leading "yes"/"true" as affirmative
    # (e.g. "Yes - verified by supervisor"), otherwise absent.
    return token.startswith(("yes", "true"))


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _statement_lookup() -> dict[str, int]:
    """Normalized rubric statement (and a shortened prefix) -> item number."""
    lookup: dict[str, int] = {}
    for item in RUBRIC:
        norm = _normalize(item.statement)
        lookup[norm] = item.number
        lookup[norm[:40]] = item.number
    return lookup


def find_item_columns(columns: list[str]) -> dict[int, str]:
    """Map scorecard item number (1-15) to the column holding its answer."""
    statements = _statement_lookup()
    found: dict[int, str] = {}
    for col in columns:
        match = _ITEM_NUMBER.match(str(col))
        if match:
            number = int(match.group(1))
            if 1 <= number <= 15:
                found.setdefault(number, col)
                continue
        norm = _normalize(col)
        number = statements.get(norm) or statements.get(norm[:40])
        if number:
            found.setdefault(number, col)
    return found


@dataclass(frozen=True)
class PJSBUpload:
    """Scored PJSB assessments from a site's own export."""

    assessments: pd.DataFrame  # per-assessment scores, original columns kept
    item_presence: pd.DataFrame  # bool matrix, columns 1-15
    n_assessments: int
    mean_quality: float  # weighted, 0-1

    @property
    def item_miss_rates(self) -> pd.DataFrame:
        """Per-item miss rate, worst first — the coaching agenda."""
        rows = []
        for item in RUBRIC:
            present = self.item_presence[item.number]
            rows.append(
                {
                    "item": item.number,
                    "statement": item.statement,
                    "weight": item.weight,
                    "miss_rate": float(1.0 - present.mean()),
                    "sif_critical": item.number in (5, 7, 8),
                }
            )
        return pd.DataFrame(rows).sort_values(
            ["miss_rate", "weight"], ascending=[False, False]
        )


def load_pjsb_file(df: pd.DataFrame) -> PJSBUpload:
    """Score a PJSB assessment export (one row per observed brief).

    Accepts item columns named ``Item01``…``Item15``, ``Q1``…``Q15``,
    ``1``…``15``, or the scorecard statement text. Raises IngestError with
    an actionable message when items are missing.
    """
    if df.empty:
        raise IngestError("The PJSB file has no rows.")

    columns = find_item_columns(list(df.columns))
    missing = sorted(set(range(1, 16)) - set(columns))
    if missing:
        raise IngestError(
            f"Could not find columns for scorecard item(s) {missing}. Name "
            "them Item01-Item15 (or 1-15, or the statement text). Download "
            "the template in the sidebar for the exact layout."
        )

    presence = pd.DataFrame(
        {n: df[col].map(to_bool) for n, col in sorted(columns.items())},
        index=df.index,
    )
    weights = pd.Series({item.number: item.weight for item in RUBRIC})
    weighted = presence.mul(weights, axis=1).sum(axis=1)

    assessments = df.copy()
    assessments["weighted_score"] = weighted
    assessments["quality"] = weighted / MAX_WEIGHTED_SCORE

    return PJSBUpload(
        assessments=assessments,
        item_presence=presence,
        n_assessments=len(df),
        mean_quality=float(assessments["quality"].mean()),
    )


@dataclass(frozen=True)
class HECAUpload:
    """Pooled HECA from a site's own hazard observations."""

    result: HECAResult
    n_rows_supplied: int
    n_excluded_low_energy: int
    uncontrolled_by_source: pd.Series = field(default_factory=pd.Series)
    n_tasks: int | None = None  # distinct TaskID values, if the export has them

    @property
    def score(self) -> float:
        return self.result.score


def load_heca_file(df: pd.DataFrame) -> HECAUpload:
    """Pool a HECA observation export (one row per observed hazard).

    Requires a Direct-Control column (any of "DirectControlPresent",
    "Control Present", "Controlled"...). If a high-energy column exists,
    only high-energy rows are counted — that is the HECA denominator by
    definition; low-energy rows are reported as excluded rather than
    silently dropped.
    """
    if df.empty:
        raise IngestError("The HECA file has no rows.")

    cols = {str(c): c for c in df.columns}
    control_col = next((c for c in cols if _HECA_CONTROL.search(c)), None)
    if control_col is None:
        raise IngestError(
            "Could not find a Direct Control column. Name it "
            "'DirectControlPresent' (Yes/No) — see the template in the "
            "sidebar."
        )
    high_col = next((c for c in cols if _HECA_HIGH_ENERGY.search(c)), None)
    source_col = next((c for c in cols if _HECA_SOURCE.search(c)), None)
    desc_col = next(
        (c for c in cols if _HECA_DESC.search(c) and c != source_col), None
    )
    task_col = next(
        (c for c in cols if re.search(r"task[\s_]*id|task$", str(c), re.I)), None
    )

    work = df.copy()
    n_supplied = len(work)
    if high_col is not None:
        keep = work[high_col].map(to_bool)
        work = work[keep]
    n_excluded = n_supplied - len(work)

    if work.empty:
        raise IngestError(
            "No high-energy hazards found in the file. HECA is only defined "
            "over high-energy hazards (>1,500 J) — if none were observed, "
            "record the tasks as having no high-energy exposure."
        )

    observations = [
        HazardObservation(
            description=str(row[desc_col]) if desc_col else "hazard",
            direct_control_present=to_bool(row[control_col]),
            energy_source=str(row[source_col]) if source_col else "",
        )
        for _, row in work.iterrows()
    ]
    result = heca_score(observations)

    uncontrolled = pd.Series(dtype=int)
    if source_col is not None:
        gaps = work[~work[control_col].map(to_bool)]
        if not gaps.empty:
            uncontrolled = (
                gaps[source_col].fillna("(unspecified)").value_counts()
            )

    return HECAUpload(
        result=result,
        n_rows_supplied=n_supplied,
        n_excluded_low_energy=n_excluded,
        uncontrolled_by_source=uncontrolled,
        n_tasks=int(work[task_col].nunique()) if task_col else None,
    )


def pjsb_template() -> pd.DataFrame:
    """Blank PJSB upload template with one worked example row."""
    row: dict[str, object] = {"Crew": "Line 2 AM crew", "Date": "2026-08-10"}
    for item in RUBRIC:
        row[f"Item{item.number:02d}"] = "Yes" if item.number not in (8, 12) else "No"
    return pd.DataFrame([row])


def heca_template() -> pd.DataFrame:
    """Blank HECA upload template with two worked example rows."""
    return pd.DataFrame(
        [
            {
                "TaskID": "T-001",
                "Date": "2026-08-10",
                "Hazard": "Suspended load over walkway",
                "EnergySource": "Gravity",
                "HighEnergy": "Yes",
                "DirectControlPresent": "No",
            },
            {
                "TaskID": "T-001",
                "Date": "2026-08-10",
                "Hazard": "480V panel work",
                "EnergySource": "Electrical",
                "HighEnergy": "Yes",
                "DirectControlPresent": "Yes",
            },
        ]
    )
