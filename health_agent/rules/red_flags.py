from __future__ import annotations

from dataclasses import dataclass

from health_agent.constants import ActionLevel


@dataclass(frozen=True)
class RedFlagResult:
    action_level: ActionLevel
    matched: tuple[str, ...]
    disclaimer: str


# These are conservative routing signals, not diagnostic rules.
URGENT_SIGNALS = {
    "severe_breathing_difficulty",
    "new_one_sided_weakness",
    "uncontrolled_bleeding",
    "loss_of_consciousness",
    "severe_chest_pain",
}


def assess_red_flags(signals: set[str]) -> RedFlagResult:
    matched = tuple(sorted(signals & URGENT_SIGNALS))
    return RedFlagResult(
        action_level=ActionLevel.A if matched else ActionLevel.D,
        matched=matched,
        disclaimer="This is emergency routing support, not a diagnosis or emergency service.",
    )
