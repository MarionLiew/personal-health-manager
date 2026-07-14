from __future__ import annotations

from pathlib import Path

from health_agent.errors import ValidationFailure
from health_agent.importers import docx, image, pdf, spreadsheet, text
from health_agent.importers.base import ImportPreview, detected_mime, hash_file
from health_agent.parsers.medical_report import parse_medical_report


def preview_report(path: Path, max_bytes: int) -> ImportPreview:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValidationFailure(f"File exceeds configured size limit: {size} bytes")
    suffix = path.suffix.lower()
    uncertainties: tuple[str, ...] = ()
    if suffix in {".txt", ".md"}:
        extracted, parser = text.extract_text(path), "plain-text"
    elif suffix == ".pdf":
        extracted, parser = pdf.extract_text(path), "pypdf-text"
        if not extracted:
            uncertainties = ("PDF has no extractable text; scanned fields were not guessed.",)
    elif suffix == ".docx":
        extracted, parser = docx.extract_text(path), "python-docx"
    elif suffix == ".csv":
        extracted, parser = spreadsheet.extract_csv(path), "csv"
    elif suffix == ".xlsx":
        extracted, parser = spreadsheet.extract_xlsx(path), "openpyxl"
    elif suffix in {".jpg", ".jpeg", ".png"}:
        extracted, uncertainties = image.describe_without_ocr(path)
        parser = "image-metadata-only"
    else:
        raise ValidationFailure(f"Unsupported report type: {suffix or 'no extension'}")
    sha256 = hash_file(path)
    structured = parse_medical_report(extracted, sha256) if extracted else None
    candidate_data = (
        {
            "report_type": structured.report_type,
            "classification_confidence": structured.classification_confidence,
            "examination_date": structured.examination_date,
            "institution": structured.institution,
            "body_region": structured.body_region,
            "title": structured.title,
            "items": [
                {**candidate, "source_type": "system_inference"}
                for candidate in structured.candidates
            ],
            "unrecognized_text": structured.unrecognized_text,
        }
        if structured
        else {"report_type": "unknown", "classification_confidence": 0.0, "items": []}
    )
    return ImportPreview(
        sha256=sha256,
        filename=path.name,
        mime_type=detected_mime(path),
        size=size,
        parser=parser,
        text=extracted,
        candidates=candidate_data,
        uncertainties=uncertainties
        + tuple(structured.uncertainties if structured else [])
        + ("候选字段在人工局部确认前不会进入正式医疗表。",),
    )
