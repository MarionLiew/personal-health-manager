from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import AuditLog, Procedure, RecordCandidate, SourceDocument
from health_agent.database.session import build_engine, session_scope

runner = CliRunner()


def _import_fixture(name: str) -> tuple[Path, dict]:
    path = ROOT / "data/imports" / f"{uuid.uuid4()}-{name}"
    shutil.copy2(ROOT / "tests/fixtures" / name, path)
    result = runner.invoke(app, ["record", "import", str(path), "--confirm", "--json"])
    assert result.exit_code == 0, result.output
    return path, json.loads(result.output)["data"]


def test_reparse_supersedes_only_stale_pending_candidates_and_is_audited(
    isolated_env: Path,
) -> None:
    path, imported = _import_fixture("fictional_neck_range_us.txt")
    legacy_id = str(uuid.uuid4())
    try:
        listed = runner.invoke(
            app, ["record", "candidates", imported["import_id"], "--json"]
        )
        current_id = json.loads(listed.output)["data"]["candidates"][0]["id"]
        confirmed_current = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                imported["import_id"],
                "--candidate-ids",
                current_id,
                "--json",
            ],
        )
        assert confirmed_current.exit_code == 0, confirmed_current.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            session.add(
                RecordCandidate(
                    id=legacy_id,
                    import_session_id=imported["import_id"],
                    patient_id="local-primary",
                    candidate_type="lesion",
                    source_type="system_inference",
                    payload={
                        "lesion_kind": "淋巴结",
                        "size": 0.5,
                        "unit": "cm",
                        "anatomical_location": "甲状腺",
                    },
                    original_text="虚构旧版错误候选",
                    original_offset=0,
                    confidence=0.9,
                )
            )

        preview = runner.invoke(
            app,
            ["record", "reparse", imported["source_document_id"], "--dry-run", "--json"],
        )
        assert preview.exit_code == 0, preview.output
        preview_payload = json.loads(preview.output)
        assert preview_payload["requires_confirmation"] is True
        assert preview_payload["data"]["report_type"] == "ultrasound"
        assert preview_payload["data"]["institution"] == "虚构市第一医院"
        assert preview_payload["data"]["pending_candidate_ids_to_supersede"] == [legacy_id]
        assert preview_payload["data"]["protected_candidate_ids"] == [current_id]
        assert {item["candidate_type"] for item in preview_payload["data"]["candidates"]} == {
            "imaging_report"
        }
        with session_scope(engine) as session:
            assert session.get(RecordCandidate, legacy_id).status == "pending"

        confirmed = runner.invoke(
            app,
            ["record", "reparse", imported["source_document_id"], "--confirm", "--json"],
        )
        assert confirmed.exit_code == 0, confirmed.output
        data = json.loads(confirmed.output)["data"]
        assert data["superseded_candidate_ids"] == [legacy_id]
        with session_scope(engine) as session:
            assert session.get(RecordCandidate, legacy_id).status == "superseded"
            assert session.get(RecordCandidate, current_id).status == "confirmed"
            assert (
                session.get(SourceDocument, imported["source_document_id"]).institution
                == "虚构市第一医院"
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.operation == "record.reparse")
                )
                == 1
            )
    finally:
        path.unlink(missing_ok=True)


def test_procedure_candidate_can_be_partially_confirmed(isolated_env: Path) -> None:
    path, imported = _import_fixture("fictional_interventional_us.txt")
    try:
        listed = runner.invoke(
            app, ["record", "candidates", imported["import_id"], "--json"]
        )
        candidates = json.loads(listed.output)["data"]["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["type"] == "procedure"

        confirmed = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                imported["import_id"],
                "--candidate-ids",
                candidates[0]["id"],
                "--json",
            ],
        )
        assert confirmed.exit_code == 0, confirmed.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            procedure = session.scalar(select(Procedure))
            assert procedure is not None
            assert procedure.details["procedure_type"] == "core_needle_biopsy"
            assert procedure.details["specimen_count"] == 4
    finally:
        path.unlink(missing_ok=True)
