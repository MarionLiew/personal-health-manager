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
from health_agent.parsers.dicom import read_item, unique_acquisitions


def make_ct(path: Path, description: str, event_uid: str) -> None:
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.Modality = "CT"
    dataset.SeriesDescription = description
    dataset.IrradiationEventUID = event_uid
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
