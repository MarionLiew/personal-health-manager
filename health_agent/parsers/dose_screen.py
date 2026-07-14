from __future__ import annotations

import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def parse_dose_screen_text(text: str, document_hash: str = "") -> list[dict[str, Any]]:
    """Extract reviewable candidates from locally produced OCR text.

    Values remain candidates. This parser never decides that OCR is a machine record.
    """
    candidates: list[dict[str, Any]] = []
    patterns = (
        ("total_dlp", r"\bTotal\s*DLP\b\s*[:=]?\s*(\d+(?:\.\d+)?)", "mGy.cm"),
        ("ctdi_vol", r"\bCTDI\s*vol\b\s*[:=]?\s*(\d+(?:\.\d+)?)", "mGy"),
        ("event_dlp", r"(?<!Total\s)\bDLP\b\s*[:=]?\s*(\d+(?:\.\d+)?)", "mGy.cm"),
        ("kvp", r"\bkVp\b\s*[:=]?\s*(\d+(?:\.\d+)?)", "kV"),
        ("mas", r"\bmAs\b\s*[:=]?\s*(\d+(?:\.\d+)?)", "mAs"),
        ("series_number", r"\bSeries(?:\s*(?:No\.?|Number))?\s*[:=]?\s*(\d+)", None),
        ("phantom", r"\bPhantom\b\s*[:=]?\s*(16|32)\s*(?:cm)?", "cm"),
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        for field, pattern, unit in patterns:
            for match in re.finditer(pattern, line, re.IGNORECASE):
                raw = match.group(1)
                value: float | int | str
                value = int(raw) if field in {"series_number", "phantom"} else float(raw)
                region = {
                    "line": line_number,
                    "start": match.start(1),
                    "end": match.end(1),
                }
                candidate_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"dose-screen:{document_hash}:{field}:{line_number}:{match.start()}:{raw}",
                    )
                )
                candidates.append(
                    {
                        "id": candidate_id,
                        "field": field,
                        "value": value,
                        "unit": unit,
                        "confidence": 0.92,
                        "original_text": line.strip(),
                        "region": region,
                    }
                )
        protocol = re.search(r"\bProtocol\b\s*[:=]\s*(.+)$", line, re.IGNORECASE)
        if protocol:
            value = protocol.group(1).strip()
            candidates.append(
                {
                    "id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"dose-screen:{document_hash}:protocol:{line_number}:{value}",
                        )
                    ),
                    "field": "protocol",
                    "value": value,
                    "unit": None,
                    "confidence": 0.9,
                    "original_text": line.strip(),
                    "region": {"line": line_number, "start": protocol.start(1), "end": len(line)},
                }
            )
    return candidates


def dose_screen_warnings(candidates: list[dict[str, Any]]) -> list[str]:
    event_sum = sum(float(item["value"]) for item in candidates if item["field"] == "event_dlp")
    totals = [float(item["value"]) for item in candidates if item["field"] == "total_dlp"]
    if event_sum and totals and abs(event_sum - totals[0]) / max(totals[0], 1.0) > 0.15:
        return ["Event DLP sum differs from Total DLP by more than 15%; review OCR fields."]
    return []
