from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, XRayRadiationDoseSRStorage, generate_uid
from sqlalchemy import func, select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import RadiationAcquisition, RadiationExposure
from health_agent.database.session import build_engine, session_scope
from health_agent.parsers.dicom_rdsr import parse_rdsr
from tests.unit.test_dicom import make_ct

runner = CliRunner()


def concept(name: str) -> Sequence:
    code = Dataset()
    code.CodeValue = "fictional"
    code.CodingSchemeDesignator = "99TEST"
    code.CodeMeaning = name
    return Sequence([code])


def num(name: str, value: float, unit: str) -> Dataset:
    item = Dataset()
    item.ValueType = "NUM"
    item.ConceptNameCodeSequence = concept(name)
    measured = Dataset()
    measured.NumericValue = value
    measured.MeasurementUnitsCodeSequence = concept(unit)
    item.MeasuredValueSequence = Sequence([measured])
    return item


def text_item(name: str, value: str, value_type: str = "TEXT") -> Dataset:
    item = Dataset()
    item.ValueType = value_type
    item.ConceptNameCodeSequence = concept(name)
    if value_type == "UIDREF":
        item.UID = value
    else:
        item.TextValue = value
    return item


def code_item(name: str, value: str) -> Dataset:
    item = Dataset()
    item.ValueType = "CODE"
    item.ConceptNameCodeSequence = concept(name)
    item.ConceptCodeSequence = concept(value)
    return item


def event(uid: str, ctdi: float, dlp: float) -> Dataset:
    item = Dataset()
    item.ValueType = "CONTAINER"
    item.ConceptNameCodeSequence = concept("CT Irradiation Event Data")
    item.ContentSequence = Sequence(
        [
            text_item("Irradiation Event UID", uid, "UIDREF"),
            code_item("CT Acquisition Type", "Spiral Acquisition"),
            text_item("Acquisition Protocol", "FICTIONAL CHEST LOW DOSE"),
            num("Mean CTDIvol", ctdi, "mGy"),
            num("DLP", dlp, "mGy.cm"),
            code_item("CTDIw Phantom Type", "IEC Body Dosimetry Phantom"),
            num("Scanning Length", 24, "cm"),
            num("KVP", 120, "kV"),
            num("X-Ray Tube Current", 100, "mA"),
            num("Exposure Time", 0.5, "s"),
            num("Exposure", 50, "mAs"),
            num("Pitch Factor", 1.2, "ratio"),
        ]
    )
    return item


def make_rdsr(path: Path, study_uid: str, event_uids: list[str]) -> None:
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = XRayRadiationDoseSRStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = XRayRadiationDoseSRStorage
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = study_uid
    dataset.Modality = "SR"
    dataset.StudyDate = "20260701"
    dataset.StudyTime = "101500"
    dataset.Manufacturer = "FICTIONAL SCANNER CO"
    dataset.ManufacturerModelName = "TEST-CT"
    dataset.BodyPartExamined = "CHEST"
    dataset.ContentSequence = Sequence(
        [
            num("CT Dose Length Product Total", 205, "mGy.cm"),
            event(event_uids[0], 5, 120),
            event(event_uids[1], 4, 80),
        ]
    )
    dataset.save_as(path)


def test_rdsr_semantics_and_ledger_do_not_double_count_total_or_reconstruction(
    isolated_env: Path,
) -> None:
    root = ROOT / "data/dicom" / f"fictional-rdsr-{uuid.uuid4()}"
    root.mkdir()
    study_uid = generate_uid()
    event_uids = [generate_uid(), generate_uid()]
    try:
        make_rdsr(root / "rdsr.dcm", study_uid, event_uids)
        make_ct(root / "axial.dcm", "AXIAL", event_uids[0])
        make_ct(root / "recon.dcm", "BONE 3D RECONSTRUCTION", event_uids[0])
        parsed = parse_rdsr(__import__("pydicom").dcmread(root / "rdsr.dcm"))
        assert parsed["total_dlp_mgy_cm"] == 205
        assert parsed["event_dlp_sum_mgy_cm"] == 200
        assert parsed["dlp_difference_mgy_cm"] == 5
        assert parsed["irradiation_event_count"] == 2
        assert parsed["events"][0]["ctdi_vol_mgy"] == 5
        assert parsed["events"][0]["phantom_type"] == "IEC Body Dosimetry Phantom"
        assert parsed["events"][0]["tube_voltage_kvp"] == 120
        assert parsed["events"][0]["mas"] == 50
        assert parsed["events"][0]["pitch"] == 1.2

        preview = runner.invoke(app, ["dicom", "import", str(root), "--dry-run", "--json"])
        assert preview.exit_code == 0, preview.output
        preview_data = json.loads(preview.output)["data"]
        assert preview_data["actual_acquisition_count"] == 1
        assert preview_data["reconstruction_series_count"] == 1

        confirmed = runner.invoke(app, ["dicom", "import", str(root), "--confirm", "--json"])
        assert confirmed.exit_code == 0, confirmed.output
        exposure_id = json.loads(confirmed.output)["data"]["exposure_ids"][0]
        duplicate = runner.invoke(app, ["dicom", "import", str(root), "--confirm", "--json"])
        assert duplicate.exit_code == 0, duplicate.output
        assert json.loads(duplicate.output)["data"]["duplicate"] is True
        engine = build_engine(isolated_env)
        with session_scope(engine) as session:
            assert session.scalar(select(func.count()).select_from(RadiationExposure)) == 1
            assert session.scalar(select(func.count()).select_from(RadiationAcquisition)) == 2
            exposure = session.scalar(select(RadiationExposure))
            assert exposure is not None
            assert exposure.dose_data_source == "dicom_rdsr"
            assert exposure.data_quality == "exact_machine_record"
        summary = runner.invoke(app, ["radiation", "summary", "--period", "12m", "--json"])
        assert summary.exit_code == 0, repr(summary.exception)
        summary_data = json.loads(summary.output)["data"]
        assert summary_data["documented_total_dlp_mgy_cm"] == 205
        assert summary_data["rdsr_count"] == 1
        assert "not organ absorbed dose" in summary_data["medical_boundary"]
        acquisitions = runner.invoke(app, ["radiation", "acquisitions", exposure_id, "--json"])
        assert len(json.loads(acquisitions.output)["data"]["acquisitions"]) == 2
    finally:
        for item in root.iterdir():
            item.unlink()
        root.rmdir()
