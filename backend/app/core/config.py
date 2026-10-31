"""Environment-based configuration.

All configuration comes from environment variables (or Docker secret files mounted
under ``SECRETS_DIR``). Nothing secret has a usable default: development defaults
exist only for non-sensitive values, and production startup refuses placeholder or
weak secrets.
"""

from __future__ import annotations

import os
import re
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
PLACEHOLDER_MARKERS = ("change_me", "changeme", "replace_me", "example", "password")
MIN_PRODUCTION_SECRET_LENGTH = 16


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


def _secrets_dir() -> str | None:
    path = os.environ.get("SECRETS_DIR", "/run/secrets")
    return path if os.path.isdir(path) else None


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # .env is loaded by Docker Compose / the shell, never implicitly
        case_sensitive=False,
        extra="ignore",
        secrets_dir=_secrets_dir(),
    )

    # --- Application -------------------------------------------------------------
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "DG-IMEWS"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    expose_api_docs: bool | None = None  # None -> enabled only outside production
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "api", "testserver"]
    )
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Header carrying the real client address when a trusted edge sets it (for example
    # "x-real-ip" on Vercel). Unset: use the socket peer (nginx/uvicorn proxy headers).
    client_ip_header: str | None = None

    # --- Deployment identity (shown in the official header; never invented) -------
    deployment_district_name: str | None = None
    deployment_district_name_local: str | None = None
    deployment_state_name: str | None = None
    deployment_state_name_local: str | None = None

    # --- PostgreSQL ----------------------------------------------------------------
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "dgimews"
    database_user: str = "dgimews_app"
    database_password: SecretStr = SecretStr("")
    database_migration_user: str | None = None
    database_migration_password: SecretStr | None = None
    database_app_role: str = "dgimews_app"  # receives DML grants from migrations
    database_sslmode: str = "prefer"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_statement_timeout_ms: int = Field(default=30_000, ge=1_000)

    # --- Redis / Celery --------------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")
    redis_cache_db: int = 0
    redis_broker_db: int = 1
    redis_result_db: int = 2
    redis_socket_timeout_seconds: float = 2.0
    redis_tls: bool = False  # rediss:// with certificate verification (managed Redis services)

    # --- Health checks ---------------------------------------------------------------
    health_check_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    # --- Sessions and authentication (Phase 2) --------------------------------------
    session_cookie_name: str = "dgi_session"
    csrf_cookie_name: str = "dgi_csrf"
    session_cookie_secure: bool | None = None  # None -> secure outside development/test
    session_absolute_timeout_minutes: int = Field(default=720, ge=5, le=1440)
    session_idle_timeout_minutes: int = Field(default=30, ge=5, le=480)
    login_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    api_rate_limit_per_minute: int = Field(default=600, ge=10)
    lockout_threshold: int = Field(default=5, ge=3, le=20)
    lockout_minutes: int = Field(default=15, ge=1, le=1440)
    password_min_length: int = Field(default=12, ge=10, le=128)
    mfa_issuer: str = "DG-IMEWS"
    # Roles that must use MFA before any other action (codes from iam.roles).
    mfa_required_roles: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "super_admin",
            "district_magistrate",
            "additional_district_magistrate",
            "auditor",
        ]
    )

    # --- Encryption of sensitive data at rest (application layer) -------------------
    data_encryption_key: SecretStr = SecretStr("")
    data_encryption_previous_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    lookup_hmac_key: SecretStr = SecretStr("")

    # --- Object storage (S3-compatible, private) -------------------------------------
    storage_endpoint: str = "localhost:3900"
    storage_access_key: str = ""
    storage_secret_key: SecretStr = SecretStr("")
    storage_bucket: str = "dgimews-files"
    storage_region: str = "garage"
    storage_secure: bool = False
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)

    # --- Malware scanning --------------------------------------------------------------
    malware_scanner: str = "none"  # "clamav" or "none" (none is refused in production)
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    # "inline": the API scans before accepting the upload (needs clamd reachable from the API).
    # "deferred": the upload is stored as "pending" and a background worker scans it; it cannot
    # be downloaded until marked clean. Use deferred where the API cannot reach clamd privately
    # (for example on Vercel).
    malware_scan_mode: Literal["inline", "deferred"] = "inline"

    # --- Grievances --------------------------------------------------------------------
    grievance_reference_prefix: str = "DGI"

    # --- GIS ---------------------------------------------------------------------------
    map_tile_url: str | None = None  # optional basemap; boundaries render without it

    # --- Monitoring -----------------------------------------------------------------------
    metrics_token: SecretStr = SecretStr("")

    @field_validator(
        "allowed_hosts",
        "cors_allowed_origins",
        "mfa_required_roles",
        "data_encryption_previous_keys",
        mode="before",
    )
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator(
        "deployment_district_name",
        "deployment_district_name_local",
        "deployment_state_name",
        "deployment_state_name_local",
        "database_migration_user",
        "map_tile_url",
        "client_ip_header",
        "session_cookie_secure",
        "expose_api_docs",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        # Compose passes unset variables as empty strings; treat them as "not configured".
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {value}")
        return upper

    @field_validator("database_sslmode")
    @classmethod
    def _valid_sslmode(cls, value: str) -> str:
        allowed = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        if value not in allowed:
            raise ValueError(f"database_sslmode must be one of {sorted(allowed)}")
        return value

    @model_validator(mode="after")
    def _add_vercel_deployment_hosts(self) -> Self:
        """On Vercel, accept the addresses Vercel reports for this deployment.

        Every preview deployment gets its own *.vercel.app address, which cannot be listed
        in ALLOWED_HOSTS in advance. Vercel sets these variables itself (they are not user
        input); only syntactically valid host names are added. Custom domains must still be
        listed in ALLOWED_HOSTS.
        """
        if os.environ.get("VERCEL") != "1":
            return self
        for var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
            host = os.environ.get(var, "").strip().lower()
            host = host.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
            if _HOSTNAME.fullmatch(host) and host not in self.allowed_hosts:
                self.allowed_hosts.append(host)
        return self

    @model_validator(mode="after")
    def _enforce_production_rules(self) -> Self:
        if self.app_env not in (Environment.PRODUCTION, Environment.STAGING):
            return self
        problems: list[str] = []
        secrets = {
            "DATABASE_PASSWORD": self.database_password,
            "REDIS_PASSWORD": self.redis_password,
        }
        if self.database_migration_password is not None:
            secrets["DATABASE_MIGRATION_PASSWORD"] = self.database_migration_password
        secrets["DATA_ENCRYPTION_KEY"] = self.data_encryption_key
        secrets["LOOKUP_HMAC_KEY"] = self.lookup_hmac_key
        secrets["STORAGE_SECRET_KEY"] = self.storage_secret_key
        for name, secret in secrets.items():
            raw = secret.get_secret_value()
            if len(raw) < MIN_PRODUCTION_SECRET_LENGTH:
                problems.append(f"{name} must be at least {MIN_PRODUCTION_SECRET_LENGTH} characters")
            elif any(marker in raw.lower() for marker in PLACEHOLDER_MARKERS):
                problems.append(f"{name} looks like a placeholder value")
        if self.log_level == "DEBUG":
            problems.append("LOG_LEVEL=DEBUG is not permitted in staging/production")
        if "*" in self.allowed_hosts:
            problems.append("ALLOWED_HOSTS must not contain '*'")
        if "*" in self.cors_allowed_origins:
            problems.append("CORS_ALLOWED_ORIGINS must not contain '*'")
        if not self.deployment_district_name:
            problems.append("DEPLOYMENT_DISTRICT_NAME must be configured")
        if self.session_cookie_secure is False:
            problems.append("SESSION_COOKIE_SECURE must not be false in staging/production")
        if self.malware_scanner != "clamav":
            problems.append("MALWARE_SCANNER must be 'clamav' in staging/production")
        if problems:
            raise ValueError("Unsafe configuration: " + "; ".join(problems))
        return self

    # --- Derived values ----------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def cookies_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env not in (Environment.DEVELOPMENT, Environment.TEST)

    @property
    def api_docs_enabled(self) -> bool:
        if self.expose_api_docs is not None:
            return self.expose_api_docs
        return self.app_env != Environment.PRODUCTION

    def _db_url(self, user: str, password: SecretStr) -> str:
        return (
            f"postgresql+psycopg://{quote(user, safe='')}:"
            f"{quote(password.get_secret_value(), safe='')}@"
            f"{self.database_host}:{self.database_port}/{quote(self.database_name, safe='')}"
            f"?sslmode={self.database_sslmode}"
        )

    @property
    def database_url(self) -> str:
        return self._db_url(self.database_user, self.database_password)

    @property
    def migration_database_url(self) -> str:
        if self.database_migration_user and self.database_migration_password is not None:
            return self._db_url(self.database_migration_user, self.database_migration_password)
        return self.database_url

    def _redis_url(self, db: int) -> str:
        auth = ""
        if self.redis_password.get_secret_value():
            auth = f":{quote(self.redis_password.get_secret_value(), safe='')}@"
        if self.redis_tls:
            return f"rediss://{auth}{self.redis_host}:{self.redis_port}/{db}?ssl_cert_reqs=required"
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{db}"

    @property
    def redis_cache_url(self) -> str:
        return self._redis_url(self.redis_cache_db)

    @property
    def celery_broker_url(self) -> str:
        return self._redis_url(self.redis_broker_db)

    @property
    def celery_result_backend_url(self) -> str:
        return self._redis_url(self.redis_result_db)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
