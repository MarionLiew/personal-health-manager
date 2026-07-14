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


def extract_numeric_content(dataset: Dataset) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []

    def walk(items: list[Dataset]) -> None:
        for item in items:
            if item.get("ValueType") == "NUM" and item.get("MeasuredValueSequence"):
                measured = item.MeasuredValueSequence[0]
                unit_sequence = measured.get("MeasurementUnitsCodeSequence")
                values.append(
                    {
                        "name": coded_value(item),
                        "value": float(measured.NumericValue),
                        "unit": str(unit_sequence[0].CodeValue) if unit_sequence else None,
                    }
                )
            if item.get("ContentSequence"):
                walk(list(item.ContentSequence))

    walk(list(dataset.get("ContentSequence", [])))
    return values
