"""Version 1 API router. Each module contributes its router here under /api/v1."""

from fastapi import APIRouter

from app.modules.system.router import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
