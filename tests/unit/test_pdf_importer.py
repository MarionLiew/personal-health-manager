from pathlib import Path

from health_agent.importers import pdf
from health_agent.importers import report as report_importer
from health_agent.importers.local_ocr import OcrResult


def test_pdf_extraction_requests_layout_mode(monkeypatch, tmp_path: Path) -> None:
    calls: list[str | None] = []

    class Page:
        def extract_text(self, extraction_mode: str | None = None) -> str:
            calls.append(extraction_mode)
            return "1 白细胞计数WBC 4.20 x10^9/L 4.00 - 10.00"

    class Reader:
        def __init__(self, _: Path) -> None:
            self.pages = [Page()]

    monkeypatch.setattr(pdf, "PdfReader", Reader)

    assert "白细胞" in pdf.extract_text(tmp_path / "fictional.pdf")
    assert calls == ["layout"]


def test_scanned_pdf_ocr_candidates_are_capped_and_require_field_confirmation(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "fictional-scanned-ultrasound.pdf"
    source.write_bytes(b"fictional scanned PDF")
    monkeypatch.setattr(report_importer.pdf, "extract_text", lambda _: "")
    monkeypatch.setattr(
        report_importer,
        "ocr_pdf_locally",
        lambda _: OcrResult(
            text=(
                "虚构医院超声报告\n检查日期：2026-06-13\n"
                "检查所见：颏下见数个淋巴结，较大约12x4mm。\n"
                "检查提示：结构未见明显异常。"
            ),
            mean_confidence=0.79,
            page_count=1,
            engine="macos-vision-ocr",
        ),
    )

    preview = report_importer.preview_report(source, 1024, allow_ocr=True)

    assert preview.parser == "macos-vision-ocr"
    assert preview.candidates["ocr"] == {
        "engine": "macos-vision-ocr",
        "mean_confidence": 0.79,
        "human_confirmation_required": True,
    }
    candidate = preview.candidates["items"][0]
    assert candidate["confidence"] == 0.65
    assert candidate["payload"]["ocr_derived"] is True
    assert candidate["payload"]["requires_field_confirmation"] is True
    assert "human review" in preview.uncertainties[1]
