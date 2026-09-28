from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import select, text
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.migrations import MIGRATIONS, current_version, upgrade
from health_agent.database.models import AuditLog, Lesion, LesionSourceLink, SourceDocument
from health_agent.database.session import build_engine, session_scope

runner = CliRunner()


def invoke(*args: str) -> dict:
    result = runner.invoke(app, ["lesions", *args, "--json"])
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def test_migration_requires_backup_and_preserves_legacy(isolated_env: Path) -> None:
    engine = build_engine(isolated_env)
    upgrade(engine, migrations=MIGRATIONS[:6])
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs(id, operation, actor, status, "
                "metadata_json, occurred_at) VALUES ('legacy', 'test', 'pytest', "
                "'success', '{}', CURRENT_TIMESTAMP)"
            )
        )
    backup = isolated_env.parent / "before.sqlite3"
    assert upgrade(engine, backup_path=backup) == [7]
    assert backup.exists() and current_version(engine) == 7
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT id FROM audit_logs WHERE id='legacy'")).scalar()
            == "legacy"
        )


def test_create_update_and_audit(isolated_env: Path) -> None:
    preview = invoke(
        "create",
        "--display-code",
        "LN-L",
        "--name",
        "Fictional left node",
        "--laterality",
        "left",
        "--dry-run",
    )
    assert preview["requires_confirmation"]
    with session_scope() as session:
        assert session.scalars(select(Lesion)).all() == []
    created = invoke(
        "create",
        "--display-code",
        "LN-L",
        "--name",
        "Fictional left node",
        "--laterality",
        "left",
        "--confirm",
    )["data"]
    lesion_id = created["id"]
    assert str(uuid.UUID(lesion_id)) == lesion_id
    assert created["source_type"] == "user_report"
    updated = invoke("update", lesion_id, "--name", "Updated fictional node", "--confirm")["data"]
    assert updated["display_code"] == "LN-L" and updated["id"] == lesion_id
    assert invoke("list")["data"]["lesions"][0]["id"] == lesion_id
    history = invoke("history", lesion_id)["data"]
    assert [event["operation"] for event in history["audit"]] == [
        "lesions.create",
        "lesions.update",
    ]
    with session_scope() as session:
        assert session.scalars(select(AuditLog).where(AuditLog.entity_id == lesion_id)).all()
    rejected = runner.invoke(
        app, ["lesions", "update", lesion_id, "--display-code", "DIFFERENT", "--confirm", "--json"]
    )
    assert rejected.exit_code != 0
    duplicate = runner.invoke(
        app,
        ["lesions", "create", "--display-code", "LN-L", "--name", "Other", "--confirm", "--json"],
    )
    assert duplicate.exit_code != 0


def test_link_measurement_and_bilateral_safety(isolated_env: Path) -> None:
    lesion_id = invoke(
        "create",
        "--display-code",
        "LN-R",
        "--name",
        "Fictional right node",
        "--laterality",
        "right",
        "--confirm",
    )["data"]["id"]
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="fictional-source",
                patient_id="local-primary",
                original_filename="fictional.pdf",
                local_path="/fictional/report.pdf",
                file_size=10,
                sha256="a" * 64,
            )
        )
    link = invoke(
        "link-source",
        lesion_id,
        "fictional-source",
        "--evidence-type",
        "user_report",
        "--status",
        "user_confirmed",
        "--original-text",
        "Right node mentioned",
        "--confirm",
    )["data"]
    assert link["evidence_type"] == "user_report" and link["status"] == "user_confirmed"
    invalid = runner.invoke(
        app,
        [
            "lesions",
            "add-measurement",
            lesion_id,
            "--source",
            "fictional-source",
            "--size",
            "12",
            "--unit",
            "mm",
            "--original-text",
            "Bilateral nodes regular, medulla unclear",
            "--scope",
            "bilateral_group",
            "--confirm",
            "--json",
        ],
    )
    assert invalid.exit_code != 0
    measurement = invoke(
        "add-measurement",
        lesion_id,
        "--source",
        "fictional-source",
        "--size",
        "12",
        "--unit",
        "mm",
        "--laterality",
        "right",
        "--original-text",
        "Right node 12 mm",
        "--confirm",
    )["data"]
    assert measurement["source_document_id"] == "fictional-source"
    assert invoke("history", lesion_id)["data"]["measurements"][0]["id"] == measurement["id"]
    assert invoke("unlink", lesion_id, link["id"], "--dry-run")["requires_confirmation"]
    assert len(invoke("history", lesion_id)["data"]["sources"]) == 1
    invoke("unlink", lesion_id, link["id"], "--confirm")
    assert invoke("history", lesion_id)["data"]["sources"] == []
    with session_scope() as session:
        assert session.get(LesionSourceLink, link["id"]).unlinked_at is not None
