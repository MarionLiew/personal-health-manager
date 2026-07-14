from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet
from pydicom.uid import generate_uid
from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.models import LaboratoryResult, RecordCandidate
from health_agent.database.session import build_engine, session_scope
from health_agent.services.backup import create_backup, read_backup
from tests.integration.test_rdsr_ledger import make_rdsr
from tests.integration.test_structured_records import candidates, import_fixture
from tests.unit.test_dicom import make_ct

runner = CliRunner()


def confirm_named(import_id: str, names: set[str]) -> None:
    items = candidates(import_id)
    selected = [
        item["id"]
        for item in items
        if item["payload"].get("item_name") in names or item["type"] in names
    ]
    result = runner.invoke(
        app,
        [
            "record",
            "confirm-candidates",
            import_id,
            "--candidate-ids",
            ",".join(selected),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output


def test_complete_fictional_medical_and_dose_flow(isolated_env: Path) -> None:
    paths: list[Path] = []
    dicom_root = isolated_env.parent.parent.parent / "dicom" / f"e2e-{generate_uid()}"
    dicom_root.mkdir(parents=True)
    try:
        lab1_path, lab1 = import_fixture("fictional_lab_1.txt")
        lab2_path, lab2 = import_fixture("fictional_lab_2.txt")
        ct1_path, ct1 = import_fixture("fictional_ct_1.txt")
        ct2_path, ct2 = import_fixture("fictional_ct_2.txt")
        paths.extend([lab1_path, lab2_path, ct1_path, ct2_path])
        confirm_named(lab1["data"]["import_id"], {"白细胞", "中性粒细胞绝对值", "血清铁"})
        confirm_named(lab2["data"]["import_id"], {"白细胞", "中性粒细胞绝对值", "血清铁"})
        trend = runner.invoke(app, ["labs", "trend", "--item", "白细胞", "--json"])
        trend_data = json.loads(trend.output)["data"]
        assert trend_data["persistence"] == "repeated_abnormality_needs_review"
        assert len(trend_data["groups"][0]["results"]) == 2

        confirm_named(ct1["data"]["import_id"], {"lesion"})
        lesions = json.loads(runner.invoke(app, ["lesions", "list", "--json"]).output)
        lesion_id = lesions["data"]["lesions"][0]["id"]
        second_lesion = next(
            item for item in candidates(ct2["data"]["import_id"]) if item["type"] == "lesion"
        )
        linked = runner.invoke(
            app,
            [
                "record",
                "confirm-candidates",
                ct2["data"]["import_id"],
                "--candidate-ids",
                second_lesion["id"],
                "--lesion-id",
                lesion_id,
                "--json",
            ],
        )
        assert linked.exit_code == 0, linked.output

        study_uid = generate_uid()
        event_uids = [generate_uid(), generate_uid()]
        make_rdsr(dicom_root / "rdsr.dcm", study_uid, event_uids)
        make_ct(dicom_root / "axial.dcm", "AXIAL", event_uids[0])
        make_ct(dicom_root / "recon.dcm", "3D RECONSTRUCTION", event_uids[0])
        dose_import = runner.invoke(
            app, ["dicom", "import", str(dicom_root), "--confirm", "--json"]
        )
        assert dose_import.exit_code == 0, dose_import.output
        ledger = runner.invoke(app, ["radiation", "summary", "--period", "12m", "--json"])
        assert json.loads(ledger.output)["data"]["documented_total_dlp_mgy_cm"] == 205

        visit = runner.invoke(app, ["visit-summary", "--department", "呼吸科", "--json"])
        visit_data = json.loads(visit.output)["data"]
        assert len(visit_data["confirmed_laboratory_results"]) == 6
        assert len(visit_data["lesions"][0]["measurements"]) == 2
        assert len(visit_data["radiation_examinations"]) == 1

        undo = runner.invoke(
            app,
            [
                "record",
                "undo-import",
                lab2["data"]["import_id"],
                "--confirm",
                "--json",
            ],
        )
        assert undo.exit_code == 0, undo.output
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(LaboratoryResult)
                    .where(LaboratoryResult.verified.is_(True))
                )
                == 3
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RecordCandidate)
                    .where(RecordCandidate.import_session_id == lab2["data"]["import_id"])
                    .where(RecordCandidate.status == "revoked")
                )
                > 0
            )
        key = Fernet.generate_key().decode()
        backup = create_backup(isolated_env, isolated_env.parent, key)
        manifest, _ = read_backup(backup, key)
        assert manifest["schema_version"] == 4
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        if dicom_root.exists():
            for item in dicom_root.iterdir():
                item.unlink()
            dicom_root.rmdir()
