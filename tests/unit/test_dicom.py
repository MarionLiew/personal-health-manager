from __future__ import annotations

import uuid
import zipfile
from pathlib import Path

import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from health_agent.config import ROOT, load_settings
from health_agent.errors import ValidationFailure
from health_agent.importers.archive import safe_extract_zip
from health_agent.parsers.dicom import metadata_dose_events, read_item, unique_acquisitions


def make_ct(
    path: Path,
    description: str,
    event_uid: str,
    *,
    ctdi_vol: float | None = None,
    study_uid: str | None = None,
) -> None:
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = study_uid or generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.Modality = "CT"
    dataset.SeriesDescription = description
    dataset.IrradiationEventUID = event_uid
    dataset.StudyDate = "20260701"
    dataset.StudyTime = "101500"
    dataset.BodyPartExamined = "CHEST"
    dataset.ProtocolName = "FICTIONAL CHEST"
    dataset.KVP = 120
    dataset.Exposure = 80
    if ctdi_vol is not None:
        dataset.CTDIvol = ctdi_vol
    dataset.PatientName = "FICTIONAL^PATIENT"
    dataset.save_as(path)


def test_reconstructions_and_same_event_are_not_double_counted() -> None:
    root = ROOT / "data/dicom" / f"fictional-{uuid.uuid4()}"
    root.mkdir()
    event = generate_uid()
    try:
        make_ct(root / "thin.dcm", "AXIAL THIN", event)
        make_ct(root / "bone.dcm", "BONE RECONSTRUCTION 3D", event)
        items = [read_item(root / "thin.dcm"), read_item(root / "bone.dcm")]
        parsed = [item for item in items if item is not None]
        assert len(parsed) == 2
        assert len(unique_acquisitions(parsed)) == 1
        assert parsed[1].is_reconstruction is True
        assert parsed[0].identity_tags_present == ("PatientName",)
    finally:
        for item in root.iterdir():
            item.unlink()
        root.rmdir()


def test_ordinary_dicom_metadata_counts_events_not_slices_and_never_infers_dlp() -> None:
    root = ROOT / "data/dicom" / f"fictional-metadata-{uuid.uuid4()}"
    root.mkdir()
    study = generate_uid()
    first_event = generate_uid()
    second_event = generate_uid()
    try:
        make_ct(root / "first.dcm", "AXIAL", first_event, ctdi_vol=4.2, study_uid=study)
        make_ct(root / "second.dcm", "AXIAL", second_event, ctdi_vol=5.1, study_uid=study)
        first = read_item(root / "first.dcm")
        second = read_item(root / "second.dcm")
        assert first is not None and second is not None
        events = metadata_dose_events([first] * 500 + [second])
        assert len(events) == 2
        assert [event["ctdi_vol_mgy"] for event in events] == [
            4.2,
            5.1,
        ]
        assert all(event["dlp_mgy_cm"] is None for event in events)
    finally:
        for item in root.iterdir():
            item.unlink()
        root.rmdir()


def test_zip_path_traversal_is_rejected() -> None:
    archive = ROOT / "data/dicom" / f"bad-{uuid.uuid4()}.zip"
    destination = ROOT / "data/quarantine" / f"zip-{uuid.uuid4()}"
    destination.mkdir()
    try:
        with zipfile.ZipFile(archive, "w") as target:
            target.writestr("../escape.dcm", b"bad")
        with pytest.raises(ValidationFailure):
            safe_extract_zip(archive, destination, load_settings())
    finally:
        archive.unlink(missing_ok=True)
        destination.rmdir()


def test_rdsr_requires_uid_and_content_structure() -> None:
    from pydicom.uid import XRayRadiationDoseSRStorage

    from health_agent.parsers.dicom_rdsr import is_rdsr

    dataset = Dataset()
    dataset.SOPClassUID = XRayRadiationDoseSRStorage
    assert is_rdsr(dataset) is False
    dataset.ContentSequence = Sequence([Dataset()])
    assert is_rdsr(dataset) is True
