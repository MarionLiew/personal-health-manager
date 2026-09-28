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


def test_link_source_requires_verbatim_text_for_report_evidence(isolated_env: Path) -> None:
    lesion_id = invoke(
        "create",
        "--display-code",
        "LN-V",
        "--name",
        "Fictional verified node",
        "--confirm",
    )["data"]["id"]
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="fictional-source-v",
                patient_id="local-primary",
                original_filename="fictional-v.pdf",
                local_path="/fictional/report-v.pdf",
                file_size=10,
                sha256="b" * 64,
            )
        )
    result = runner.invoke(
        app,
        [
            "lesions",
            "link-source",
            lesion_id,
            "fictional-source-v",
            "--evidence-type",
            "source_fact",
            "--status",
            "confirmed",
            "--confirm",
            "--json",
        ],
    )
    assert result.exit_code != 0
    assert "verbatim original text" in result.stdout
    negative = runner.invoke(
        app,
        [
            "lesions",
            "link-source",
            lesion_id,
            "fictional-source-v",
            "--evidence-type",
            "source_fact",
            "--status",
            "confirmed",
            "--page",
            "0",
            "--confirm",
            "--json",
        ],
    )
    assert negative.exit_code != 0 and "Invalid page" in negative.stdout


def test_link_source_rejects_identical_active_link(isolated_env: Path) -> None:
    lesion_id = invoke(
        "create",
        "--display-code",
        "LN-D",
        "--name",
        "Fictional duplicate node",
        "--confirm",
    )["data"]["id"]
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="fictional-source-d",
                patient_id="local-primary",
                original_filename="fictional-d.pdf",
                local_path="/fictional/report-d.pdf",
                file_size=10,
                sha256="c" * 64,
            )
        )
    first = invoke(
        "link-source",
        lesion_id,
        "fictional-source-d",
        "--evidence-type",
        "user_report",
        "--status",
        "user_confirmed",
        "--original-text",
        "Same verbatim text",
        "--confirm",
    )["data"]
    link_id = first["id"]
    duplicate = runner.invoke(
        app,
        [
            "lesions",
            "link-source",
            lesion_id,
            "fictional-source-d",
            "--evidence-type",
            "user_report",
            "--status",
            "user_confirmed",
            "--original-text",
            "Same verbatim text",
            "--confirm",
            "--json",
        ],
    )
    assert duplicate.exit_code != 0 and "already exists" in duplicate.stdout
    re_linked = invoke(
        "link-source",
        lesion_id,
        "fictional-source-d",
        "--evidence-type",
        "user_report",
        "--status",
        "user_confirmed",
        "--original-text",
        "Different verbatim text",
        "--confirm",
    )["data"]
    assert re_linked["id"] != link_id
    invoke("unlink", lesion_id, link_id, "--confirm")
    restored = invoke(
        "link-source",
        lesion_id,
        "fictional-source-d",
        "--evidence-type",
        "user_report",
        "--status",
        "user_confirmed",
        "--original-text",
        "Same verbatim text",
        "--confirm",
    )["data"]
    assert restored["id"] != link_id


def test_unified_measurement_rows_dedup_formal_and_legacy(isolated_env: Path) -> None:
    from datetime import datetime

    from health_agent.database.models import LesionMeasurement, LesionObservation
    from health_agent.services.lesion_tracker import measurement_rows

    lesion_id = invoke(
        "create",
        "--display-code",
        "LN-U",
        "--name",
        "Fictional unified node",
        "--laterality",
        "left",
        "--confirm",
    )["data"]["id"]
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="fictional-source-u",
                patient_id="local-primary",
                original_filename="fictional-u.pdf",
                local_path="/fictional/report-u.pdf",
                file_size=10,
                sha256="d" * 64,
            )
        )
        session.flush()
        legacy = LesionMeasurement(
            patient_id="local-primary",
            source_type="source_fact",
            source_document_id="fictional-source-u",
            verified=True,
            occurred_at=datetime(2026, 5, 1),
            original_text="legacy 10 mm",
            details={"lesion_id": lesion_id, "size": 10, "unit": "mm"},
        )
        session.add(legacy)
        session.flush()
        formal = LesionObservation(
            lesion_id=lesion_id,
            source_document_id="fictional-source-u",
            size=10,
            unit="mm",
            original_text="legacy 10 mm",
            evidence_type="source_fact",
            status="confirmed",
            examination_date=datetime(2026, 5, 1),
        )
        session.add(formal)
        formal_other = LesionObservation(
            lesion_id=lesion_id,
            source_document_id="fictional-source-u",
            size=11,
            unit="mm",
            original_text="formal 11 mm",
            evidence_type="source_fact",
            status="unresolved",
            examination_date=datetime(2026, 6, 1),
        )
        session.add(formal_other)
    with session_scope() as session:
        rows = measurement_rows(session, lesion_id)
    # legacy 10 mm (2026-05-01, fictional-source-u) and the formal observation with the
    # identical (lesion_id, date, size, source) key deduplicate into a single row.
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-05-01" and rows[0]["size"] == 10
    assert rows[1]["date"] == "2026-06-01" and rows[1]["size"] == 11
    assert all(row["source_document_id"] == "fictional-source-u" for row in rows)
