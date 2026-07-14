from __future__ import annotations

import pytest

from health_agent.constants import ActionLevel
from health_agent.errors import ValidationFailure
from health_agent.rules.red_flags import assess_red_flags
from health_agent.safety.evidence_policy import validate_source_type
from health_agent.safety.response_validator import validate_response
from health_agent.schemas.responses import ResponseEnvelope


def test_forbidden_pseudo_score_is_rejected() -> None:
    response = ResponseEnvelope(
        status="success", action="test", data={"label": "今日炎症指数", "value": 73}
    )
    with pytest.raises(ValidationFailure):
        validate_response(response)


@pytest.mark.parametrize("term", ["免疫力评分", "炎症评分", "个人癌症概率", "HPV一定会癌变"])
def test_personal_profile_forbidden_claims_are_rejected(term: str) -> None:
    response = ResponseEnvelope(status="success", action="profile.summary", data={"claim": term})
    with pytest.raises(ValidationFailure):
        validate_response(response)


def test_evidence_types_are_closed_enum() -> None:
    assert validate_source_type("source_fact").value == "source_fact"
    with pytest.raises(ValidationFailure):
        validate_source_type("ai_diagnosis")


def test_emergency_red_flag_is_action_a() -> None:
    result = assess_red_flags({"severe_chest_pain"})
    assert result.action_level is ActionLevel.A
    assert "severe_chest_pain" in result.matched


def test_anxiety_is_not_a_disease_probability_modifier() -> None:
    result = assess_red_flags({"worried_about_cancer"})
    assert result.action_level is ActionLevel.D
    assert not result.matched
