# ADR 0006: Garage as the S3-compatible object store

**Status:** Accepted (Phase 4)

**Context.** The specification requires private S3-compatible storage. The MinIO
container image was no longer obtainable from Docker Hub when this was built.

**Decision.** Use Garage v2 (open source, S3-compatible, single binary) for the reference
deployment, bootstrapped idempotently through its admin API (`infra/garage/bootstrap.py`).
The application uses the generic S3 protocol (`minio` Python client) and is not tied to
Garage: any S3-compatible service (for example a government cloud object store) can be
used by changing `STORAGE_*` settings.

**Consequences.** Buckets are private; the application key has read/write on one bucket
only; downloads always pass through authorised API endpoints (no presigned URLs).
Encryption at rest relies on volume/disk encryption of the host; citizen personal data
in the database is additionally encrypted at the application layer.
