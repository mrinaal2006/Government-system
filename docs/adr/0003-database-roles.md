# ADR 0003: Separate migration and runtime database roles

**Status:** Accepted (Phase 1)

**Decision.** Three roles: `postgres` (superuser, init script only), a migration
role that owns the database and schemas, and a runtime role that receives only
`SELECT, INSERT, UPDATE` grants from migrations (`ALTER DEFAULT PRIVILEGES`). The
runtime role has no DDL rights and no `DELETE` on reference data; append-only
tables (status history, audit logs) will receive `INSERT, SELECT` only.

**Consequences.** A compromised API process cannot alter the schema, drop tables or
delete history. Extensions (PostGIS etc.) must be installed by the superuser init
script because the migration role is not a superuser; migration 0001 verifies they
exist and fails with instructions otherwise. Integration tests assert the denials.
