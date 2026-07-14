from __future__ import annotations

import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.migrations import migrate
from health_agent.database.models import ImagingReport, Patient
from health_agent.database.session import session_scope

runner = CliRunner()


def test_imaging_list_returns_only_verified_records(isolated_env) -> None:
    migrate()
    with session_scope() as session:
        patient = session.get(Patient, "local-primary")
        assert patient is not None
        session.add_all(
            [
                ImagingReport(
                    patient_id=patient.id,
                    source_type="source_fact",
                    occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
                    verified=True,
                    verification_status="human_confirmed",
                    details={"modality": "CT", "body_region": "chest"},
                ),
                ImagingReport(
                    patient_id=patient.id,
                    source_type="system_inference",
                    verified=False,
                    details={"modality": "US", "body_region": "neck"},
                ),
            ]
        )

    result = runner.invoke(app, ["imaging", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["action"] == "imaging.list"
    assert len(payload["data"]["imaging"]) == 1
    assert payload["data"]["imaging"][0]["details"]["modality"] == "CT"
    assert payload["data"]["imaging"][0]["source_type"] == "source_fact"
