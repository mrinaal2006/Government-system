import json
import logging

from app.core.logging import REDACTED, JsonFormatter, redact
from app.core.request_context import reset_request_id, set_request_id


def test_redact_masks_sensitive_keys_recursively() -> None:
    data = {
        "password": "p",
        "nested": {"mobile_number": "9", "Authorization": "Bearer x", "ok": 1},
        "items": [{"email": "a@b"}],
        "district": "kept",
    }
    out = redact(data)
    assert out["password"] == REDACTED
    assert out["nested"]["mobile_number"] == REDACTED
    assert out["nested"]["Authorization"] == REDACTED
    assert out["nested"]["ok"] == 1
    assert out["items"][0]["email"] == REDACTED
    assert out["district"] == "kept"


def test_json_formatter_includes_request_id_and_redacts_extras() -> None:
    record = logging.makeLogRecord(
        {
            "name": "t",
            "levelname": "INFO",
            "levelno": logging.INFO,
            "msg": "event",
            "aadhaar_number": "1234",
            "count": 3,
        }
    )
    token = set_request_id("req-12345678")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)
    assert payload["request_id"] == "req-12345678"
    assert payload["aadhaar_number"] == REDACTED
    assert payload["count"] == 3
    assert payload["timestamp"].endswith("+00:00")


def test_celery_accepts_json_only() -> None:
    import app.worker.tasks  # noqa: F401 - workers import included task modules at start
    from app.worker.celery_app import celery_app

    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.enable_utc is True
    assert "system.ping" in celery_app.tasks


def test_ping_task_executes_locally() -> None:
    from app.worker.tasks import ping

    assert ping.run()["status"] == "pong"
