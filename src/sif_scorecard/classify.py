"""Deterministic, explainable classification of free-text hazard records.

An EHS team's existing JHA register, inspection log, or hazard list is free
text. To triage it against the energy-based framework you need two calls per
row: is this high-energy, and is a Direct Control present? This module makes
those calls with keyword rules rather than a language model, which matters
for three reasons: the same text always yields the same answer, every answer
reports the phrase that produced it, and a reviewer can overrule it before
anything is scored.

The rules encode the recognition cues in the high-energy literature
(Oguz Erkal & Hallowell, 2023; EEI *Power to Prevent*): >1,500 J of energy
is the SIF threshold, and a Direct Control must target the energy source,
mitigate it to non-SIF levels, and keep working when a person makes a
mistake.

Treat the output as a first pass for human review, never as a finding. Text
that matches nothing returns ``None`` for high-energy — genuinely unknown,
which routes to verification rather than to a guess in either direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- energy source cues ---------------------------------------------------
# Ordered: the first source whose pattern matches wins, so put the most
# specific/lethal mechanisms first.
ENERGY_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "excavation",
        r"trench|excavat|cave[\s-]?in|shoring|spoil pile|benching",
    ),
    (
        "chemical-explosive",
        r"confined space|permit[\s-]?required|tank entry|silo|vault entry"
        r"|explos|deflagrat|flammable (?:vapou?r|atmosphere|gas)|lel\b"
        r"|hydrogen|h2s|hydrogen sulfide|carbon monoxide|\bco\b poisoning"
        r"|oxygen[\s-]?deficien|asphyxiat|inert(?:ing|ed)? (?:gas|atmosphere)"
        r"|nitrogen purge|hydrofluoric|\bhf\b|pyrophoric",
    ),
    (
        "electrical",
        r"\d{2,4}\s?(?:v\b|volt)|energi[sz]ed|live (?:work|electrical|part)"
        r"|arc[\s-]?flash|switchgear|\bmcc\b|breaker|electrical panel"
        r"|electrocut|shock hazard|bus ?bar|transformer|high[\s-]?voltage"
        r"|electrical work|class 4 laser|laser (?:cutting|welding)",
    ),
    (
        "gravity-fall",
        r"fall (?:from|protection|arrest|hazard)|work(?:ing)? at height"
        r"|elevated (?:work|platform|surface)|roof|ladder|scaffold|mezzanine"
        r"|leading edge|floor opening|aerial lift|scissor lift|man ?lift"
        r"|\d+\s?(?:ft|feet|foot|m)\s+(?:high|above|elevation|drop)"
        r"|guard ?rail|parapet|catwalk",
    ),
    (
        "gravity-load",
        r"crane|hoist|rigging|\bsling\b|suspended load|overhead load"
        r"|dropped (?:object|load|tool)|pallet rack|racking|forklift load"
        r"|lifting (?:beam|fixture|device)|jib|davit|chain fall|die (?:pick|change)",
    ),
    (
        "motion",
        # "PIT" only when capitalized: the abbreviation, not "pump pit".
        r"forklift|fork ?truck|(?-i:\bPIT\b)|powered industrial truck|tow motor"
        r"|pallet jack|loader|yard truck|dock (?:leveler|plate)|struck[\s-]?by"
        r"|pedestrian|mobile equipment|vehicle (?:traffic|movement)"
        r"|traffic|backing|aisle",
    ),
    (
        "mechanical",
        r"conveyor|nip point|pinch point|unguarded|rotating|auger|calender"
        r"|\bpress\b|shear|lathe|milling|\bcnc\b|robot|entangle|amputat"
        r"|machine guard|drive shaft|\bpto\b|flywheel|die cutter|band ?saw"
        r"|table ?saw|grinder wheel|jam (?:clear|removal)",
    ),
    (
        "pressure",
        r"\d+\s?psi|compressed (?:air|gas)|pressuri[sz]ed|hydraulic"
        r"|pneumatic|steam (?:line|header|trap|system)|boiler|accumulator"
        r"|relief valve|pressure (?:test|vessel)|gas cylinder|hose whip"
        r"|autoclave|burst",
    ),
    (
        "temperature",
        r"molten|furnace|quench|hot work|welding|torch|cutting torch"
        r"|steam burn|scald|cryogen|liquid nitrogen|\bln2\b|dry ice"
        r"|hot (?:surface|oil|fluid|metal)|>?\s?\d{3}\s?°?\s?[cf]\b|kiln|oven",
    ),
)

# Text that indicates an ordinary, low-severity exposure. Only decisive when
# no high-energy pattern also matched.
LOW_ENERGY_PATTERN = (
    r"ergonomic|repetitive|carpal|strain|sprain|manual (?:lifting|handling)"
    r"|slip|trip|housekeeping|wet floor|paper ?cut|hand tool|utility knife"
    r"|razor|\bcut\b|laceration|abrasion|bruis|noise|hearing|dust|irritant"
    r"|office|computer|keyboard|monitor|mouse|eye ?strain|splash|glove"
)

# --- control cues ---------------------------------------------------------
# Direct Controls: targeted at the energy, effective, error-tolerant.
DIRECT_CONTROL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("LOTO / de-energization",
     r"\bloto\b|lock ?out|tag ?out|de[\s-]?energi[sz]|zero energy"
     r"|isolat(?:ion|ed|e) (?:point|valve|and verif)|blank(?:ing|ed) and blind"),
    ("Machine guarding / interlock",
     r"interlock|light curtain|two[\s-]?hand|hard guard|machine guard(?:ing|ed)"
     r"|fixed guard|barrier guard|presence sensing|safety mat|e[\s-]?stop gate"),
    ("Hard physical barrier",
     r"hard barrier|physical (?:barrier|separation|segregat)|bollard"
     r"|barrier rail|jersey barrier|fenc(?:e|ing)|enclosure|guard ?rail"
     r"|handrail|toe ?board"),
    ("Fall arrest / restraint",
     r"fall arrest|fall restraint|harness|lanyard|anchor(?:age)? point"
     r"|self[\s-]?retracting|srl\b|safety net"),
    ("Trench protection",
     r"trench box|trench shield|shoring|sloping|benching system"),
    ("Specialty engineered PPE",
     r"arc[\s-]?flash suit|arc rated|cat(?:egory)? [24] ppe|blast suit"
     r"|flash hood|switching hood"),
)

# Present but not a Direct Control: worth naming so the gap is concrete.
NON_DIRECT_CONTROL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("training / qualification",
     r"train(?:ed|ing)|qualified|competent person|experienc|certif(?:ied|ication)"
     r"|awareness|orientation|toolbox|briefing"),
    ("procedure / permit",
     r"procedure|\bsop\b|work instruction|permit|\bjha\b|checklist|policy"
     r"|protocol|review(?:ed)? (?:the )?plan"),
    ("standard PPE",
     r"\bppe\b|safety glass|goggle|face ?shield|hard ?hat|glove|steel[\s-]?toe"
     r"|hi[\s-]?vis|vest|ear (?:plug|muff)|respirator|apron|lab coat"),
    ("warning / awareness",
     r"sign(?:age|s)?\b|cone|warning (?:line|tape|light)|barricade tape"
     r"|caution|spotter|buddy system|flagger|horn|mirror|alarm|paint(?:ed)? line"),
    ("local ventilation",
     r"fume hood|exhaust hood|local (?:exhaust|ventilation)|snorkel"
     r"|ventilat|laminar flow|biosafety cabinet"),
    ("administrative / supervision",
     r"administrativ|supervis|monitor(?:ing)?|inspect(?:ion|ed)|audit"
     r"|housekeep|rotation|limit(?:ed)? (?:access|exposure)|speed limit"),
)


@dataclass(frozen=True)
class EnergyMatch:
    """Result of energy classification for one free-text record."""

    source: str | None  # e.g. "gravity-fall", None when nothing matched
    high_energy: bool | None  # None == uncertain, route to verification
    matched: str | None  # the phrase that triggered the call
    reason: str

    @property
    def label(self) -> str:
        if self.high_energy is True:
            return "yes"
        if self.high_energy is False:
            return "no"
        return "uncertain"


@dataclass(frozen=True)
class ControlMatch:
    """Result of control classification for one free-text record."""

    is_direct: bool
    control_type: str  # "none" when nothing matched
    matched: str | None
    reason: str


def _search(pattern: str, text: str) -> str | None:
    found = re.search(pattern, text, re.IGNORECASE)
    return found.group(0).strip() if found else None


def classify_energy(text: str) -> EnergyMatch:
    """Classify free text as high-energy, low-energy, or uncertain.

    High-energy patterns take precedence over low-energy ones, because a
    record that mentions both ("manual handling near the crane pick") still
    carries the lethal exposure.
    """
    text = str(text or "")
    if not text.strip():
        return EnergyMatch(None, None, None, "no text to classify")

    for source, pattern in ENERGY_PATTERNS:
        hit = _search(pattern, text)
        if hit:
            return EnergyMatch(
                source=source,
                high_energy=True,
                matched=hit,
                reason=f'matched "{hit}" → {source} (>1,500 J class)',
            )

    low = _search(LOW_ENERGY_PATTERN, text)
    if low:
        return EnergyMatch(
            source="low-energy",
            high_energy=False,
            matched=low,
            reason=f'matched "{low}" → ordinary-severity exposure',
        )

    return EnergyMatch(
        None, None, None,
        "no energy cue found — needs a human call (defaults to uncertain)",
    )


def classify_control(text: str) -> ControlMatch:
    """Detect whether the described control is a Direct Control.

    Direct patterns are checked first so that "arc flash suit and training"
    reads as controlled, while "training and gloves" does not.
    """
    text = str(text or "")
    if not text.strip():
        return ControlMatch(False, "none", None, "no control described")

    for control_type, pattern in DIRECT_CONTROL_PATTERNS:
        hit = _search(pattern, text)
        if hit:
            return ControlMatch(
                True, control_type, hit,
                f'matched "{hit}" → Direct Control ({control_type})',
            )

    for label, pattern in NON_DIRECT_CONTROL_PATTERNS:
        hit = _search(pattern, text)
        if hit:
            return ControlMatch(
                False, f"non-direct: {label}", hit,
                f'matched "{hit}" → {label}; targets behaviour or exposure, '
                "not the energy source",
            )

    return ControlMatch(
        False, "none", None,
        "no recognizable control described — scored absent",
    )
