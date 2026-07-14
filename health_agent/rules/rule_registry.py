from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    version: str
    production: bool
    guideline_reference_id: str | None


# No fabricated production guideline is shipped. Deterministic safety/routing rules are explicit.
RULES = {
    "red-flags-v1": RuleMetadata("red-flags-v1", "1.0.0", False, None),
    "examination-decision-v1": RuleMetadata("examination-decision-v1", "1.0.0", False, None),
}
