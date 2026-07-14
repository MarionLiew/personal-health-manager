from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportPreview:
    sha256: str
    filename: str
    mime_type: str
    size: int
    parser: str
    text: str | None
    candidates: dict[str, object] = field(default_factory=dict)
    uncertainties: tuple[str, ...] = ()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detected_mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
