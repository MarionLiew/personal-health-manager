from health_agent.config import ROOT


def test_hermes_skill_is_cli_only_and_confirmation_gated() -> None:
    text = (ROOT / "hermes_skill/personal-health-manager/SKILL.md").read_text(encoding="utf-8")
    wrapper = (ROOT / "hermes_skill/personal-health-manager/tools/health.sh").read_text(
        encoding="utf-8"
    )
    assert "tools/health.sh <command> --json" in text
    assert 'exec uv run --project "$PROJECT_DIR" health "$@"' in wrapper
    assert 'config/hermes.yaml' in wrapper
    assert "health.sqlite3" not in wrapper
    assert "/data/" not in wrapper
    assert "--dry-run --json" in text
    assert "--confirm --json" in text
    assert "Never run a database client" in text
    assert "conversation memory as a medical fact" in text
    assert "health profile" in text
    assert "Never diagnose a scar" in text


def test_hermes_skill_has_required_weixin_routes_and_no_direct_data_access() -> None:
    skill_root = ROOT / "hermes_skill/personal-health-manager"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    command_map = (skill_root / "references/command-map.md").read_text(encoding="utf-8")
    examples = (skill_root / "references/wechat-examples.md").read_text(encoding="utf-8")

    assert "health imaging list" in command_map
    assert "health radiation summary" in command_map
    assert "health labs trend --item ITEM" in command_map
    assert "health lesions compare ID" in command_map
    assert "health profile summary --json" in examples
    assert "health visit-summary --department 耳鼻喉科 --json" in examples
    assert "Never auto-confirm" in skill
    assert "execute SQL" in skill
    assert "project's `data` directory" in skill
    assert "health-related PDFs" in skill
    assert "generic document Skill" in skill
    assert "record import FILE --dry-run --json" in skill
    assert "file was not imported" in skill
    assert "source_document_id" in skill
    assert "import_id" in skill
    assert "never quote or summarize the old tool" in skill
    assert "does not count as a retry" in skill
    assert "UNSAFE_PATH" in examples
    assert "Do not call only `--help`" in examples
    assert "Never say “原始 PDF 已保留”" in examples

    installer = (ROOT / "hermes_skill/install.sh").read_text(encoding="utf-8")
    verifier = (ROOT / "hermes_skill/verify.sh").read_text(encoding="utf-8")
    assert '$HERMES_ROOT/backups/personal-health-manager-skills' in installer
    assert "Hermes loaded a legacy backup" in verifier
