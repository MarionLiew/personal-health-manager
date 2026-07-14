from pathlib import Path


def describe_without_ocr(path: Path) -> tuple[None, tuple[str, ...]]:
    return None, (
        "Image OCR is not treated as silent truth; dates, values, units, laterality and signs "
        "require a separate human-confirmed transcription.",
    )
