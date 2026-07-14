import json
from pathlib import Path

from typer.testing import CliRunner

from health_agent.cli.main import app


def test_prohibited_profile_claim_is_rejected_before_persistence(isolated_env: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile",
            "risk-add",
            "--name",
            "HPV一定会癌变",
            "--group",
            "condition_related",
            "--category",
            "invalid_claim",
            "--confirm",
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert isolated_env.exists() is False
