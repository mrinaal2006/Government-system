# Database design

PostgreSQL 16 + PostGIS 3.4. Migrations: Alembic (`backend/alembic/versions`).

## Conventions

| Rule | Implementation |
|---|---|
| Primary keys | `uuid`, `DEFAULT gen_random_uuid()` (+ Python default for pre-flush IDs) |
| Timestamps | `timestamptz`; every connection uses `timezone=UTC`; displayed in IST by the UI |
| `updated_at` | Maintained by trigger `public.dgimews_set_updated_at()` so non-ORM writes are correct |
| Enumerations | `varchar` + `CHECK (col IN (...))`, not PG `ENUM` — values can be added in a transactional migration |
| Constraint names | Deterministic naming convention (`pk_`, `fk_<table>_<col>_<ref>`, `uq_`, `ck_`, `ix_`) |
| Deletion | Reference rows are deactivated (`is_active = false`), not deleted. The runtime role has **no DELETE** privilege on `ref`. Grievance history tables (Phase 4) will be append-only. |
| Model ↔ migration drift | Integration test `test_orm_models_match_migrations` runs Alembic autogenerate comparison and must be empty |

## Roles and privileges ([ADR 0003](adr/0003-database-roles.md))

| Role | Purpose | Privileges |
|---|---|---|
| `postgres` | Superuser; init script only (extensions, roles) | all |
| `dgimews_migrator` | Owns database and schemas; used only by `alembic` | DDL in owned schemas, `CREATE` on `public` |
| `dgimews_app` | API and worker runtime | `SELECT, INSERT, UPDATE` on `ref`; `SELECT` on `public.alembic_version`; no DDL, no DELETE, no TRUNCATE |

Integration tests assert the runtime role is denied `DELETE`, `TRUNCATE`,
`CREATE TABLE` (in `ref` and `public`), `ALTER`, `DROP` and `CREATE SCHEMA`.

## Schemas

| Schema | Owner module | Contents | Created in |
|---|---|---|---|
| `public` | — | PostGIS objects, `alembic_version`, trigger function | Phase 1 |
| `ref` | geography, administration | administrative geography, departments, categories, sources | **Phase 1** |
| `iam` | iam | users, roles, permissions, user_roles, role_permissions, user_scope_assignments, user_sessions, mfa_credentials | Phase 2 |
| `audit` | audit | audit_logs (append-only, INSERT-only grant, hash-chained) | Phase 2 |
| `grievance` | grievances, intake | grievances, assignments, status_history, comments, attachments, external_references, relationships | Phase 4 |
| `citizen` | grievances | complainant personal data, separately granted and encryptable | Phase 4 |
| `intel` | intelligence, early_warning | ai_classifications(+history), duplicate_candidates, grievance_clusters, risk_assessments, early_warning_alerts | Phases 5–6 |
| `perf` | performance | sla_policies, sla_events, escalations, department_performance_snapshots | Phase 7 |
| `governance` | notifications, reports, administration | notifications, report_jobs, system_configurations | Phases 3, 8 |

## Phase 1 tables (implemented)

### Administrative hierarchy

```
district ─┬─ subdivision
          ├─ block ──────── gram_panchayat
          ├─ village   (optional → subdivision, block, gram_panchayat)
          └─ municipality ── ward
```

**Assumption (documented, not invented):** development blocks and revenue
subdivisions/tehsils do not nest consistently across states, and village ↔ GP
mapping must come from source data. So `blocks.subdivision_id` and all village
links except `district_id` are **nullable**, populated only from verified data
(e.g. Local Government Directory). No relationship is inferred by the system.

Every administrative unit table has:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `lgd_code` | varchar(16) | digits only (CHECK); unique when present (partial unique index) |
| `name_en` | varchar(200) | not blank (CHECK); trigram GIN index for search |
| `name_local` | varchar(200) | official local-language name |
| `boundary` | geometry(MultiPolygon, 4326) | GiST index; must be valid (`ST_IsValid` CHECK) |
| `geometry_dataset_id` | uuid → `boundary_datasets` | **required whenever a geometry is present** (CHECK) |
| `is_active`, `created_at`, `updated_at` | | |

Additional columns: `districts.state_name_en`, `state_lgd_code`;
`municipalities.body_type` (CHECK: municipal_corporation, municipal_council,
nagar_panchayat, cantonment_board, other); `villages.census_code` (unique when
present), `villages.location` geometry(Point, 4326) with GiST index and its own
provenance CHECK; `wards.ward_number` (unique per municipality).

### `ref.boundary_datasets` — geometry provenance

`name`, `publisher`, `dataset_version` (unique together), `source_reference`,
`licence`, `acquired_on`, `checksum_sha256` (format CHECK), `verified_at`,
`verification_notes`. A boundary or point **cannot be stored** without a row here,
so unverified coordinates cannot enter silently.

### `ref.departments`, `ref.issue_categories`, `ref.grievance_sources`

* `departments`: `code` (unique, `^[A-Z][A-Z0-9_]{1,49}$`), names, `description`,
  self-referencing `parent_id` (not self).
* `issue_categories`: same code rule; `parent_id` → subcategory tree;
  `default_department_id`; `is_essential_service` (admin-set flag for Phase 6).
* `grievance_sources`: `code`, names, `channel_type` (CHECK: helpline,
  government_portal, administrative_office, print_media, social_media, manual,
  departmental_record), `integration_mode` (CHECK: not_configured,
  development_adapter, file_import, live_api; default `not_configured`).

### Data loaded by migrations

Only the seven source **channels** named in the specification (migration 0002),
all `not_configured`. No districts, blocks, villages, departments, categories or
geometries are pre-loaded; tests assert these tables start empty. They must be
imported from verified sources (Phase 3 admin UI / Phase 6 boundary import).

## Planned schema for later phases (design summary)

* **Grievances (Phase 4):** `grievance.grievances` with an immutable human
  reference (`reference_no`, generated by a sequence per district/year, `UNIQUE`,
  protected from UPDATE by trigger), FKs to source, category, subcategory,
  department, location units; `current_status` with allowed transitions enforced in
  the service and by a CHECK; `grievance_status_history` append-only (runtime role
  has INSERT/SELECT only); assignments with `SELECT … FOR UPDATE` + partial unique
  index "one active assignment per grievance"; personal data in
  `citizen.complainants` referenced by id.
* **AI (Phase 5):** `intel.ai_classifications` stores model_id, model_version,
  prediction (jsonb), confidence, input_ref, status, evidence (jsonb),
  verification_status, verified_by/at; history table is append-only.
* **Retention/archival:** every grievance-side table gets `retention_class`;
  archival moves closed records past retention into `archive` schema partitions;
  the exact periods require a documented government retention policy (to be
  provided — not assumed).
