from health_agent.config import ROOT


def test_hermes_skill_is_cli_only_and_confirmation_gated() -> None:
    text = (ROOT / "hermes_skill/personal-health-manager/SKILL.md").read_text(encoding="utf-8")
    assert "uv run --project" in text
    assert "health <command> --json" in text
    assert "--dry-run --json" in text
    assert "--confirm --json" in text
    assert "Never run a database client" in text
    assert "conversation memory as a medical fact" in text
    assert "health profile" in text
    assert "Never diagnose a scar" in text
