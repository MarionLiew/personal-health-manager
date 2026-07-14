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
    "AcquisitionType",
    "CTDIvol",
    "Exposure",
    "ExposureInuAs",
    "KVP",
    "SpiralPitchFactor",
    "SingleCollimationWidth",
    "TotalCollimationWidth",
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
    if item.is_reconstruction or item.is_rdsr:
        return None
    if metadata.get("IrradiationEventUID"):
        return ("irradiation", str(metadata["IrradiationEventUID"]))
    if metadata.get("AcquisitionUID"):
        return ("acquisition", str(metadata["AcquisitionUID"]))
    if metadata.get("AcquisitionNumber"):
        return (
            "number",
            str(metadata.get("StudyInstanceUID")),
            str(metadata.get("AcquisitionNumber")),
        )
    return (
        "series",
        str(metadata.get("StudyInstanceUID")),
        str(metadata.get("SeriesInstanceUID")),
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


def _number(value: object) -> float | None:
    try:
        return float(str(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def metadata_dose_events(items: list[DicomItem]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in unique_acquisitions(items):
        metadata = item.metadata
        exposure_uas = _number(metadata.get("ExposureInuAs"))
        series_number = _number(metadata.get("SeriesNumber"))
        result.append(
            {
                "study_instance_uid": metadata.get("StudyInstanceUID"),
                "series_instance_uid": metadata.get("SeriesInstanceUID"),
                "irradiation_event_uid": metadata.get("IrradiationEventUID"),
                "acquisition_uid": metadata.get("AcquisitionUID"),
                "series_number": int(series_number) if series_number is not None else None,
                "acquisition_type": metadata.get("AcquisitionType") or "unknown",
                "protocol_name": metadata.get("ProtocolName") or metadata.get("SeriesDescription"),
                "body_region": metadata.get("BodyPartExamined"),
                "study_date": metadata.get("StudyDate"),
                "study_time": metadata.get("StudyTime"),
                "modality": metadata.get("Modality"),
                "ctdi_vol_mgy": _number(metadata.get("CTDIvol")),
                # DLP is intentionally never inferred from slice count or scan parameters.
                "dlp_mgy_cm": None,
                "tube_voltage_kvp": _number(metadata.get("KVP")),
                "tube_current_mas": _number(metadata.get("Exposure"))
                or (exposure_uas / 1000 if exposure_uas is not None else None),
                "pitch": _number(metadata.get("SpiralPitchFactor")),
            }
        )
    return result
