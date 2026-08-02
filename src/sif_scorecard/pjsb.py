"""Pre-Job Safety Brief (PJSB) quality scoring.

Implements the Construction Safety Research Alliance (CSRA) Pre-Job Safety
Meeting Scorecard: 15 binary statements, each with an official weight (3-5),
aggregated to a weighted quality score in [0, 1].

References:
    Bayona, A., Hallowell, M. R., Bhandari, S., & Raheemy, Y. (2026). Balanced
    approach to serious injury and fatality prevention. Journal of Safety
    Research, 98, 175-189. https://doi.org/10.1016/j.jsr.2026.06.007

    CSRA Pre-Job Safety Meeting Scorecard, csra.colorado.edu/qsl
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class RubricItem:
    """One statement on the CSRA scorecard."""

    number: int
    statement: str
    weight: int
    # Observable example behaviors from the scorecard's guidance page.
    criteria: tuple[str, ...] = ()


RUBRIC: tuple[RubricItem, ...] = (
    RubricItem(
        1,
        "Everyone performing the job was present at the meeting.",
        4,
        (
            "Everyone performing the planned task was present for the entire "
            "pre-job meeting.",
            "If working alone, plans were discussed with a manager, mentor, or "
            "co-worker.",
        ),
    ),
    RubricItem(
        2,
        "The discussion was held as close to the work as reasonably possible.",
        4,
        (
            "Meeting was held at or near where the work will be performed.",
            "Workspace was reviewed by the crew before starting the meeting.",
        ),
    ),
    RubricItem(
        3,
        "Work steps required to complete the job were identified and discussed.",
        4,
        (
            "Crew identified and discussed the major work steps.",
            "Facilitator confirmed the major work steps and plans to address "
            "changes and provided corrections if necessary.",
        ),
    ),
    RubricItem(
        4,
        "Necessary tools and equipment were identified and discussed.",
        3,
        (
            "Crew identified and discussed tools and equipment needed to safely "
            "complete the work.",
            "Facilitator confirmed that the crew had all necessary tools and "
            "equipment.",
        ),
    ),
    RubricItem(
        5,
        "Hazards associated with the job were identified and discussed.",
        5,
        ("Crew identified and discussed hazards associated with their tasks.",),
    ),
    RubricItem(
        6,
        "Hazards posed by the environment or surrounding work were identified "
        "and discussed.",
        4,
        (
            "Crew identified and discussed the hazards created by other crews.",
            "Crew discussed how hazards they create may impact other crews.",
            "Crew identified and discussed hazards posed by the environment.",
        ),
    ),
    RubricItem(
        7,
        "Controls for each hazard were identified and discussed.",
        5,
        (
            "Crew identified and discussed controls or management strategies "
            "associated with each identified hazard.",
        ),
    ),
    RubricItem(
        8,
        "All life-threatening hazards and their controls were emphasized.",
        5,
        (
            "Crew emphasized all hazards with the potential to cause serious "
            "injury or fatality.",
            "Crew emphasized all controls for all hazards with potential to "
            "cause serious injury or fatality.",
        ),
    ),
    RubricItem(
        9,
        "Hazards and necessary controls were documented.",
        3,
        (
            "Crew completed required pre-job documentation.",
            "Facilitator confirmed that pre-job documentation is readily "
            "accessible.",
        ),
    ),
    RubricItem(
        10,
        "All required permits were obtained and reviewed.",
        3,
        (
            "Facilitator confirmed that all required work permits were obtained "
            "and readily accessible.",
        ),
    ),
    RubricItem(
        11,
        "Potential changes were identified and discussed and a plan to address "
        "change was created.",
        4,
        (
            "Crew identified and discussed possible changes to the work and "
            "work environment.",
            "Crew discussed the impacts of those changes on the safety.",
        ),
    ),
    RubricItem(
        12,
        "The importance of stopping work to address an unexpected change, "
        "disruption, or hazard was discussed.",
        4,
        (
            "Crew identified and discussed potential work conditions to use "
            "Stop Work Authority.",
            "Crew discussed the protocol for using Stop Work Authority.",
        ),
    ),
    RubricItem(
        13,
        "Emergency response plans were reviewed, including individual roles "
        "and responsibilities.",
        3,
        (
            "Crew identified potential emergencies.",
            "Crew discussed the protocol to address emergencies.",
            "Crew discussed individual roles and responsibilities during an "
            "emergency.",
        ),
    ),
    RubricItem(
        14,
        "Crew actively demonstrated their understanding of their work steps, "
        "hazards, and controls.",
        3,
        (
            "Crew verbally acknowledged the hazards and controls.",
            "Crew demonstrated that they understand the safety expectations.",
            "Facilitator confirmed that the crew members understand their roles "
            "and responsibilities.",
        ),
    ),
    RubricItem(
        15,
        "All crew members participated in the discussion by identifying "
        "hazards and controls.",
        3,
        (
            "Crew was active in the conversation by identifying hazards and "
            "controls, voicing comments or concerns, and providing specific "
            "details.",
        ),
    ),
)

MAX_WEIGHTED_SCORE: int = sum(item.weight for item in RUBRIC)  # 57
ITEM_NUMBERS: frozenset[int] = frozenset(item.number for item in RUBRIC)


@dataclass(frozen=True)
class PJSBResult:
    """Scored pre-job safety brief."""

    weighted_score: int
    quality: float  # weighted_score / MAX_WEIGHTED_SCORE, in [0, 1]
    simple_proportion: float  # unweighted fraction of items present
    missing_items: tuple[RubricItem, ...] = field(default_factory=tuple)

    @property
    def missing_statements(self) -> list[str]:
        return [f"{i.number}. {i.statement}" for i in self.missing_items]


def score_pjsb(responses: Mapping[int, bool]) -> PJSBResult:
    """Score a pre-job safety brief from 15 binary item responses.

    Args:
        responses: mapping of item number (1-15) to True (present) / False
            (absent). All 15 items are required.

    Returns:
        PJSBResult with the weighted score (0-57), quality (0-1), unweighted
        proportion, and the list of missing items (highest weight first).
    """
    provided = set(responses)
    if provided != ITEM_NUMBERS:
        missing = sorted(ITEM_NUMBERS - provided)
        extra = sorted(provided - ITEM_NUMBERS)
        raise ValueError(
            f"Responses must cover items 1-15 exactly; "
            f"missing={missing}, unexpected={extra}"
        )

    weighted = sum(item.weight for item in RUBRIC if responses[item.number])
    present = sum(1 for item in RUBRIC if responses[item.number])
    missing_items = tuple(
        sorted(
            (item for item in RUBRIC if not responses[item.number]),
            key=lambda i: (-i.weight, i.number),
        )
    )
    return PJSBResult(
        weighted_score=weighted,
        quality=weighted / MAX_WEIGHTED_SCORE,
        simple_proportion=present / len(RUBRIC),
        missing_items=missing_items,
    )


def score_from_flags(flags: Sequence[bool]) -> PJSBResult:
    """Convenience wrapper: score from a sequence of 15 booleans (item order)."""
    if len(flags) != len(RUBRIC):
        raise ValueError(f"Expected {len(RUBRIC)} flags, got {len(flags)}")
    return score_pjsb({i + 1: bool(v) for i, v in enumerate(flags)})
