import json
import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.models import RadiationAcquisition, RadiationExposure
from health_agent.database.session import session_scope


def test_partial_dose_screen_confirmation_does_not_double_count_total(
    isolated_env: Path, request: pytest.FixtureRequest
) -> None:
    runner = CliRunner()
    fixture = (
        isolated_env.parent.parent.parent / "imports" / f"fictional-dose-screen-{uuid.uuid4()}.txt"
    )
    shutil.copy2(Path("tests/fixtures/fictional_dose_screen.txt"), fixture)
    request.addfinalizer(lambda: fixture.unlink(missing_ok=True))
    preview = runner.invoke(app, ["dicom", "dose-screen", str(fixture), "--dry-run", "--json"])
    assert preview.exit_code == 0, preview.output
    payload = json.loads(preview.stdout)
    selected = [
        item["id"]
        for item in payload["data"]["candidates"]
        if item["field"] in {"ctdi_vol", "event_dlp", "total_dlp", "protocol"}
    ]
    confirmed = runner.invoke(
        app,
        [
            "dicom",
            "dose-screen",
            str(fixture),
            "--confirm",
            "--candidate-ids",
            ",".join(selected),
            "--json",
        ],
    )
    assert confirmed.exit_code == 0, confirmed.output
    with session_scope() as session:
        exposure = session.scalar(select(RadiationExposure))
        assert exposure is not None
        assert exposure.details["total_dlp_mgy_cm"] == 186.0
        rows = session.scalars(select(RadiationAcquisition)).all()
        assert [row.dlp_mgy_cm for row in rows] == [84.0, 102.0]
        assert sum(row.dlp_mgy_cm or 0 for row in rows) == 186.0
