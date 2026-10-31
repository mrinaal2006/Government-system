"""Administrative geography reference tables (schema ``ref``).

Hierarchy, as modelled (see docs/database.md, "Administrative hierarchy"):

    district ─┬─ subdivision
              ├─ block ── gram_panchayat
              ├─ village  (optional links to subdivision / block / gram_panchayat)
              └─ municipality ── ward

Development blocks and revenue subdivisions (tehsils) do not nest cleanly in every
state, so ``block.subdivision_id`` and the village links are optional and must be
populated only from verified source data (e.g. LGD). No relationship is inferred.

Geometry is stored in WGS 84 (EPSG:4326). A geometry may only be stored together
with a reference to the registered ``boundary_datasets`` row it came from; this is
enforced by a CHECK constraint so unverified coordinates cannot enter silently.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.db.base import (
    SCHEMA_REFERENCE,
    ActiveFlagMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

SRID_WGS84 = 4326
LGD_CODE_PATTERN = r"^[0-9]{1,16}$"
MUNICIPALITY_BODY_TYPES = (
    "municipal_corporation",
    "municipal_council",
    "nagar_panchayat",
    "cantonment_board",
    "other",
)


def _fk(target: str, *, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(f"{SCHEMA_REFERENCE}.{target}", ondelete=ondelete)


class BoundaryDataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance record for an imported, verified boundary/location dataset."""

    __tablename__ = "boundary_datasets"
    __table_args__ = (
        UniqueConstraint("name", "dataset_version"),
        CheckConstraint("checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'", name="checksum_format"),
        {"schema": SCHEMA_REFERENCE, "comment": "Provenance of verified geographic datasets"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str] = mapped_column(
        Text, nullable=False, comment="URL, order number or document reference of the source"
    )
    licence: Mapped[str | None] = mapped_column(String(200))
    acquired_on: Mapped[date] = mapped_column(Date, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # verified_by becomes a FK to iam.users in Phase 2.
    verification_notes: Mapped[str | None] = mapped_column(Text)


class AdministrativeUnitMixin(UUIDPrimaryKeyMixin, TimestampMixin, ActiveFlagMixin):
    """Columns shared by every administrative unit table."""

    lgd_code: Mapped[str | None] = mapped_column(String(16), comment="Local Government Directory code, when assigned")
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(200), comment="Name in the official local language/script")
    boundary: Mapped[Any | None] = mapped_column(Geometry("MULTIPOLYGON", srid=SRID_WGS84, spatial_index=False))

    @declared_attr
    def geometry_dataset_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), _fk("boundary_datasets.id"))

    @classmethod
    def unit_table_args(cls, table: str, *extra: Any) -> tuple[Any, ...]:
        return (
            CheckConstraint(f"lgd_code IS NULL OR lgd_code ~ '{LGD_CODE_PATTERN}'", name="lgd_code_format"),
            CheckConstraint("length(btrim(name_en)) > 0", name="name_en_not_blank"),
            CheckConstraint(
                "boundary IS NULL OR geometry_dataset_id IS NOT NULL",
                name="boundary_requires_dataset",
            ),
            CheckConstraint("boundary IS NULL OR ST_IsValid(boundary)", name="boundary_is_valid"),
            Index(
                f"uq_{table}_lgd_code",
                "lgd_code",
                unique=True,
                postgresql_where=text("lgd_code IS NOT NULL"),
            ),
            Index(f"ix_{table}_boundary", "boundary", postgresql_using="gist"),
            Index(
                f"ix_{table}_name_en_trgm",
                "name_en",
                postgresql_using="gin",
                postgresql_ops={"name_en": "gin_trgm_ops"},
            ),
            *extra,
            {"schema": SCHEMA_REFERENCE},
        )


class District(AdministrativeUnitMixin, Base):
    __tablename__ = "districts"
    __table_args__ = AdministrativeUnitMixin.unit_table_args("districts", UniqueConstraint("state_name_en", "name_en"))

    state_name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    state_lgd_code: Mapped[str | None] = mapped_column(String(16))


class Subdivision(AdministrativeUnitMixin, Base):
    __tablename__ = "subdivisions"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "subdivisions",
        UniqueConstraint("district_id", "name_en"),
        Index("ix_subdivisions_district_id", "district_id"),
    )

    district_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("districts.id"), nullable=False)


class Block(AdministrativeUnitMixin, Base):
    __tablename__ = "blocks"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "blocks",
        UniqueConstraint("district_id", "name_en"),
        Index("ix_blocks_district_id", "district_id"),
        Index("ix_blocks_subdivision_id", "subdivision_id"),
    )

    district_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("districts.id"), nullable=False)
    subdivision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("subdivisions.id"))


class Municipality(AdministrativeUnitMixin, Base):
    __tablename__ = "municipalities"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "municipalities",
        UniqueConstraint("district_id", "name_en"),
        CheckConstraint(
            "body_type IN (" + ", ".join(f"'{t}'" for t in MUNICIPALITY_BODY_TYPES) + ")",
            name="body_type_allowed",
        ),
        Index("ix_municipalities_district_id", "district_id"),
    )

    district_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("districts.id"), nullable=False)
    subdivision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("subdivisions.id"))
    body_type: Mapped[str] = mapped_column(String(40), nullable=False)


class GramPanchayat(AdministrativeUnitMixin, Base):
    __tablename__ = "gram_panchayats"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "gram_panchayats",
        UniqueConstraint("block_id", "name_en"),
        Index("ix_gram_panchayats_block_id", "block_id"),
    )

    block_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("blocks.id"), nullable=False)


class Village(AdministrativeUnitMixin, Base):
    __tablename__ = "villages"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "villages",
        CheckConstraint(
            "location IS NULL OR geometry_dataset_id IS NOT NULL",
            name="location_requires_dataset",
        ),
        Index("ix_villages_location", "location", postgresql_using="gist"),
        Index("ix_villages_district_id", "district_id"),
        Index("ix_villages_block_id", "block_id"),
        Index("ix_villages_gram_panchayat_id", "gram_panchayat_id"),
        Index("ix_villages_subdivision_id", "subdivision_id"),
        Index(
            "uq_villages_census_code",
            "census_code",
            unique=True,
            postgresql_where=text("census_code IS NOT NULL"),
        ),
    )

    district_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("districts.id"), nullable=False)
    subdivision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("subdivisions.id"))
    block_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("blocks.id"))
    gram_panchayat_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _fk("gram_panchayats.id"))
    census_code: Mapped[str | None] = mapped_column(String(16))
    location: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=SRID_WGS84, spatial_index=False),
        comment="Representative point from a registered dataset; never estimated",
    )


class Ward(AdministrativeUnitMixin, Base):
    __tablename__ = "wards"
    __table_args__ = AdministrativeUnitMixin.unit_table_args(
        "wards",
        UniqueConstraint("municipality_id", "ward_number"),
        Index("ix_wards_municipality_id", "municipality_id"),
    )

    municipality_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _fk("municipalities.id"), nullable=False)
    ward_number: Mapped[str] = mapped_column(String(20), nullable=False)
