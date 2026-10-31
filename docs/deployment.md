# Production deployment

Single-host deployment with Docker Compose. All commands run from the repository root.

## 1. Prerequisites

* Linux host with Docker Engine and Compose v2, ports 80/443 reachable from the office network.
* A TLS certificate and key for the public hostname, issued by a trusted CA (for example NIC
  or the department's PKI). The self-signed script is for local testing only.
* Outbound HTTPS for ClamAV signature updates (`database.clamav.net`) or a local signature mirror.
* Disk encryption on the volumes that hold PostgreSQL and object storage.

## 2. Secrets

Create `.env` from `.env.example` and fill every `CHANGE_ME` from the department's secret
manager (or run `./scripts/init-dev-env.sh` on a secure host and transfer the values).
Production refuses to start if any secret is shorter than 16 characters or looks like a
placeholder, if `DEPLOYMENT_DISTRICT_NAME` is unset, if cookies are not Secure, or if malware
scanning is disabled.

**Store `DATA_ENCRYPTION_KEY` and `LOOKUP_HMAC_KEY` separately from backups.** Without them,
encrypted complainant data cannot be read after a restore.

Also set: `DEPLOYMENT_DISTRICT_NAME` (and local-language/state names), `ALLOWED_HOSTS`
(the public hostname), `GRIEVANCE_REFERENCE_PREFIX` (for example the district code),
`DATABASE_SSLMODE=verify-full` if PostgreSQL runs on another host.

Write the metrics token for Prometheus: `grep ^METRICS_TOKEN= .env | cut -d= -f2- > secrets/metrics_token`.

## 3. Certificates

Place `tls.crt` (full chain) and `tls.key` in `secrets/tls/`.

## 4. Build and start

```bash
./scripts/build-images.sh
```

```bash
docker compose --profile scan --profile monitoring -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The `migrate` job applies database migrations and `storage-init` prepares the private bucket
before the API and workers start. First start of ClamAV downloads signatures (several minutes).

## 5. First administrator

```bash
docker compose exec api python -m app.cli create-superadmin --username admin.dg --full-name "Name of officer"
```

Alternatively, open the site and use *Sign up*: while no Super Administrator exists, the first
account created there becomes one. Do this immediately after deployment.

The password is prompted (never on the command line). At first sign-in the administrator must
enrol MFA and change the password. The administrator then creates officer accounts, roles and
areas of responsibility under **Users and roles**, and loads master data under **Configuration**
(departments, categories, verified geography and boundaries, SLA policies with their legal
references, classification rules). The provisional risk model must be reviewed and approved.

## 6. Verify

* `https://<host>/` shows the sign-in page; `http://` redirects to `https://`.
* **System status** shows every component operational.
* Prometheus (`http://127.0.0.1:9090` on the host) shows target `dgimews-api` up.

## 7. Upgrades

1. Take a backup (`docs/operations.md`).
2. Build the new images, then `up -d` with the same command; `migrate` applies new migrations
   before the API restarts. Migrations are reviewed SQL and are tested downgrade/upgrade in CI.
3. Check readiness and the audit-chain verification.

## Hardening checklist

- [ ] Real CA-issued certificate; HSTS is sent automatically.
- [ ] Host firewall: only 80/443 open; Prometheus bound to 127.0.0.1.
- [ ] Disk encryption for Docker volumes; backups stored off-host.
- [ ] `.env` mode 600, owned by the deployment account; secrets rotated per policy.
- [ ] Time synchronised (NTP): TOTP and audit timestamps depend on it.
- [ ] Log shipping from container stdout to the central log system (JSON lines).
- [ ] Backup job scheduled and a restore drill performed quarterly.
- [ ] Independent security and accessibility audit before go-live (no certification is claimed).
