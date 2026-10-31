"""Import every ORM model so Alembic and tests see the complete metadata."""

from app.db.base import Base
from app.modules.administration import models as administration_models
from app.modules.geography import models as geography_models

__all__ = ["Base", "administration_models", "geography_models"]
