from __future__ import annotations

from pathlib import Path

from health_agent.errors import ValidationFailure
from health_agent.importers import docx, image, pdf, spreadsheet, text
from health_agent.importers.base import ImportPreview, detected_mime, hash_file


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
    return ImportPreview(
        sha256=hash_file(path),
        filename=path.name,
        mime_type=detected_mime(path),
        size=size,
        parser=parser,
        text=extracted,
        candidates={"document_kind": "unclassified_medical_report"},
        uncertainties=uncertainties + ("No medical facts are inferred before human review.",),
    )
