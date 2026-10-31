"""Import every ORM model so Alembic and tests see the complete metadata."""

from app.db.base import Base
from app.modules.administration import config_models as administration_config_models
from app.modules.administration import models as administration_models
from app.modules.audit import models as audit_models
from app.modules.citizen_portal import models as citizen_portal_models
from app.modules.early_warning import models as early_warning_models
from app.modules.geography import models as geography_models
from app.modules.grievances import models as grievance_models
from app.modules.iam import models as iam_models
from app.modules.intelligence import models as intelligence_models
from app.modules.notifications import models as notification_models
from app.modules.performance import models as performance_models
from app.modules.reports import models as report_models

__all__ = [
    "Base",
    "administration_config_models",
    "administration_models",
    "audit_models",
    "citizen_portal_models",
    "early_warning_models",
    "geography_models",
    "grievance_models",
    "iam_models",
    "intelligence_models",
    "notification_models",
    "performance_models",
    "report_models",
]
