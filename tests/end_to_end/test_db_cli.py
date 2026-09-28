from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.migrations import LATEST_SCHEMA_VERSION

runner = CliRunner()


def test_db_cli_dry_run_upgrade_version_and_verify(isolated_env: Path) -> None:
    preview = runner.invoke(app, ["db", "upgrade", "--dry-run", "--json"])
    assert preview.exit_code == 0, preview.output
    preview_data = json.loads(preview.output)
    assert preview_data["requires_confirmation"] is True
    assert [item["version"] for item in preview_data["data"]["pending"]] == list(
        range(1, LATEST_SCHEMA_VERSION + 1)
    )
    assert not isolated_env.exists()

    confirmed = runner.invoke(app, ["db", "upgrade", "--confirm", "--json"])
    assert confirmed.exit_code == 0, confirmed.output
    assert json.loads(confirmed.output)["data"]["applied"] == list(
        range(1, LATEST_SCHEMA_VERSION + 1)
    )
    version = runner.invoke(app, ["db", "version", "--json"])
    assert json.loads(version.output)["data"] == {
        "current": LATEST_SCHEMA_VERSION,
        "latest": LATEST_SCHEMA_VERSION,
    }
    verified = runner.invoke(app, ["db", "verify", "--json"])
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["data"]["valid"] is True
