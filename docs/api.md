# API reference (v1)

Base path: `/api/v1`. The OpenAPI schema is served at `/api/v1/openapi.json` with
Swagger UI at `/api/docs` outside production (`EXPOSE_API_DOCS` overrides).

## Conventions

* JSON only; timestamps are ISO-8601 UTC.
* Every response carries `X-Request-ID`. Quote it when reporting a problem.
* Errors use one envelope:

```json
{"error": {"code": "not_found", "message": "Not Found", "request_id": "6f1c…", "details": []}}
```

Validation errors (`422`, code `validation_error`) list
`{"location": [...], "message": "...", "type": "..."}` per field and never echo the
submitted value.

## Endpoints implemented in Phase 1 (unauthenticated by design)

### `GET|HEAD /health/live`
Process liveness; checks no dependencies. `200 {"status": "ok"}`.

### `GET /health/ready`
Readiness for traffic. `200` when all components are usable, otherwise `503` with
the same body shape:

```json
{
  "status": "ok",
  "checked_at": "2026-10-31T10:32:26.201283+00:00",
  "components": {
    "database":   {"status": "ok", "latency_ms": 4.4, "reason": null},
    "postgis":    {"status": "ok", "latency_ms": 0.8, "reason": null},
    "migrations": {"status": "ok", "latency_ms": 7.1, "reason": null},
    "redis":      {"status": "ok", "latency_ms": 3.5, "reason": null}
  }
}
```

`reason` codes: `unreachable`, `timeout`, `schema_not_at_head`,
`extension_missing`, `database_unavailable`, `no_pong`. Hostnames, versions and
exception text are never returned (they are logged server-side).

### `GET /system/info`
```json
{"application": "DG-IMEWS", "version": "0.1.0", "environment": "development",
 "deployment": {"district_name": null, "district_name_local": null,
                "state_name": null, "state_name_local": null}}
```
`null` means "not configured"; the UI displays that rather than a default name.
