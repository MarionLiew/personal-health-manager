from __future__ import annotations

from pathlib import Path

import pytest

from health_agent.config import load_settings
from health_agent.errors import ConfigurationError
from health_agent.safety.privacy import require_allowed_import_path


def _write_config(path: Path, external_root: str) -> None:
    path.write_text(
        "\n".join(
            [
                "database_path: data/database/health.sqlite3",
                "data_root: data",
                "allowed_import_roots:",
                "  - data/imports",
                "allowed_external_import_roots:",
                f"  - {external_root}",
            ]
        ),
        encoding="utf-8",
    )


def test_exact_external_attachment_root_is_allowed(tmp_path: Path) -> None:
    attachment_root = tmp_path / "documents"
    attachment_root.mkdir()
    report = attachment_root / "fictional-report.pdf"
    report.write_bytes(b"%PDF-1.4 fictional fixture")
    config = tmp_path / "hermes.yaml"
    _write_config(config, str(attachment_root))

    settings = load_settings(config)

    assert settings.external_import_roots == (attachment_root.resolve(),)
    assert require_allowed_import_path(report, settings) == report.resolve()


@pytest.mark.parametrize("external_root", ["/", str(Path.home()), str(Path.home().parent)])
def test_overbroad_external_attachment_root_is_rejected(
    tmp_path: Path, external_root: str
) -> None:
    config = tmp_path / "unsafe.yaml"
    _write_config(config, external_root)

    with pytest.raises(ConfigurationError, match="broader than permitted"):
        load_settings(config)


def test_relative_external_attachment_root_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "relative.yaml"
    _write_config(config, "cache/documents")

    with pytest.raises(ConfigurationError, match="must be absolute"):
        load_settings(config)
