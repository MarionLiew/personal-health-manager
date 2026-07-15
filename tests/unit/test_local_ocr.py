from pathlib import Path
from subprocess import CompletedProcess

from health_agent.importers import local_ocr


def test_local_vision_ocr_parses_page_results_without_external_service(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "fictional-scan.pdf"
    source.write_bytes(b"fictional")
    monkeypatch.setattr(local_ocr.shutil, "which", lambda _: "/usr/bin/swift")
    monkeypatch.setattr(
        local_ocr.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout='[{"page":1,"text":"虚构超声报告","confidence":0.82}]',
            stderr="",
        ),
    )

    result = local_ocr.ocr_pdf_locally(source)

    assert result.engine == "macos-vision-ocr"
    assert result.page_count == 1
    assert result.mean_confidence == 0.82
    assert result.text == "虚构超声报告"
