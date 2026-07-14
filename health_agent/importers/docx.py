from pathlib import Path

from docx import Document


def extract_text(path: Path) -> str:
    return "\n".join(paragraph.text for paragraph in Document(path).paragraphs).strip()
