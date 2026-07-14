from __future__ import annotations

from pathlib import Path

from health_agent.config import Settings
from health_agent.errors import UnsafePath


def require_allowed_import_path(path: Path, settings: Settings) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not any(resolved.is_relative_to(root) for root in settings.allowed_import_roots):
        raise UnsafePath(
            "Import path is outside configured roots; copy the file into data/imports, "
            "data/dicom, or data/apple_health first"
        )
    if not resolved.is_file() and not resolved.is_dir():
        raise UnsafePath("Import target is neither a regular file nor directory")
    return resolved


def safe_log_metadata(*, operation: str, record_id: str | None = None) -> dict[str, str]:
    result = {"operation": operation}
    if record_id:
        result["record_id"] = record_id
    return result
