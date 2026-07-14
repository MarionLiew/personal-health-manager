import json
from pathlib import Path

from typer.testing import CliRunner

from health_agent.cli.main import app


def assert_json_error(arguments: list[str], expected_code: str) -> None:
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["data"] is None
    assert payload["error"]["code"] == expected_code
    assert "Traceback" not in result.stdout


def test_json_errors_cover_missing_argument_invalid_date_and_confirmation_gate(
    isolated_env: Path,
) -> None:
    assert_json_error(["symptoms", "show", "--json"], "INVALID_ARGUMENT")
    assert_json_error(
        [
            "symptoms",
            "add",
            "--name",
            "虚构疼痛",
            "--started",
            "not-a-date",
            "--dry-run",
            "--json",
        ],
        "VALIDATION_ERROR",
    )
    assert_json_error(["followup", "add", "--title", "虚构复查", "--json"], "VALIDATION_ERROR")
