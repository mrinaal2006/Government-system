# Operations runbook

## Monitoring

Prometheus (compose profile `monitoring`) scrapes `/api/v1/system/metrics` on the internal
network with a bearer token. Metrics:

| Metric | Meaning |
|---|---|
| `dgimews_component_up{component}` | database, postgis, migrations, redis, object_storage (1 = usable) |
| `dgimews_http_requests_total{method,route,status}` | request counts by route template |
| `dgimews_http_request_seconds` | latency histogram |
| `dgimews_celery_queue_length` | queued background tasks |
| `dgimews_grievances_open`, `dgimews_grievances_overdue` | operational picture |
| `dgimews_alerts_active{level}` | active early-warning alerts |
| `dgimews_report_jobs_failed_24h` | failed report jobs |

Alert rules (`infra/monitoring/alerts.yml`): dependency down, API down, error rate > 2 %,
p95 latency > 2 s, task backlog, burst of failed sign-ins, failing reports. Route them to the
IT cell through Alertmanager or the department's paging system.

Logs: every container writes JSON lines to stdout with `request_id`; nginx logs the same ID,
so one ID traces a request end to end. Query strings and personal data are never logged.

## Backup

```bash
BACKUP_PASSPHRASE=... COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml" ./scripts/backup.sh /srv/backups
```

Produces an encrypted PostgreSQL dump (with ownership and privileges), an encrypted archive
of every stored object, and a SHA-256 manifest. Schedule it (for example nightly via cron or a
systemd timer), copy the output off-host, and keep the passphrase in the secret manager.

## Restore / disaster recovery

```bash
BACKUP_PASSPHRASE=... COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml" ./scripts/restore.sh /srv/backups/dgimews-<timestamp>
```

Requirements: the same `DATA_ENCRYPTION_KEY`, `LOOKUP_HMAC_KEY` and database role passwords as
the source. On a new host, start the stack once (to create roles and an empty schema), then run
the restore. The script verifies checksums, recreates the database, restores it as superuser,
restarts services and re-imports objects. After restoring: check readiness, record counts,
**Audit log → Verify integrity**, and open one attachment.

**Drill performed during development (31 Oct 2026):** after a backup, the database and
object-storage volumes were destroyed and the stack recreated empty. The restore took 24 s;
grievance and alert counts matched exactly (119 / 7), the audit hash chain verified, an
attachment was byte-identical, and the runtime role was still denied DELETE/UPDATE on history
and audit tables. RPO equals the backup interval; RTO is minutes for this data volume.

## Routine tasks

| Task | How |
|---|---|
| Unlock an account | Users and roles → Unlock (audited) |
| Lost authenticator | Users and roles → Reset MFA; user enrols again at next sign-in |
| Leaver | Deactivate the account (sessions are revoked immediately) |
| Change of posting | Edit roles and area of responsibility (sessions are revoked on role change) |
| Verify audit integrity | Audit log → Verify integrity; investigate any failure as a security incident |
| Re-run alert evaluation | Early warning → Re-evaluate now (also runs every 15 minutes) |

## Key rotation

* **Data encryption key:** set the new key as `DATA_ENCRYPTION_KEY` and the old one in
  `DATA_ENCRYPTION_PREVIOUS_KEYS`; restart. New writes use the new key; old values remain
  readable. Re-encrypting existing rows is a planned maintenance task (not yet automated).
* **LOOKUP_HMAC_KEY:** rotating it breaks duplicate matching against older complainant
  records; rotate only with a planned re-hash.
* **Database/Redis/storage passwords, metrics token:** update `.env` and the corresponding
  service, then restart.

## Incident response (outline)

1. Preserve evidence: export audit logs and container logs for the period.
2. Contain: deactivate affected accounts, rotate secrets, block source addresses at the firewall.
3. Report to CERT-In within the time limit required by its directions, and to the data
   protection authority where the DPDP Act requires it (the district's nodal officer decides).
4. Restore from a known-good backup if integrity is in doubt; verify the audit chain.

## Retention

Not implemented as automatic deletion: retention periods for grievance and personal data
must be set by an official retention schedule. `citizen.complainants.retention_until` exists
to support it once the schedule is approved.
