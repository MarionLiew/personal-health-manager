from health_agent.constants import SourceType
from health_agent.errors import ValidationFailure


def validate_source_type(value: str) -> SourceType:
    try:
        return SourceType(value)
    except ValueError as exc:
        raise ValidationFailure(f"Unsupported evidence source type: {value}") from exc
