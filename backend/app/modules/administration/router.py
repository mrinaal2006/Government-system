"""Reference lookups (/reference, any signed-in user) and configuration (/admin, config.manage)."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.auth import CurrentUserDep, DbDep, require
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.request_meta import RequestMeta
from app.modules.administration.models import (
    CODE_PATTERN,
    Department,
    GrievanceSource,
    IssueCategory,
)
from app.modules.audit import service as audit
from app.modules.geography.models import (
    Block,
    BoundaryDataset,
    District,
    GramPanchayat,
    Municipality,
    Subdivision,
    Village,
    Ward,
)
from app.modules.iam.service import CurrentUser
from app.modules.intelligence.models import ClassificationRule, RiskModel
from app.modules.performance.models import SlaPolicy

reference = APIRouter(prefix="/reference", tags=["reference"])
admin = APIRouter(prefix="/admin", tags=["administration"])
Manager = Annotated[CurrentUser, Depends(require("config.manage"))]

UNIT_MODELS: dict[str, tuple[Any, str | None]] = {
    "districts": (District, None),
    "subdivisions": (Subdivision, "district_id"),
    "blocks": (Block, "district_id"),
    "gram_panchayats": (GramPanchayat, "block_id"),
    "villages": (Village, "gram_panchayat_id"),
    "municipalities": (Municipality, "district_id"),
    "wards": (Ward, "municipality_id"),
}
UnitLevel = Literal["districts", "subdivisions", "blocks", "gram_panchayats", "villages", "municipalities", "wards"]


def _meta(r: Request) -> RequestMeta:
    return RequestMeta.from_request(r)


def _row(obj: Any, *fields: str) -> dict[str, Any]:
    out = {}
    for f in ("id", *fields):
        v = getattr(obj, f, None)
        out[f] = str(v) if isinstance(v, uuid.UUID) else (float(v) if isinstance(v, Decimal) else v)
    return out


# --- Lookups ---------------------------------------------------------------------------------


@reference.get("/sources")
def sources(cu: CurrentUserDep, db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(
            s,
            "code",
            "name_en",
            "name_local",
            "channel_type",
            "integration_mode",
            "is_active",
            "description",
        )
        for s in db.execute(select(GrievanceSource).order_by(GrievanceSource.name_en)).scalars()
    ]


@reference.get("/departments")
def departments(cu: CurrentUserDep, db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(d, "code", "name_en", "name_local", "parent_id", "is_active", "description")
        for d in db.execute(select(Department).order_by(Department.name_en)).scalars()
    ]


@reference.get("/categories")
def categories(cu: CurrentUserDep, db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(
            c,
            "code",
            "name_en",
            "name_local",
            "parent_id",
            "default_department_id",
            "is_essential_service",
            "is_active",
            "description",
        )
        for c in db.execute(select(IssueCategory).order_by(IssueCategory.name_en)).scalars()
    ]


@reference.get("/units/{level}")
def units(
    level: UnitLevel,
    cu: CurrentUserDep,
    db: DbDep,
    parent_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    model, parent = UNIT_MODELS[level]
    stmt = select(model)
    if parent_id and parent:
        stmt = stmt.where(getattr(model, parent) == parent_id)
    if q:
        stmt = stmt.where(model.name_en.ilike(f"%{q[:100]}%"))
    fields = [
        f
        for f in (
            "lgd_code",
            "name_en",
            "name_local",
            "is_active",
            "district_id",
            "subdivision_id",
            "block_id",
            "gram_panchayat_id",
            "municipality_id",
            "ward_number",
            "body_type",
            "state_name_en",
            "census_code",
        )
        if hasattr(model, f)
    ]
    order = model.ward_number if level == "wards" else model.name_en
    rows = db.execute(stmt.order_by(order).limit(min(limit, 5000))).scalars()
    out = []
    for r in rows:
        d = _row(r, *fields)
        d["has_geometry"] = r.boundary is not None or getattr(r, "location", None) is not None
        if level == "wards":
            d["name_en"] = f"Ward {r.ward_number}"
        out.append(d)
    return out


# --- Organisation master data -------------------------------------------------------------------


class DepartmentIn(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name_en: str = Field(min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class CategoryIn(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name_en: str = Field(min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: uuid.UUID | None = None
    default_department_id: uuid.UUID | None = None
    is_essential_service: bool = False
    is_active: bool = True


class SourceUpdate(BaseModel):
    name_en: str | None = Field(default=None, min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    integration_mode: Literal["not_configured", "development_adapter", "file_import", "live_api"] | None = None
    is_active: bool | None = None


def _save(db: DbDep, obj: Any) -> None:
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "The value conflicts with an existing record (for example a duplicate code or name)."
        ) from exc


def _upsert(
    db: DbDep,
    request: Request,
    cu: CurrentUser,
    model: Any,
    kind: str,
    body: BaseModel,
    obj_id: uuid.UUID | None,
) -> Any:
    data = body.model_dump(exclude_unset=obj_id is not None)
    if obj_id:
        obj = db.get(model, obj_id)
        if obj is None:
            raise NotFoundError()
        for k, v in data.items():
            setattr(obj, k, v)
    else:
        obj = model(**data)
        db.add(obj)
    if getattr(obj, "parent_id", None) and obj.parent_id == getattr(obj, "id", None):
        raise AppError("A record cannot be its own parent.")
    _save(db, obj)
    audit.record(
        db,
        action=f"config.{kind}_{'updated' if obj_id else 'created'}",
        actor=cu.actor,
        resource_type=kind,
        resource_id=obj.id,
        details={"fields": sorted(data)},
        meta=_meta(request),
    )
    return obj


@admin.post("/departments", status_code=201)
def create_department(body: DepartmentIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, Department, "department", body, None), "code", "name_en")


@admin.patch("/departments/{obj_id}")
def update_department(
    obj_id: uuid.UUID, body: DepartmentIn, request: Request, cu: Manager, db: DbDep
) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, Department, "department", body, obj_id), "code", "name_en")


@admin.post("/categories", status_code=201)
def create_category(body: CategoryIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, IssueCategory, "category", body, None), "code", "name_en")


@admin.patch("/categories/{obj_id}")
def update_category(obj_id: uuid.UUID, body: CategoryIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, IssueCategory, "category", body, obj_id), "code", "name_en")


@admin.patch("/sources/{obj_id}")
def update_source(obj_id: uuid.UUID, body: SourceUpdate, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(
        _upsert(db, request, cu, GrievanceSource, "source", body, obj_id),
        "code",
        "name_en",
        "integration_mode",
    )


# --- Geography --------------------------------------------------------------------------------


class UnitIn(BaseModel):
    name_en: str = Field(min_length=2, max_length=200)
    name_local: str | None = Field(default=None, max_length=200)
    lgd_code: str | None = Field(default=None, pattern=r"^[0-9]{1,16}$")
    is_active: bool = True
    district_id: uuid.UUID | None = None
    subdivision_id: uuid.UUID | None = None
    block_id: uuid.UUID | None = None
    gram_panchayat_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    state_name_en: str | None = Field(default=None, max_length=200)
    body_type: str | None = None
    ward_number: str | None = Field(default=None, max_length=20)
    census_code: str | None = Field(default=None, max_length=16)


@admin.post("/units/{level}", status_code=201)
def create_unit(level: UnitLevel, body: UnitIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    model, _ = UNIT_MODELS[level]
    data = {k: v for k, v in body.model_dump().items() if hasattr(model, k) and v is not None}
    if level == "wards":
        data["name_en"] = body.name_en
    obj = model(**data)
    db.add(obj)
    _save(db, obj)
    audit.record(
        db,
        action="config.unit_created",
        actor=cu.actor,
        resource_type=level,
        resource_id=obj.id,
        details={"name": body.name_en},
        meta=_meta(request),
    )
    return {"id": str(obj.id)}


@admin.patch("/units/{level}/{unit_id}")
def update_unit(
    level: UnitLevel, unit_id: uuid.UUID, body: UnitIn, request: Request, cu: Manager, db: DbDep
) -> dict[str, Any]:
    model, _ = UNIT_MODELS[level]
    obj = db.get(model, unit_id)
    if obj is None:
        raise NotFoundError()
    for k, v in body.model_dump(exclude_unset=True).items():
        if hasattr(model, k):
            setattr(obj, k, v)
    _save(db, obj)
    audit.record(
        db,
        action="config.unit_updated",
        actor=cu.actor,
        resource_type=level,
        resource_id=obj.id,
        meta=_meta(request),
    )
    return {"id": str(obj.id)}


class DatasetIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    publisher: str = Field(min_length=2, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=50)
    source_reference: str = Field(min_length=5, max_length=2000)
    licence: str | None = Field(default=None, max_length=200)
    acquired_on: date
    verification_notes: str | None = Field(default=None, max_length=2000)


@admin.get("/boundary-datasets")
def list_datasets(cu: Manager, db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(
            d,
            "name",
            "publisher",
            "dataset_version",
            "source_reference",
            "licence",
            "acquired_on",
            "checksum_sha256",
            "verified_at",
        )
        for d in db.execute(select(BoundaryDataset).order_by(BoundaryDataset.created_at.desc())).scalars()
    ]


@admin.post("/boundary-datasets", status_code=201)
def create_dataset(body: DatasetIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    ds = BoundaryDataset(**body.model_dump())
    db.add(ds)
    _save(db, ds)
    audit.record(
        db,
        action="config.boundary_dataset_registered",
        actor=cu.actor,
        resource_type="boundary_dataset",
        resource_id=ds.id,
        details=body.model_dump(mode="json"),
        meta=_meta(request),
    )
    return {"id": str(ds.id)}


@admin.post("/boundaries/import")
async def import_boundaries(
    request: Request,
    cu: Manager,
    db: DbDep,
    level: Annotated[UnitLevel, Form()],
    dataset_id: Annotated[uuid.UUID, Form()],
    match_property: Annotated[str, Form(max_length=50)],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Attach geometries from a GeoJSON FeatureCollection (EPSG:4326) to existing units,
    matched by LGD code taken from ``match_property``. Invalid geometries are rejected,
    never "repaired"; unmatched features are reported, never created."""
    import hashlib

    model, _ = UNIT_MODELS[level]
    ds = db.get(BoundaryDataset, dataset_id)
    if ds is None:
        raise AppError("Register the boundary dataset first.", code="unknown_dataset")
    raw = await file.read(50 * 1024 * 1024 + 1)
    if len(raw) > 50 * 1024 * 1024:
        raise AppError("GeoJSON files may be at most 50 MB.", code="file_too_large")
    try:
        fc = json.loads(raw)
        features = fc["features"] if fc.get("type") == "FeatureCollection" else None
        if features is None:
            raise ValueError
    except (ValueError, KeyError, AttributeError) as exc:
        raise AppError("The file is not a GeoJSON FeatureCollection.", code="invalid_geojson") from exc
    matched, unmatched, invalid = 0, [], []
    for i, f in enumerate(features):
        code = str((f.get("properties") or {}).get(match_property, "")).strip()
        unit = db.execute(select(model).where(model.lgd_code == code)).scalar_one_or_none() if code else None
        if unit is None:
            unmatched.append(code or f"feature #{i}")
            continue
        gj = json.dumps(f.get("geometry"))
        geom_type = (
            "POINT" if (level == "villages" and (f.get("geometry") or {}).get("type") == "Point") else "MULTIPOLYGON"
        )
        ok = db.execute(text("SELECT ST_IsValid(ST_GeomFromGeoJSON(:g))"), {"g": gj}).scalar()
        if not ok:
            invalid.append(code)
            continue
        col = "location" if geom_type == "POINT" else "boundary"
        expr = (
            "ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)"
            if geom_type == "POINT"
            else "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326))"
        )
        db.execute(
            text(
                f"UPDATE {model.__table__.schema}.{model.__tablename__} SET {col} = {expr}, "  # noqa: S608
                "geometry_dataset_id = :ds WHERE id = :id"
            ),
            {"g": gj, "ds": dataset_id, "id": unit.id},
        )
        matched += 1
    if ds.checksum_sha256 is None:
        ds.checksum_sha256 = hashlib.sha256(raw).hexdigest()
    audit.record(
        db,
        action="config.boundaries_imported",
        actor=cu.actor,
        resource_type="boundary_dataset",
        resource_id=ds.id,
        details={
            "level": level,
            "matched": matched,
            "unmatched": len(unmatched),
            "invalid": len(invalid),
        },
        meta=_meta(request),
    )
    return {"matched": matched, "unmatched": unmatched[:200], "invalid": invalid[:200]}


# --- SLA policies -------------------------------------------------------------------------------


class SlaIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    category_id: uuid.UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    resolution_hours: int = Field(gt=0, le=8760)
    warning_percent: int = Field(default=75, gt=0, lt=100)
    legal_reference: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


@admin.get("/sla-policies")
def list_sla(cu: Annotated[CurrentUser, Depends(require("performance.read"))], db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(
            p,
            "name",
            "category_id",
            "priority",
            "resolution_hours",
            "warning_percent",
            "legal_reference",
            "is_active",
        )
        for p in db.execute(select(SlaPolicy).order_by(SlaPolicy.name)).scalars()
    ]


@admin.post("/sla-policies", status_code=201)
def create_sla(body: SlaIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    p = SlaPolicy(**body.model_dump(), created_by=cu.id)
    db.add(p)
    _save(db, p)
    audit.record(
        db,
        action="config.sla_policy_created",
        actor=cu.actor,
        resource_type="sla_policy",
        resource_id=p.id,
        details=body.model_dump(mode="json"),
        meta=_meta(request),
    )
    return {"id": str(p.id)}


@admin.patch("/sla-policies/{obj_id}")
def update_sla(obj_id: uuid.UUID, body: SlaIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, SlaPolicy, "sla_policy", body, obj_id), "name")


# --- Classification rules ---------------------------------------------------------------------


class RuleIn(BaseModel):
    category_id: uuid.UUID
    keyword: str = Field(min_length=2, max_length=100)
    weight: Decimal = Field(default=Decimal("1"), gt=0, le=10)
    is_active: bool = True


@admin.get("/classification-rules")
def list_rules(cu: Annotated[CurrentUser, Depends(require("ai.read"))], db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(r, "category_id", "keyword", "weight", "is_active")
        for r in db.execute(select(ClassificationRule).order_by(ClassificationRule.keyword)).scalars()
    ]


@admin.post("/classification-rules", status_code=201)
def create_rule(body: RuleIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    r = ClassificationRule(**body.model_dump(), created_by=cu.id)
    db.add(r)
    _save(db, r)
    audit.record(
        db,
        action="config.classification_rule_created",
        actor=cu.actor,
        resource_type="classification_rule",
        resource_id=r.id,
        details={"keyword": body.keyword},
        meta=_meta(request),
    )
    return {"id": str(r.id)}


@admin.patch("/classification-rules/{obj_id}")
def update_rule(obj_id: uuid.UUID, body: RuleIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    return _row(_upsert(db, request, cu, ClassificationRule, "classification_rule", body, obj_id), "keyword")


# --- Risk models (versioned) ---------------------------------------------------------------------


class RiskModelIn(BaseModel):
    parameters: dict[str, Any]
    notes: str = Field(min_length=10, max_length=2000)
    approved: bool = Field(default=False, description="True when approved by the competent authority")


REQUIRED_RISK_KEYS = {
    "risk_factors",
    "levels",
    "alerts",
    "cluster",
    "duplicate",
    "recommended_actions",
}


@admin.get("/risk-models")
def risk_models(cu: Annotated[CurrentUser, Depends(require("ai.read"))], db: DbDep) -> list[dict[str, Any]]:
    return [
        _row(m, "version", "parameters", "is_active", "is_provisional", "notes", "created_at")
        for m in db.execute(select(RiskModel).order_by(RiskModel.version.desc())).scalars()
    ]


@admin.post("/risk-models", status_code=201)
def new_risk_model(body: RiskModelIn, request: Request, cu: Manager, db: DbDep) -> dict[str, Any]:
    missing = REQUIRED_RISK_KEYS - set(body.parameters)
    if missing:
        raise AppError(f"Missing parameter sections: {', '.join(sorted(missing))}", code="invalid_risk_model")
    lv = body.parameters["levels"]
    if not (0 < lv.get("watch", 0) < lv.get("high", 0) < lv.get("critical", 0)):
        raise AppError("Levels must satisfy 0 < watch < high < critical.", code="invalid_risk_model")
    version = (db.execute(select(func.max(RiskModel.version))).scalar() or 0) + 1
    db.execute(update(RiskModel).where(RiskModel.is_active.is_(True)).values(is_active=False))
    m = RiskModel(
        version=version,
        parameters=body.parameters,
        is_active=True,
        is_provisional=not body.approved,
        notes=body.notes,
        created_by=cu.id,
    )
    db.add(m)
    db.flush()
    audit.record(
        db,
        action="config.risk_model_activated",
        actor=cu.actor,
        resource_type="risk_model",
        resource_id=m.id,
        details={"version": version, "approved": body.approved},
        meta=_meta(request),
    )
    return {"id": str(m.id), "version": version}
