from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.migrations import migrate
from health_agent.database.models import (
    AuditLog,
    ImportSession,
    RecordCandidate,
    SourceDocument,
    SymptomEpisode,
)
from health_agent.database.session import session_scope

runner = CliRunner()


def test_gpt_bundle_is_gated_redacted_audited_and_never_uploaded(isolated_env) -> None:
    migrate()
    source_id = str(uuid.uuid4())
    import_id = str(uuid.uuid4())
    with session_scope() as session:
        source = SourceDocument(
            id=source_id,
            patient_id="local-primary",
            original_filename="fictional-person-name.pdf",
            local_path="/fictional/private/report.pdf",
            mime_type="application/pdf",
            file_size=100,
            sha256="e" * 64,
            institution="虚构市第一医院",
            human_confirmed=True,
            parser_name="fictional-parser",
            parser_version="7",
        )
        session.add(source)
        session.add(
            ImportSession(
                id=import_id,
                patient_id="local-primary",
                source_sha256="e" * 64,
                source_document_id=source_id,
                kind="general_report",
                status="confirmed",
            )
        )
        session.add(
            SymptomEpisode(
                patient_id="local-primary",
                source_type="user_report",
                source_document_id=source_id,
                symptom_name="虚构不适",
                normalized_symptom_name="虚构不适",
                started_at=datetime(2026, 7, 1, tzinfo=UTC),
                status="stable",
                user_notes="姓名：虚构甲 电话：13800138000 邮箱 test@example.com",
                verified=True,
                verification_status="user_confirmed",
            )
        )
        session.add(
            RecordCandidate(
                id=str(uuid.uuid4()),
                import_session_id=import_id,
                patient_id="local-primary",
                candidate_type="imaging_report",
                source_type="system_inference",
                payload={"finding": "虚构待确认内容"},
                original_text="虚构待确认原文",
                confidence=0.5,
            )
        )

    destination = ROOT / "data/exports" / f"fictional-gpt-{uuid.uuid4()}.json"
    pending_destination = ROOT / "data/exports" / f"fictional-gpt-pending-{uuid.uuid4()}.json"
    no_institution_destination = (
        ROOT / "data/exports" / f"fictional-gpt-no-institution-{uuid.uuid4()}.json"
    )
    try:
        preview = runner.invoke(
            app,
            [
                "export",
                "gpt-bundle",
                "--output",
                str(destination),
                "--dry-run",
                "--json",
            ],
        )
        assert preview.exit_code == 0, preview.output
        preview_payload = json.loads(preview.output)
        assert preview_payload["requires_confirmation"] is True
        assert preview_payload["data"]["external_upload_performed"] is False
        assert preview_payload["data"]["pending_candidate_count"] == 1
        assert preview_payload["data"]["pending_candidates_included"] is False
        assert not destination.exists()

        created = runner.invoke(
            app,
            [
                "export",
                "gpt-bundle",
                "--output",
                str(destination),
                "--confirm",
                "--json",
            ],
        )
        assert created.exit_code == 0, created.output
        assert destination.stat().st_mode & 0o777 == 0o600
        bundle = json.loads(destination.read_text(encoding="utf-8"))
        encoded = json.dumps(bundle, ensure_ascii=False)
        assert bundle["privacy"]["external_upload_performed"] is False
        assert bundle["source_index"][0]["institution"] == "虚构市第一医院"
        assert bundle["pending_candidate_summary"]["count"] == 1
        assert bundle["pending_candidate_summary"]["included"] is False
        assert bundle["unconfirmed_data"]["parser_candidates"] == []
        assert "虚构待确认内容" not in encoded
        assert "fictional-person-name.pdf" not in encoded
        assert "/fictional/private" not in encoded
        assert "13800138000" not in encoded
        assert "test@example.com" not in encoded
        assert "虚构甲" not in encoded
        assert "original_text" not in encoded
        assert "study_instance_uid" not in encoded

        with session_scope() as session:
            event = session.scalar(
                select(AuditLog).where(AuditLog.operation == "export.gpt-bundle")
            )
            assert event is not None
            assert event.file_hash_prefix

        included = runner.invoke(
            app,
            [
                "export",
                "gpt-bundle",
                "--output",
                str(pending_destination),
                "--include-pending",
                "--confirm",
                "--json",
            ],
        )
        assert included.exit_code == 0, included.output
        pending_bundle = json.loads(pending_destination.read_text(encoding="utf-8"))
        pending_rows = pending_bundle["unconfirmed_data"]["parser_candidates"]
        assert len(pending_rows) == 1
        assert pending_rows[0]["source_type"] == "system_inference"
        assert pending_rows[0]["status"] == "pending"
        assert pending_rows[0]["payload"]["finding"] == "虚构待确认内容"
        assert "虚构待确认原文" not in pending_destination.read_text(encoding="utf-8")

        excluded = runner.invoke(
            app,
            [
                "export",
                "gpt-bundle",
                "--output",
                str(no_institution_destination),
                "--include-pending",
                "--exclude-institutions",
                "--confirm",
                "--json",
            ],
        )
        assert excluded.exit_code == 0, excluded.output
        excluded_text = no_institution_destination.read_text(encoding="utf-8")
        assert "虚构市第一医院" not in excluded_text
        assert '"institution"' not in excluded_text
    finally:
        destination.unlink(missing_ok=True)
        pending_destination.unlink(missing_ok=True)
        no_institution_destination.unlink(missing_ok=True)


def test_gpt_bundle_rejects_output_outside_managed_exports(isolated_env) -> None:
    result = runner.invoke(
        app,
        [
            "export",
            "gpt-bundle",
            "--output",
            str(isolated_env.parent / "outside.json"),
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["code"] == "VALIDATION_ERROR"
