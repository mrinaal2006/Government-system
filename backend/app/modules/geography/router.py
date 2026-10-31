"""GIS layers (/gis). Boundaries come only from registered datasets; counts are
limited to the user's grievance scope; village/GP precision needs gis.read_precise."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select

from app.api.auth import DbDep, require
from app.core.config import get_settings
from app.core.errors import PermissionDeniedError
from app.modules.geography.models import (
    Block,
    BoundaryDataset,
    District,
    GramPanchayat,
    Subdivision,
    Village,
)
from app.modules.grievances.models import OPEN_STATUSES, Grievance
from app.modules.iam.scope import grievance_scope
from app.modules.iam.service import CurrentUser
from app.modules.performance.service import overdue_clause

router = APIRouter(prefix="/gis", tags=["gis"])
GisRead = Annotated[CurrentUser, Depends(require("gis.read", "grievance.read"))]

LEVELS: dict[str, tuple[Any, Any, bool]] = {
    "district": (District, Grievance.district_id, False),
    "subdivision": (Subdivision, Grievance.subdivision_id, False),
    "block": (Block, Grievance.block_id, False),
    "gram_panchayat": (GramPanchayat, Grievance.gram_panchayat_id, True),
    "village": (Village, Grievance.village_id, True),
}


@router.get("/config")
def config(cu: GisRead) -> dict[str, Any]:
    return {
        "tile_url": get_settings().map_tile_url,
        "precise_allowed": cu.has("gis.read_precise"),
        "levels": [k for k, (_, _, precise) in LEVELS.items() if not precise or cu.has("gis.read_precise")],
    }


@router.get("/layers/{level}")
def layer(
    level: Literal["district", "subdivision", "block", "gram_panchayat", "village"],
    cu: GisRead,
    db: DbDep,
    category_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    open_only: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    district_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    model, gcol, precise = LEVELS[level]
    if precise and not cu.has("gis.read_precise"):
        raise PermissionDeniedError("Your role may view maps at block level and above only.")
    conds = [grievance_scope(cu), gcol.is_not(None)]
    if category_id:
        conds.append(Grievance.category_id == category_id)
    if department_id:
        conds.append(Grievance.department_id == department_id)
    if open_only:
        conds.append(Grievance.status.in_(OPEN_STATUSES))
    if since:
        conds.append(Grievance.registered_at >= since)
    if until:
        conds.append(Grievance.registered_at < until)
    counts = {
        r[0]: r[1:]
        for r in db.execute(
            select(
                gcol,
                func.count(),
                func.count().filter(Grievance.status.in_(OPEN_STATUSES)),
                func.count().filter(overdue_clause()),
            )
            .where(and_(*conds))
            .group_by(gcol)
        ).all()
    }
    geom = model.boundary
    shape = func.ST_AsGeoJSON(func.ST_Multi(func.ST_SimplifyPreserveTopology(geom, 0.0005)), 6)
    if level == "village":
        shape = func.coalesce(shape, func.ST_AsGeoJSON(Village.location, 6))
        has_geom = (Village.boundary.is_not(None)) | (Village.location.is_not(None))
    else:
        has_geom = geom.is_not(None)
    stmt = (
        select(
            model.id,
            model.name_en,
            model.lgd_code,
            shape,
            BoundaryDataset.name,
            BoundaryDataset.dataset_version,
            BoundaryDataset.publisher,
        )
        .outerjoin(BoundaryDataset, BoundaryDataset.id == model.geometry_dataset_id)
        .where(model.is_active.is_(True), has_geom)
    )
    if district_id and hasattr(model, "district_id"):
        stmt = stmt.where(model.district_id == district_id)
    features = []
    datasets: set[tuple[str, str, str]] = set()
    for uid, name, lgd, gj, ds_name, ds_ver, ds_pub in db.execute(stmt).all():
        total, open_n, overdue = counts.get(uid, (0, 0, 0))
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(gj),
                "properties": {
                    "id": str(uid),
                    "name": name,
                    "lgd_code": lgd,
                    "total": total,
                    "open": open_n,
                    "overdue": overdue,
                },
            }
        )
        if ds_name:
            datasets.add((ds_name, ds_ver, ds_pub))
    without = db.execute(
        select(func.count()).select_from(model).where(model.is_active.is_(True), ~has_geom)
    ).scalar_one()
    unmapped = sum(v[0] for k, v in counts.items()) - sum(f["properties"]["total"] for f in features)
    return {
        "type": "FeatureCollection",
        "features": features,
        "level": level,
        "sources": [{"name": n, "version": v, "publisher": p} for n, v, p in sorted(datasets)],
        "units_without_geometry": without,
        "grievances_in_units_without_geometry": unmapped,
    }
