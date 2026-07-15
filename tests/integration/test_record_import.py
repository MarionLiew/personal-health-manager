from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import AuditLog, ImagingReport, RecordCandidate, SourceDocument
from health_agent.database.session import build_engine, session_scope

runner = CliRunner()


def fictional_report() -> Path:
    path = ROOT / "data/imports" / f"fictional-{uuid.uuid4()}.txt"
    path.write_text("虚构报告：2026-01-01 胸部CT。仅用于测试。", encoding="utf-8")
    return path


def test_dry_run_does_not_write_formal_record_and_confirm_is_idempotent(isolated_env) -> None:
    path = fictional_report()
    try:
        preview = runner.invoke(app, ["record", "import", str(path), "--dry-run", "--json"])
        assert preview.exit_code == 0, preview.output
        preview_payload = json.loads(preview.output)
        assert preview_payload["requires_confirmation"] is True
        assert not isolated_env.exists()

        first = runner.invoke(app, ["record", "import", str(path), "--confirm", "--json"])
        assert first.exit_code == 0, first.output
        first_payload = json.loads(first.output)
        assert first_payload["data"]["duplicate"] is False

        second = runner.invoke(app, ["record", "import", str(path), "--confirm", "--json"])
        assert second.exit_code == 0, second.output
        second_payload = json.loads(second.output)
        assert second_payload["data"]["duplicate"] is True

        duplicate_preview = runner.invoke(
            app, ["record", "import", str(path), "--dry-run", "--json"]
        )
        assert duplicate_preview.exit_code == 0, duplicate_preview.output
        duplicate_preview_payload = json.loads(duplicate_preview.output)
        assert duplicate_preview_payload["data"]["duplicate"] is True
        assert (
            duplicate_preview_payload["data"]["source_document_id"]
            == first_payload["data"]["source_document_id"]
        )

        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1
            assert session.scalar(select(func.count()).select_from(ImagingReport)) == 0
            assert session.scalar(select(func.count()).select_from(RecordCandidate)) == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.operation == "record.import")
                )
                == 1
            )
    finally:
        path.unlink(missing_ok=True)


def test_undo_import_is_confirmed_and_audited(isolated_env) -> None:
    path = fictional_report()
    try:
        imported = runner.invoke(app, ["record", "import", str(path), "--confirm", "--json"])
        payload = json.loads(imported.output)
        import_id = payload["data"]["import_id"]
        preview = runner.invoke(app, ["record", "undo-import", import_id, "--dry-run", "--json"])
        assert json.loads(preview.output)["requires_confirmation"] is True
        undone = runner.invoke(app, ["record", "undo-import", import_id, "--confirm", "--json"])
        assert undone.exit_code == 0, undone.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            source = session.scalar(select(SourceDocument))
            assert source is not None and source.revoked is True
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.operation.like("record.%"))
                )
                == 2
            )
    finally:
        path.unlink(missing_ok=True)
