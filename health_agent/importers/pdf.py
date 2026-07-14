from pathlib import Path

from pypdf import PdfReader


def extract_text(path: Path) -> str:
    pages = [page.extract_text() or "" for page in PdfReader(path).pages]
    return "\n".join(pages).strip()
