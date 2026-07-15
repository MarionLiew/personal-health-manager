from pathlib import Path

from pypdf import PdfReader


def extract_text(path: Path) -> str:
    pages = []
    for page in PdfReader(path).pages:
        try:
            extracted = page.extract_text(extraction_mode="layout")
        except (TypeError, ValueError):
            extracted = page.extract_text()
        pages.append(extracted or "")
    return "\n".join(pages).strip()
