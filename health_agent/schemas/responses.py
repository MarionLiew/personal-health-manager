from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from health_agent.constants import ActionLevel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    status: Literal["success", "error"]
    action: str
    data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    source_records: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    medical_action_level: ActionLevel | None = None
    error: ErrorDetail | None = None
