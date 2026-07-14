from __future__ import annotations

import json

from typer.testing import CliRunner

from health_agent.cli.main import app

runner = CliRunner()


def test_init_status_doctor_json_contract(isolated_env) -> None:
    for command, action in (
        (["init", "--json"], "init"),
        (["status", "--json"], "status"),
        (["doctor", "--json"], "doctor"),
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["action"] == action
        assert payload["warnings"] == []
        assert payload["uncertainties"] == []
        assert payload["error"] is None
