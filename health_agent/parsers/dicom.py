from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pydicom
from pydicom.errors import InvalidDicomError

from health_agent.parsers.dicom_rdsr import is_rdsr

IDENTITY_TAGS = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "AccessionNumber",
    "InstitutionName",
)
SAFE_TAGS = (
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "SOPClassUID",
    "StudyDate",
    "StudyTime",
    "SeriesDate",
    "Modality",
    "StudyDescription",
    "SeriesDescription",
    "ProtocolName",
    "BodyPartExamined",
    "Manufacturer",
    "ManufacturerModelName",
    "StationName",
    "ImageType",
    "AcquisitionNumber",
    "SeriesNumber",
    "IrradiationEventUID",
    "AcquisitionUID",
)
RECONSTRUCTION_WORDS = {"mpr", "vr", "3d", "recon", "reconstruction", "bone", "soft tissue"}


@dataclass(frozen=True)
class DicomItem:
    path: Path
    metadata: dict[str, Any]
    identity_tags_present: tuple[str, ...]
    is_rdsr: bool
    is_reconstruction: bool


def read_item(path: Path) -> DicomItem | None:
    try:
        dataset = pydicom.dcmread(path, stop_before_pixels=True, force=False)
    except (InvalidDicomError, OSError):
        return None
    metadata = {tag: str(dataset.get(tag, "")) or None for tag in SAFE_TAGS}
    description = " ".join(
        str(metadata.get(key) or "") for key in ("SeriesDescription", "ImageType", "ProtocolName")
    ).lower()
    reconstruction = any(word in description for word in RECONSTRUCTION_WORDS)
    return DicomItem(
        path=path,
        metadata=metadata,
        identity_tags_present=tuple(tag for tag in IDENTITY_TAGS if dataset.get(tag)),
        is_rdsr=is_rdsr(dataset),
        is_reconstruction=reconstruction,
    )


def scan_paths(root: Path) -> list[DicomItem]:
    paths = [root] if root.is_file() else [item for item in root.rglob("*") if item.is_file()]
    return [parsed for path in paths if (parsed := read_item(path)) is not None]


def acquisition_key(item: DicomItem) -> tuple[str, ...] | None:
    metadata = item.metadata
    if item.is_reconstruction:
        return None
    if metadata.get("IrradiationEventUID"):
        return ("irradiation", str(metadata["IrradiationEventUID"]))
    if metadata.get("AcquisitionUID"):
        return ("acquisition", str(metadata["AcquisitionUID"]))
    return (
        "fallback",
        str(metadata.get("StudyInstanceUID")),
        str(metadata.get("AcquisitionNumber")),
        str(metadata.get("ProtocolName")),
    )


def unique_acquisitions(items: list[DicomItem]) -> list[DicomItem]:
    result: list[DicomItem] = []
    seen: set[tuple[str, ...]] = set()
    for item in items:
        key = acquisition_key(item)
        if key is not None and key not in seen:
            seen.add(key)
            result.append(item)
    return result
