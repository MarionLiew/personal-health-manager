from __future__ import annotations

from typing import Any

from pydicom.dataset import Dataset
from pydicom.uid import XRayRadiationDoseSRStorage


def is_rdsr(dataset: Dataset) -> bool:
    return str(dataset.get("SOPClassUID", "")) == str(XRayRadiationDoseSRStorage) and bool(
        dataset.get("ContentSequence")
    )


def coded_value(item: Dataset) -> str | None:
    sequence = item.get("ConceptNameCodeSequence")
    if sequence:
        return str(sequence[0].get("CodeMeaning", "")) or None
    return None


def _value(item: Dataset) -> Any:
    value_type = str(item.get("ValueType", ""))
    if value_type == "NUM" and item.get("MeasuredValueSequence"):
        measured = item.MeasuredValueSequence[0]
        units = measured.get("MeasurementUnitsCodeSequence")
        return {
            "value": float(measured.NumericValue),
            "unit": str(units[0].get("CodeValue", "")) if units else None,
            "unit_meaning": str(units[0].get("CodeMeaning", "")) if units else None,
        }
    if value_type == "CODE" and item.get("ConceptCodeSequence"):
        code = item.ConceptCodeSequence[0]
        return str(code.get("CodeMeaning", code.get("CodeValue", "")))
    for attribute in ("TextValue", "UID", "DateTime", "Date", "Time", "PersonName"):
        if item.get(attribute) is not None:
            return str(item.get(attribute))
    return None


def _flatten(items: list[Dataset]) -> list[tuple[str, Any, Dataset]]:
    result: list[tuple[str, Any, Dataset]] = []
    for item in items:
        name = coded_value(item)
        if name:
            result.append((name, _value(item), item))
        if item.get("ContentSequence"):
            result.extend(_flatten(list(item.ContentSequence)))
    return result


def extract_numeric_content(dataset: Dataset) -> list[dict[str, Any]]:
    return [
        {"name": name, **value}
        for name, value, _ in _flatten(list(dataset.get("ContentSequence", [])))
        if isinstance(value, dict) and "value" in value
    ]


def _find(flat: list[tuple[str, Any, Dataset]], *terms: str) -> Any:
    lowered = tuple(term.lower() for term in terms)
    for name, value, _ in flat:
        if name.lower() in lowered:
            return value
    for name, value, _ in flat:
        normalized = name.lower()
        if any(term in normalized for term in lowered):
            return value
    return None


def _number(value: Any) -> float | None:
    return (
        float(value["value"])
        if isinstance(value, dict) and value.get("value") is not None
        else None
    )


def _unit_detail(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("unit_meaning") or value.get("unit")


def _event_containers(dataset: Dataset) -> list[Dataset]:
    events: list[Dataset] = []

    def walk(items: list[Dataset]) -> None:
        for item in items:
            name = (coded_value(item) or "").lower()
            children = list(item.get("ContentSequence", []))
            child_names = {(coded_value(child) or "").lower() for child in children}
            if "irradiation event" in name or any(
                "irradiation event uid" in child for child in child_names
            ):
                events.append(item)
            else:
                walk(children)

    walk(list(dataset.get("ContentSequence", [])))
    return events


def parse_rdsr(dataset: Dataset) -> dict[str, Any]:
    if not is_rdsr(dataset):
        raise ValueError("Dataset is not an X-Ray Radiation Dose SR with content")
    flat = _flatten(list(dataset.ContentSequence))
    total_value = _find(flat, "ct dose length product total", "total dlp")
    events = []
    for container in _event_containers(dataset):
        event_flat = _flatten(list(container.get("ContentSequence", [])))
        acquisition_type = _find(event_flat, "ct acquisition type", "acquisition type")
        ctdi = _find(event_flat, "mean ctdi vol", "ctdivol", "ctdi vol")
        dlp = _find(event_flat, "dlp", "dose length product")
        phantom = _find(event_flat, "ctdiw phantom type", "phantom type")
        scanning_length = _find(event_flat, "scanning length")
        event = {
            "irradiation_event_uid": _find(event_flat, "irradiation event uid"),
            "acquisition_type": acquisition_type,
            "protocol_name": _find(event_flat, "acquisition protocol", "protocol name"),
            "ctdi_vol_mgy": _number(ctdi),
            "dlp_mgy_cm": _number(dlp),
            "phantom_type": phantom or _unit_detail(ctdi),
            "scanning_length_cm": _number(scanning_length),
            "tube_voltage_kvp": _number(_find(event_flat, "kvp", "x-ray tube voltage")),
            "tube_current_ma": _number(_find(event_flat, "x-ray tube current", "tube current")),
            "exposure_time_s": _number(_find(event_flat, "exposure time")),
            "mas": _number(_find(event_flat, "exposure", "mas")),
            "effective_mas": _number(_find(event_flat, "effective exposure", "effective mas")),
            "pitch": _number(_find(event_flat, "pitch factor", "pitch")),
            "collimation": _find(event_flat, "collimation width", "collimation"),
            "source_to_reference_distance_mm": _number(
                _find(event_flat, "source to reference point distance")
            ),
            "scan_start_position": _find(event_flat, "scan start position"),
            "scan_end_position": _find(event_flat, "scan end position"),
            "is_localizer": bool(
                acquisition_type
                and any(
                    word in str(acquisition_type).lower()
                    for word in ("localizer", "constant angle")
                )
            ),
            "is_repeat": bool(_find(event_flat, "repeated acquisition", "repeat")),
            "repeat_reason": _find(event_flat, "reason for repeating acquisition", "repeat reason"),
        }
        events.append(event)
    event_sum = sum(event["dlp_mgy_cm"] or 0.0 for event in events)
    total_dlp = _number(total_value)
    difference = total_dlp - event_sum if total_dlp is not None else None
    ratio = difference / total_dlp if total_dlp not in (None, 0) else None
    template_sequence = dataset.get("ContentTemplateSequence")
    template_identifier = (
        str(template_sequence[0].get("TemplateIdentifier", "")) or None
        if template_sequence
        else str(dataset.get("TemplateIdentifier", "")) or None
    )
    return {
        "study_instance_uid": str(dataset.get("StudyInstanceUID", "")) or None,
        "sop_instance_uid": str(dataset.get("SOPInstanceUID", "")) or None,
        "study_date": str(dataset.get("StudyDate", "")) or None,
        "study_time": str(dataset.get("StudyTime", "")) or None,
        "manufacturer": str(dataset.get("Manufacturer", "")) or None,
        "manufacturer_model": str(dataset.get("ManufacturerModelName", "")) or None,
        "protocol_name": _find(flat, "acquisition protocol", "protocol name"),
        "body_region": _find(flat, "target region", "body part examined")
        or (str(dataset.get("BodyPartExamined", "")) or None),
        "total_dlp_mgy_cm": total_dlp,
        "event_dlp_sum_mgy_cm": event_sum,
        "dlp_difference_mgy_cm": difference,
        "dlp_difference_ratio": ratio,
        "dlp_consistency_warning": bool(ratio is not None and abs(ratio) > 0.1),
        "dlp_difference_possible_reasons": (
            [
                "vendor rounding",
                "events present in Total DLP but absent from event containers",
                "localizer or test exposures handled differently by the scanner",
                "vendor-specific SR encoding",
            ]
            if difference not in (None, 0)
            else []
        ),
        "irradiation_event_count": len(events),
        "dose_data_source": "dicom_rdsr",
        "data_quality": "exact_machine_record",
        "template_identifier": template_identifier,
        "events": events,
    }
