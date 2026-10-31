"""Object-storage export/import for backup and disaster recovery.

    python -m app.cli export-objects > objects.tar
    python -m app.cli import-objects < objects.tar

The tar stream contains every object in the private bucket under its key. Import
validates member names (no absolute paths, no "..", only known prefixes).
"""

from __future__ import annotations

import io
import sys
import tarfile

from app.core.config import get_settings
from app.infra import storage

ALLOWED_PREFIXES = ("grievances/", "imports/", "reports/")


def export_objects() -> int:
    bucket = get_settings().storage_bucket
    count = 0
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        for obj in storage.client().list_objects(bucket, recursive=True):
            data = storage.get_bytes(obj.object_name)
            info = tarfile.TarInfo(obj.object_name)
            info.size = len(data)
            info.mtime = int(obj.last_modified.timestamp()) if obj.last_modified else 0
            tar.addfile(info, io.BytesIO(data))
            count += 1
    print(f"exported {count} objects", file=sys.stderr)
    return 0


def import_objects() -> int:
    count = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as tar:
        for member in tar:
            name = member.name
            if (
                not member.isfile()
                or name.startswith("/")
                or ".." in name.split("/")
                or not name.startswith(ALLOWED_PREFIXES)
            ):
                print(f"skipped unsafe or unexpected member: {name[:100]}", file=sys.stderr)
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            storage.put_bytes(name, f.read(), "application/octet-stream")
            count += 1
    print(f"imported {count} objects", file=sys.stderr)
    return 0
