import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

STRONG = "x9Kq2LmP7vR4tZ8wB3nY6cF1"


def _prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "database_password": STRONG,
        "redis_password": STRONG + "r",
        "deployment_district_name": "Configured District",
        "data_encryption_key": STRONG + "d",
        "lookup_hmac_key": STRONG + "h",
        "storage_secret_key": STRONG + "s",
        "malware_scanner": "clamav",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_development_defaults_are_accepted(env: pytest.MonkeyPatch) -> None:
    s = Settings()
    assert s.app_env is Environment.DEVELOPMENT
    assert s.api_docs_enabled is True


def test_production_accepts_strong_configuration(env: pytest.MonkeyPatch) -> None:
    s = _prod()
    assert s.is_production
    assert s.api_docs_enabled is False  # docs off by default in production


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"database_password": "short"}, "DATABASE_PASSWORD must be at least"),
        ({"database_password": "CHANGE_ME_CHANGE_ME_1234"}, "DATABASE_PASSWORD looks like"),
        ({"redis_password": ""}, "REDIS_PASSWORD must be at least"),
        ({"log_level": "debug"}, "LOG_LEVEL=DEBUG"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
        ({"cors_allowed_origins": "*"}, "CORS_ALLOWED_ORIGINS"),
        ({"deployment_district_name": None}, "DEPLOYMENT_DISTRICT_NAME"),
        ({"database_migration_password": "changeme"}, "DATABASE_MIGRATION_PASSWORD"),
    ],
)
def test_production_rejects_unsafe_configuration(
    env: pytest.MonkeyPatch, override: dict[str, object], fragment: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        _prod(**override)
    assert fragment in str(exc.value)


def test_staging_is_held_to_production_rules(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="staging", database_password="weak")  # type: ignore[arg-type]


def test_unsafe_error_message_never_contains_the_secret(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as exc:
        _prod(database_password="example-secret-value-123")
    assert "example-secret-value-123" not in str(exc.value)


def test_environment_variables_and_csv_lists(env: pytest.MonkeyPatch) -> None:
    env.setenv("ALLOWED_HOSTS", "a.example, b.example ,")
    env.setenv("DATABASE_PORT", "6543")
    s = Settings()
    assert s.allowed_hosts == ["a.example", "b.example"]
    assert s.database_port == 6543


def test_database_url_escapes_special_characters(env: pytest.MonkeyPatch) -> None:
    s = Settings(database_user="app", database_password="p@ss:w/rd#1")  # type: ignore[arg-type]
    assert "p%40ss%3Aw%2Frd%231@" in s.database_url
    assert s.database_url.startswith("postgresql+psycopg://app:")


def test_migration_url_falls_back_to_runtime_credentials(env: pytest.MonkeyPatch) -> None:
    s = Settings(database_user="app", database_password="pw")  # type: ignore[arg-type]
    assert s.migration_database_url == s.database_url
    s2 = Settings(
        database_user="app",
        database_password="pw",  # type: ignore[arg-type]
        database_migration_user="owner",
        database_migration_password="pw2",  # type: ignore[arg-type]
    )
    assert "//owner:pw2@" in s2.migration_database_url


def test_redis_urls_use_separate_databases(env: pytest.MonkeyPatch) -> None:
    s = Settings(redis_password="secret", redis_host="r")  # type: ignore[arg-type]
    assert s.redis_cache_url == "redis://:secret@r:6379/0"
    assert s.celery_broker_url.endswith("/1")
    assert s.celery_result_backend_url.endswith("/2")


def test_secrets_are_masked_in_repr(env: pytest.MonkeyPatch) -> None:
    s = Settings(database_password="topsecretvalue")  # type: ignore[arg-type]
    assert "topsecretvalue" not in repr(s)


def test_invalid_values_are_rejected(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="LOUD")
    with pytest.raises(ValidationError):
        Settings(database_sslmode="maybe")
    with pytest.raises(ValidationError):
        Settings(app_env="qa")  # type: ignore[arg-type]


def test_blank_identity_values_mean_not_configured(env: pytest.MonkeyPatch) -> None:
    env.setenv("DEPLOYMENT_DISTRICT_NAME", "   ")
    env.setenv("DEPLOYMENT_STATE_NAME", "")
    s = Settings()
    assert s.deployment_district_name is None
    assert s.deployment_state_name is None


def test_blank_district_name_still_fails_production(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="DEPLOYMENT_DISTRICT_NAME"):
        _prod(deployment_district_name="  ")


def test_blank_optional_booleans_mean_default(env: pytest.MonkeyPatch) -> None:
    env.setenv("SESSION_COOKIE_SECURE", "")
    env.setenv("EXPOSE_API_DOCS", "")
    s = Settings()
    assert s.session_cookie_secure is None and s.cookies_secure is False  # development default
    assert s.expose_api_docs is None


def test_redis_tls_urls(env: pytest.MonkeyPatch) -> None:
    s = Settings(redis_password="secret", redis_host="r.example", redis_tls=True)  # type: ignore[arg-type]
    assert s.celery_broker_url == "rediss://:secret@r.example:6379/1?ssl_cert_reqs=required"
    assert Settings(redis_host="r").redis_cache_url.startswith("redis://")


def test_malware_scan_mode_validated(env: pytest.MonkeyPatch) -> None:
    assert Settings(malware_scan_mode="deferred").malware_scan_mode == "deferred"
    with pytest.raises(ValidationError):
        Settings(malware_scan_mode="sometimes")  # type: ignore[arg-type]
