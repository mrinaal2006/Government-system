# Security controls

The design uses OWASP ASVS, CERT-In directions, the DPDP Act and GIGW as reference points.
**No compliance or certification is claimed**; that requires an independent assessment.

| Area | Control | Where / evidence |
|---|---|---|
| Passwords | Argon2id (64 MiB, t=3); length ≥ 12, 3 character classes, not containing username/name, deny-list; rehash on login | `core/security.py`; tests |
| Login abuse | Per-IP and per-username rate limit (fails closed if Redis is down); lockout after 5 failures for 15 min; identical message for unknown user / wrong password; timing equalised | `iam/service.py`; `test_auth.py` |
| MFA | TOTP (RFC 6238), secret encrypted at rest, replay protection; mandatory for Super Admin, DM, ADM, Auditor | tests + E2E |
| Sessions | Opaque token, SHA-256 stored, HttpOnly + SameSite=Strict + Secure; absolute 12 h, idle 30 min; rotation after MFA/password change; revoked on logout, role change, reset, deactivation | ADR 0008 |
| CSRF | Per-session secret in header for unsafe methods; Origin check on login | tests |
| Suspicious sign-in | New network address or recent failures → audit event + user notification | `test_auth.py` |
| Authorization | Permission catalogue per role; every endpoint declares permissions; scopes applied as SQL predicates; out-of-scope = 404; denials audited | 153-case matrix test |
| Separation of duties | Super Admin has no grievance/citizen access; Auditor read-only; resolution submitter cannot verify it | tests |
| Citizen data | Separate schema; AES (Fernet) encryption at application layer; HMAC lookup hash; masked without `citizen.read`; every view audited; PII in exports only on explicit request + permission | tests |
| Database | Migration role vs runtime role; runtime cannot DDL; history/audit append-only; immutable reference via trigger | `test_database.py` |
| Audit | Append-only, hash-chained, verifiable; failed logins and denials recorded in independent transactions | tests + DR drill |
| Input/output | Pydantic validation; ORM/bound parameters only; validation errors never echo input; XLSX formula injection neutralised; React escaping, no `dangerouslySetInnerHTML` (lint rule) | probes in matrix test, E2E XSS test |
| Files | Magic-byte + extension check (PDF/PNG/JPEG), 10 MB limit, sanitised names, ClamAV INSTREAM scan, private storage, download only via authorised endpoint with `attachment` disposition | tests; EICAR detected |
| Transport | TLS 1.2/1.3 only, HSTS, HTTP→HTTPS redirect | verified with openssl/curl |
| Browser | Strict CSP (self only, no inline), frame-ancestors none, nosniff, no source maps | E2E |
| Infrastructure | Non-root, read-only containers, all capabilities dropped, internal data network, Redis auth with dangerous commands disabled, metrics blocked at the edge | compose files |
| Secrets | Environment/Docker secrets only; production refuses weak/placeholder values; build CA via BuildKit secret, not in layers | unit tests |
| Logging | JSON with request IDs; sensitive keys redacted; query strings never logged | unit tests |

## Known gaps

* Rate limiting is per process/Redis window; a distributed WAF is recommended in front.
* Encryption at rest for PostgreSQL/object storage relies on host disk encryption.
* Re-encryption on key rotation is manual; automatic data retention is not implemented
  (needs an approved retention schedule).
* No independent penetration test or accessibility audit has been performed.
* The interface is English-only.
