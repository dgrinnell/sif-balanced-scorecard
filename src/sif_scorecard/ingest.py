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

import csv
import io
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


# --------------------------------------------------------------------------
# Universal ingest: read any hazard-shaped export
# --------------------------------------------------------------------------

# Columns whose *names* suggest personal data. EHS exports routinely carry
# reporter and injured-person fields; surfacing them lets the user drop them
# before anything is displayed or downloaded.
PII_COLUMN_PATTERN = re.compile(
    r"\b(?:first|last|full) ?name\b|\bemployee\b|\bperson(?:nel)?\b|\bworker\b"
    r"|\binjured\b|\breporter\b|reported by|\bemail\b|e-?mail|\bphone\b"
    r"|\bmobile\b|\bssn\b|social security|\bdob\b|date of birth|\bbadge\b"
    r"|\binitials\b|\bcontact\b|\bsupervisor\b|\bmanager\b|home address",
    re.IGNORECASE,
)
# A bare "name" is only personal when it isn't naming a thing.
_BARE_NAME = re.compile(r"\bnames?\b", re.IGNORECASE)
_THING_NAME = re.compile(
    r"\b(?:site|task|file|project|company|product|equipment|asset|job|step"
    r"|document|report|sheet|column|process|program|system|area|building"
    r"|room|unit|device|machine|chemical|material|vendor|supplier|facility"
    r"|location|entity|department|field|test|method|study|lab|tool|line"
    r"|procedure|sub|business)\s*names?\b",
    re.IGNORECASE,
)
_EMAIL_VALUE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# Suggestion cues for the column-mapping step.
ROLE_PATTERNS: dict[str, str] = {
    "description": r"hazard|description|detail|finding|concern|task|activity|title|issue|narrative|event",
    "controls": r"control|safeguard|mitigat|barrier|protection|countermeasure|existing|current",
    "energy_source": r"energy|categor|hazard type|classification|source",
    "location": r"location|area|site|dept|department|building|zone|room|line",
    "frequency": r"frequenc|how often|periodic|interval|occurrence",
    "workers": r"exposed|headcount|# ?of|number of|people|crew size|employees",
    "verification": r"verif|audit|last (?:check|inspect|test)|status|result",
}


@dataclass(frozen=True)
class SheetProfile:
    """What a single sheet or CSV contains, after header detection."""

    name: str
    n_rows: int
    columns: list[str]
    header_row: int
    pii_columns: list[str]
    preview: pd.DataFrame


def detect_header_row(raw: pd.DataFrame, max_scan: int = 8) -> int:
    """Find the row that actually holds column names.

    System exports (incident databases, report builders, consolidated
    workbooks) stack a title and a description above the real header. The
    header is the earliest row with several distinct, short, mostly-text
    cells.
    """
    width = max((raw.notna().sum(axis=1).max(), 1))
    best_row, best_score = 0, -1.0
    for i in range(min(max_scan, len(raw))):
        values = [v for v in raw.iloc[i].tolist() if pd.notna(v)]
        if len(values) < 2:
            continue
        texts = [str(v).strip() for v in values]
        fullness = len(values) / width  # a header spans the table
        textiness = sum(1 for t in texts if not _looks_numeric(t)) / len(texts)
        shortish = sum(1 for t in texts if 0 < len(t) <= 60) / len(texts)
        # Deliberately no distinctness term: merged cells legitimately
        # produce repeated header labels, and penalizing that picked the
        # first data row instead. The position penalty breaks ties toward
        # the earliest qualifying row.
        score = fullness * textiness * shortish - i * 0.02
        if score > best_score:
            best_row, best_score = i, score
    return best_row


def _looks_numeric(text: str) -> bool:
    """True for values that read as data rather than a field label."""
    try:
        float(text.replace(",", ""))
        return True
    except (TypeError, ValueError):
        return bool(re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", text.strip()))


def detect_pii_columns(df: pd.DataFrame) -> list[str]:
    """Columns that look like personal data, by name or by email-shaped values."""
    flagged: list[str] = []
    for col in df.columns:
        label = str(col)
        is_personal = bool(PII_COLUMN_PATTERN.search(label)) or (
            bool(_BARE_NAME.search(label)) and not _THING_NAME.search(label)
        )
        if is_personal:
            flagged.append(col)
            continue
        sample = df[col].dropna().astype(str).head(25)
        if len(sample) and sample.str.contains(_EMAIL_VALUE).mean() > 0.2:
            flagged.append(col)
    return flagged


def read_table(file, sheet_name: str | None = None) -> pd.DataFrame:
    """Read a CSV or Excel sheet with header detection and encoding fallback."""
    name = getattr(file, "name", str(file)).lower()
    if name.endswith((".xlsx", ".xls")):
        raw = pd.read_excel(file, sheet_name=sheet_name or 0, header=None,
                            dtype=object)
    else:
        raw = _read_ragged_csv(file)
    if raw.empty:
        raise IngestError("The file (or selected sheet) is empty.")

    header_row = detect_header_row(raw)
    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    # Collapse the newlines and padding that spreadsheet headers carry, so
    # labels stay readable in a dropdown.
    df.columns = [
        re.sub(r"\s+", " ", str(c)).strip() if pd.notna(c) else f"column_{i}"
        for i, c in enumerate(raw.iloc[header_row].tolist())
    ]
    # Drop fully-empty columns and rows, and de-duplicate column labels.
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    seen: dict[str, int] = {}
    labels = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            labels.append(f"{col}.{seen[col]}")
        else:
            seen[col] = 0
            labels.append(col)
    df.columns = labels
    df.attrs["header_row"] = header_row
    return df


def _read_ragged_csv(file) -> pd.DataFrame:
    """Parse a CSV whose rows have differing field counts.

    Report-builder exports put a one-cell title above a many-cell header,
    which pandas rejects outright. Parsing with the csv module and padding
    short rows keeps those files readable.
    """
    if hasattr(file, "seek"):
        file.seek(0)
    payload = file.read() if hasattr(file, "read") else open(file, "rb").read()
    if isinstance(payload, bytes):
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:  # pragma: no cover - latin-1 decodes any byte string
            raise IngestError("Could not decode the file's text.")
    else:
        text = payload

    rows = [r for r in csv.reader(io.StringIO(text)) if any(str(c).strip() for c in r)]
    if not rows:
        raise IngestError("The file (or selected sheet) is empty.")
    width = max(len(r) for r in rows)
    padded = [
        [(c if str(c).strip() else None) for c in r] + [None] * (width - len(r))
        for r in rows
    ]
    return pd.DataFrame(padded, dtype=object)


def list_sheets(file) -> list[str]:
    """Sheet names for an Excel upload; empty list for CSV."""
    name = getattr(file, "name", str(file)).lower()
    if not name.endswith((".xlsx", ".xls")):
        return []
    return pd.ExcelFile(file).sheet_names


def profile_table(df: pd.DataFrame, name: str = "data") -> SheetProfile:
    """Summarize a loaded table for the mapping step."""
    return SheetProfile(
        name=name,
        n_rows=len(df),
        columns=[str(c) for c in df.columns],
        header_row=int(df.attrs.get("header_row", 0)),
        pii_columns=detect_pii_columns(df),
        preview=df.head(5),
    )


def suggest_column(columns: list[str], role: str) -> str | None:
    """Best-guess column for a mapping role, or None if nothing matches."""
    pattern = ROLE_PATTERNS.get(role)
    if not pattern:
        return None
    compiled = re.compile(pattern, re.IGNORECASE)
    matches = [c for c in columns if compiled.search(str(c))]
    if not matches:
        return None
    # Prefer the most specific (shortest) matching label.
    return min(matches, key=lambda c: len(str(c)))


def classify_table(
    df: pd.DataFrame,
    description_col: str,
    controls_col: str | None = None,
    energy_col: str | None = None,
    location_col: str | None = None,
    frequency_col: str | None = None,
    workers_col: str | None = None,
) -> pd.DataFrame:
    """Run the keyword classifiers over a mapped table.

    Returns a review table with one row per hazard: the classification, the
    phrase that produced it, and editable energy/control columns. Nothing
    here is a finding until a human reviews it.
    """
    from .classify import classify_control, classify_energy

    if description_col not in df.columns:
        raise IngestError(f"Column '{description_col}' is not in the file.")

    rows = []
    for _, record in df.iterrows():
        description = str(record[description_col] or "").strip()
        if not description:
            continue
        energy_text = description
        if energy_col and energy_col in df.columns:
            energy_text = f"{description} {record[energy_col]}"
        control_text = (
            str(record[controls_col]) if controls_col and controls_col in df.columns
            else ""
        )
        energy = classify_energy(energy_text)
        control = classify_control(control_text)
        rows.append(
            {
                "hazard": description[:180],
                "location": (
                    str(record[location_col])
                    if location_col and location_col in df.columns else ""
                ),
                "energy_source": energy.source or "",
                "high_energy": energy.label,
                "why_energy": energy.reason,
                "direct_control": control.is_direct,
                "control_type": control.control_type,
                "why_control": control.reason,
                "verification": "unverified" if control.is_direct else "absent",
                "exposure_freq": (
                    str(record[frequency_col])
                    if frequency_col and frequency_col in df.columns else "weekly"
                ),
                "workers_exposed": (
                    record[workers_col]
                    if workers_col and workers_col in df.columns else 1
                ),
            }
        )
    if not rows:
        raise IngestError(
            f"No rows had text in '{description_col}'. Pick the column that "
            "holds the hazard description."
        )
    return pd.DataFrame(rows)


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
