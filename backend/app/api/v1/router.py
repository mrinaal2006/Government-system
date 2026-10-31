"""Version 1 API router. Each module contributes its router here under /api/v1."""

from fastapi import APIRouter

from app.modules.administration.router import admin as admin_router
from app.modules.administration.router import reference as reference_router
from app.modules.audit.router import router as audit_router
from app.modules.citizen_portal.router import router as citizen_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.early_warning.router import router as alerts_router
from app.modules.geography.router import router as gis_router
from app.modules.grievances.router import router as grievances_router
from app.modules.iam.router import admin as iam_admin_router
from app.modules.iam.router import router as auth_router
from app.modules.intake.router import router as intake_router
from app.modules.intelligence.router import router as intelligence_router
from app.modules.notifications.router import router as notifications_router
from app.modules.performance.router import router as performance_router
from app.modules.reports.router import router as reports_router
from app.modules.system.router import router as system_router

api_router = APIRouter()
for r in (
    system_router,
    auth_router,
    iam_admin_router,
    audit_router,
    notifications_router,
    reference_router,
    admin_router,
    grievances_router,
    intake_router,
    intelligence_router,
    alerts_router,
    gis_router,
    performance_router,
    dashboard_router,
    reports_router,
    citizen_router,
):
    api_router.include_router(r)
