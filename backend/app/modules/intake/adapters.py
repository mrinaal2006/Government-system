"""Source adapter interface and the adapters that exist today.

No live government API integration is implemented: none has been authorised or
documented for this deployment. Each source channel starts as ``not_configured``.
Available adapters:

* ``FileImportAdapter``   - authorised CSV/XLSX exports (all channels).
* ``DevelopmentAdapter``  - DEVELOPMENT ONLY. Produces clearly labelled synthetic
                            records; refuses to run outside development.

A live adapter (e.g. for a state CM Helpline) must implement ``SourceAdapter``,
document its authentication and data-sharing approval in docs/integrations.md, and
set the channel's ``integration_mode`` to ``live_api`` only once approved.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.core.config import Environment, get_settings

REQUIRED_COLUMNS = {"external_id", "description"}
KNOWN_COLUMNS = REQUIRED_COLUMNS | {
    "subject",
    "received_at",
    "category_code",
    "priority",
    "block_lgd_code",
    "block_name",
    "village_lgd_code",
    "village_name",
    "location_text",
    "complainant_name",
    "complainant_mobile",
    "complainant_address",
}
MAX_ROWS = 20_000


@dataclass
class ExternalRecord:
    row_number: int
    external_id: str
    description: str
    subject: str | None = None
    received_at: datetime | None = None
    category_code: str | None = None
    priority: str | None = None
    block_lgd_code: str | None = None
    block_name: str | None = None
    village_lgd_code: str | None = None
    village_name: str | None = None
    location_text: str | None = None
    complainant_name: str | None = None
    complainant_mobile: str | None = None
    complainant_address: str | None = None
    warnings: list[str] = field(default_factory=list)


class AdapterError(ValueError):
    pass


class SourceAdapter(Protocol):
    name: str

    def records(self) -> Iterator[ExternalRecord]: ...


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ):
        try:
            dt = datetime.strptime(v, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # assumption documented: naive = UTC
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError as exc:
        raise AdapterError(f"unrecognised date '{v[:30]}'") from exc


class FileImportAdapter:
    name = "file_import"

    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self.data = data

    def _rows(self) -> Iterator[dict[str, str]]:
        lower = self.filename.lower()
        if lower.endswith(".csv"):
            try:
                text = self.data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise AdapterError("CSV files must be UTF-8 encoded.") from exc
            reader = csv.DictReader(io.StringIO(text))
            yield from ({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader)
        elif lower.endswith(".xlsx"):
            from openpyxl import load_workbook

            if not self.data.startswith(b"PK"):
                raise AdapterError("The file is not a valid XLSX workbook.")
            wb = load_workbook(io.BytesIO(self.data), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            it = ws.iter_rows(values_only=True)
            header = [str(h or "").strip().lower() for h in next(it, [])]
            for values in it:
                yield {
                    header[i]: ("" if v is None else (v.isoformat() if isinstance(v, datetime) else str(v)).strip())
                    for i, v in enumerate(values)
                    if i < len(header)
                }
        else:
            raise AdapterError("Only .csv and .xlsx files are accepted.")

    def records(self) -> Iterator[ExternalRecord]:
        first = True
        for n, row in enumerate(self._rows(), start=2):
            if first:
                missing = REQUIRED_COLUMNS - set(row)
                if missing:
                    raise AdapterError(f"Missing required columns: {', '.join(sorted(missing))}")
                first = False
            if n - 1 > MAX_ROWS:
                raise AdapterError(f"Files may contain at most {MAX_ROWS} rows.")
            if not any(row.values()):
                continue
            rec = ExternalRecord(
                row_number=n,
                external_id=row.get("external_id", "")[:200],
                description=row.get("description", ""),
            )
            for k in KNOWN_COLUMNS - REQUIRED_COLUMNS - {"received_at"}:
                setattr(rec, k, (row.get(k) or None))
            try:
                rec.received_at = _parse_dt(row.get("received_at"))
            except AdapterError as exc:
                rec.warnings.append(str(exc))
            unknown = set(row) - KNOWN_COLUMNS
            if unknown and n == 2:
                rec.warnings.append(f"ignored columns: {', '.join(sorted(unknown))[:200]}")
            yield rec


class DevelopmentAdapter:
    """DEVELOPMENT ONLY: synthetic, clearly labelled records for exercising the pipeline."""

    name = "development_adapter"

    def __init__(self, count: int = 5) -> None:
        if get_settings().app_env != Environment.DEVELOPMENT:
            raise AdapterError("The development adapter is disabled outside the development environment.")
        self.count = min(count, 50)

    def records(self) -> Iterator[ExternalRecord]:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        for i in range(self.count):
            yield ExternalRecord(
                row_number=i + 1,
                external_id=f"DEV-{stamp}-{i:03d}",
                subject=f"[SYNTHETIC DEV RECORD {i + 1}] Test complaint",
                description="SYNTHETIC DEVELOPMENT RECORD - not a real complaint. Generated by the development "
                "adapter to exercise the intake pipeline.",
            )
