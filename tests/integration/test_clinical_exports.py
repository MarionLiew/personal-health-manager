from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.database.migrations import migrate
from health_agent.database.models import Lesion, LesionMeasurement, Patient, SourceDocument
from health_agent.database.session import build_engine
from health_agent.services.clinical_exports import (
    build_lesion_bundle,
    build_visit_bundle,
    write_case_zip,
)


@pytest.fixture
def clinical_case(tmp_path: Path):
    engine = build_engine(tmp_path / "case.sqlite3")
    migrate(engine)
    original = tmp_path / "original.pdf"
    original.write_bytes(b"%PDF-1.4\nfictional test report\n")
    with Session(engine) as session:
        patient = Patient(local_label="Fictional")
        session.add(patient)
        session.flush()
        source = SourceDocument(
            patient_id=patient.id,
            original_filename="../../evil.pdf",
            local_path=str(original),
            file_size=original.stat().st_size,
            sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            institution="Example Hospital",
        )
        session.add(source)
        session.flush()
        lesion = Lesion(
            patient_id=patient.id,
            source_type="source_fact",
            source_document_id=source.id,
            verified=True,
            occurred_at=datetime(2026, 1, 1),
            original_text="source says nodule",
            details={
                "display_code": "L-1",
                "name": "Fictional nodule",
                "department": "respiratory",
                "summary": "AI summary differs",
            },
        )
        session.add(lesion)
        session.flush()
        measurement = LesionMeasurement(
            patient_id=patient.id,
            source_type="source_fact",
            source_document_id=source.id,
            verified=True,
            occurred_at=datetime(2026, 1, 2),
            original_text="nodule measures 4 mm",
            details={
                "lesion_id": lesion.id,
                "size": 4,
                "unit": "mm",
                "source_type": "source_fact",
                "identity_status": "probable",
                "page": 2,
            },
        )
        session.add(measurement)
        session.commit()
        yield engine, lesion.id, source.id, original
    engine.dispose()


def test_single_lesion_evidence_and_quote_separation(clinical_case):
    engine, lesion_id, source_id, _ = clinical_case
    with Session(engine) as session:
        result = build_lesion_bundle(session, lesion_id, include_unconfirmed=True)
    assert result["lesion"]["id"] == lesion_id
    assert result["original_quotes"] == [
        {
            "text": "source says nodule",
            "source_document_id": source_id,
            "source_type": "source_fact",
        }
    ]
    assert result["system_summary"] == "AI summary differs"
    evidence = result["evidence_chain"][0]
    assert evidence["source_document_id"] == source_id
    assert evidence["original_quote"] == "nodule measures 4 mm"
    assert evidence["page"] == 2
    assert evidence["identity_status"] == "probable"
    assert evidence["source_type"] == "source_fact"
    assert evidence["source_file"] == f"originals/{source_id}.pdf"
    assert result["measurements"][0]["size"] == 4


def test_visit_filters_by_department_and_keeps_source_index(clinical_case):
    engine, lesion_id, source_id, _ = clinical_case
    with Session(engine) as session:
        result = build_visit_bundle(session, "respiratory", "review nodule")
        empty = build_visit_bundle(session, "dermatology", "skin")
    assert result["purpose"] == "review nodule"
    assert [item["lesion"]["id"] for item in result["lesions"]] == [lesion_id]
    assert result["source_index"][0]["source_document_id"] == source_id
    assert not empty["lesions"]


def test_case_zip_contains_original_with_safe_name_and_manifest(clinical_case, tmp_path):
    engine, _, source_id, original = clinical_case
    dest = tmp_path / "case.zip"
    with Session(engine) as session:
        write_case_zip(session, dest)
    with zipfile.ZipFile(dest) as bundle:
        names = bundle.namelist()
        assert f"originals/{source_id}.pdf" in names
        assert not any(".." in name or name.startswith("/") for name in names)
        assert bundle.read(f"originals/{source_id}.pdf") == original.read_bytes()
        manifest = json.loads(bundle.read("manifest.json"))
        assert (
            manifest["source_index"][0]["sha256"]
            == hashlib.sha256(original.read_bytes()).hexdigest()
        )


def test_case_zip_rejects_tampered_original(clinical_case, tmp_path):
    engine, _, _, original = clinical_case
    original.write_bytes(b"tampered")
    with Session(engine) as session, pytest.raises(ValueError, match="checksum"):
        write_case_zip(session, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_formal_observation_in_evidence_chain_and_version_two(clinical_case, tmp_path):
    from sqlalchemy.orm import Session as SqSession

    from health_agent.database.models import LesionObservation
    from health_agent.services.clinical_exports import VERSION

    engine, lesion_id, _, _ = clinical_case
    with SqSession(engine) as session:
        lesion = session.get(Lesion, lesion_id)
        source_id = lesion.source_document_id
        session.add(
            LesionObservation(
                lesion_id=lesion_id,
                source_document_id=source_id,
                size=5,
                unit="mm",
                original_text="formal observation 5 mm",
                evidence_type="source_fact",
                status="confirmed",
                examination_date=datetime(2026, 2, 1),
            )
        )
        session.commit()
        bundle = build_lesion_bundle(session, lesion_id, include_unconfirmed=True)
    assert bundle["format_version"] == "2" and VERSION == "2"
    entries = [item for item in bundle["evidence_chain"] if item["report_record_id"]]
    formal = [item for item in entries if item["identity_status"] == "confirmed"][-1]
    assert formal["source_type"] == "source_fact"
    assert formal["date"] == "2026-02-01"
    assert formal["original_quote"] == "formal observation 5 mm"
    measurements = bundle["measurements"]
    assert any(item["size"] == 5 for item in measurements)


def test_evidence_chain_redacts_direct_identifiers(tmp_path: Path):

    from sqlalchemy.orm import Session as SqSession

    from health_agent.database.migrations import migrate
    from health_agent.database.models import LesionObservation
    from health_agent.database.session import build_engine
    from health_agent.services.clinical_exports import build_lesion_bundle

    engine = build_engine(tmp_path / "redact.sqlite3")
    migrate(engine)
    original = tmp_path / "r.pdf"
    original.write_bytes(b"%PDF-1.4\n")
    with SqSession(engine) as session:
        patient = Patient(local_label="Fictional")
        session.add(patient)
        session.flush()
        source = SourceDocument(
            patient_id=patient.id,
            original_filename="report [REDACTED].pdf",
            local_path=str(original),
            file_size=original.stat().st_size,
            sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            institution="Fictional",
        )
        session.add(source)
        session.flush()
        lesion = Lesion(
            patient_id=patient.id,
            source_type="source_fact",
            source_document_id=source.id,
            verified=True,
            details={"display_code": "LR-1", "name": "Fictional"},
        )
        session.add(lesion)
        session.flush()
        session.add(
            LesionObservation(
                lesion_id=lesion.id,
                source_document_id=source.id,
                size=6,
                unit="mm",
                original_text="patient id 11010119900307777X reported 6 mm",
                evidence_type="source_fact",
                status="confirmed",
                examination_date=datetime(2026, 3, 1),
            )
        )
        session.commit()
        bundle = build_lesion_bundle(session, lesion.id, include_unconfirmed=True)
    quotes = [item["original_quote"] for item in bundle["evidence_chain"]]
    assert quotes, "expected at least one evidence-chain entry"
    joined = "\n".join(str(item) for item in quotes)
    assert "11010119900307777X" not in joined
    assert "[REDACTED]" in joined
    engine.dispose()


def test_cli_requires_gate_and_exports_json(clinical_case, tmp_path, monkeypatch):
    engine, lesion_id, _, _ = clinical_case
    monkeypatch.setenv("HEALTH_AGENT_DATABASE", str(engine.url.database))
    monkeypatch.setattr("health_agent.cli.export._clinical_output", lambda value, suffix: value)
    monkeypatch.setattr("health_agent.cli.export.migrate", lambda: None)
    from contextlib import contextmanager

    from sqlalchemy.orm import Session

    @contextmanager
    def test_session():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr("health_agent.cli.export.session_scope", test_session)
    output = tmp_path / "bundle.json"
    runner = CliRunner()
    assert (
        runner.invoke(
            app, ["export", "lesion-bundle", lesion_id, "--output", str(output), "--json"]
        ).exit_code
        != 0
    )
    preview = runner.invoke(
        app, ["export", "lesion-bundle", lesion_id, "--output", str(output), "--dry-run", "--json"]
    )
    assert preview.exit_code == 0, preview.output
    assert not output.exists()
    done = runner.invoke(
        app, ["export", "lesion-bundle", lesion_id, "--output", str(output), "--confirm", "--json"]
    )
    assert done.exit_code == 0, done.output
    assert json.loads(output.read_text())["lesion"]["id"] == lesion_id
