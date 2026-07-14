from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

from health_agent.config import Settings
from health_agent.errors import ValidationFailure


def safe_extract_zip(archive: Path, destination: Path, settings: Settings) -> list[Path]:
    extracted: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > settings.zip_max_files:
            raise ValidationFailure("ZIP contains too many files")
        for member in members:
            name = PurePosixPath(member.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValidationFailure("ZIP path traversal detected")
            mode = member.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValidationFailure("ZIP symbolic links are not allowed")
            total += member.file_size
            if total > settings.zip_max_uncompressed_bytes:
                raise ValidationFailure("ZIP uncompressed size exceeds limit")
            if member.compress_size == 0 and member.file_size > 0:
                raise ValidationFailure("ZIP suspicious compression ratio")
            if (
                member.compress_size
                and member.file_size / member.compress_size > settings.zip_max_compression_ratio
            ):
                raise ValidationFailure("ZIP compression ratio exceeds limit")
            target = (destination / Path(*name.parts)).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValidationFailure("ZIP extraction escaped destination")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with source.open(member) as reader, target.open("wb") as writer:
                while block := reader.read(1024 * 1024):
                    writer.write(block)
            extracted.append(target)
    return extracted
