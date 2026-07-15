from pathlib import Path

from health_agent.importers import pdf


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
