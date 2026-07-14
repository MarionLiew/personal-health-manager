from __future__ import annotations

from health_agent.constants import SourceType
from health_agent.errors import ValidationFailure
from health_agent.safety.medical_boundaries import safety_policy
from health_agent.schemas.responses import ResponseEnvelope


def validate_response(response: ResponseEnvelope) -> ResponseEnvelope:
    policy = safety_policy()
    serialized = response.model_dump_json()
    forbidden = [term for term in policy["forbidden_score_terms"] if str(term) in serialized]
    if forbidden:
        raise ValidationFailure(f"Response contains prohibited pseudo-score terms: {forbidden}")
    allowed = {value.value for value in SourceType}
    for record in response.source_records:
        if ":" in record and record.split(":", 1)[0] not in allowed:
            raise ValidationFailure(f"Invalid source record classification: {record}")
    return response
