from __future__ import annotations

from pathlib import Path

from health_agent.errors import ValidationFailure
from health_agent.importers import docx, image, pdf, spreadsheet, text
from health_agent.importers.base import ImportPreview, detected_mime, hash_file
from health_agent.importers.local_ocr import ocr_pdf_locally
from health_agent.parsers.medical_report import parse_medical_report


def preview_report(path: Path, max_bytes: int, *, allow_ocr: bool = False) -> ImportPreview:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValidationFailure(f"File exceeds configured size limit: {size} bytes")
    suffix = path.suffix.lower()
    uncertainties: tuple[str, ...] = ()
    ocr_confidence: float | None = None
    if suffix in {".txt", ".md"}:
        extracted, parser = text.extract_text(path), "plain-text"
    elif suffix == ".pdf":
        extracted, parser = pdf.extract_text(path), "pypdf-text"
        if not extracted and allow_ocr:
            ocr_result = ocr_pdf_locally(path)
            extracted = ocr_result.text
            parser = ocr_result.engine
            ocr_confidence = ocr_result.mean_confidence
            uncertainties = (
                "Text was extracted locally with OCR and was not sent externally.",
                "OCR dates, numbers, decimal points, units, laterality and signs require explicit "
                "human review before candidate confirmation.",
            )
        elif not extracted:
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
    items = []
    if structured:
        for candidate in structured.candidates:
            item = {**candidate, "source_type": "system_inference"}
            if ocr_confidence is not None:
                item["confidence"] = min(float(item["confidence"]), 0.65)
                item["payload"] = {
                    **item["payload"],
                    "ocr_derived": True,
                    "ocr_mean_confidence": round(ocr_confidence, 4),
                    "requires_field_confirmation": True,
                }
            items.append(item)
    candidate_data = (
        {
            "report_type": structured.report_type,
            "classification_confidence": structured.classification_confidence,
            "examination_date": structured.examination_date,
            "dates": structured.dates,
            "institution": structured.institution,
            "body_region": structured.body_region,
            "title": structured.title,
            "items": items,
            "unrecognized_text": structured.unrecognized_text,
            "ocr": (
                {
                    "engine": parser,
                    "mean_confidence": round(ocr_confidence, 4),
                    "human_confirmation_required": True,
                }
                if ocr_confidence is not None
                else None
            ),
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
