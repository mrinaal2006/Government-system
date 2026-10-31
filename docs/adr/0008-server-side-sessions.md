# ADR 0008: Server-side sessions instead of bearer tokens

**Status:** Accepted (Phase 2)

**Decision.** Opaque random session tokens in HttpOnly, SameSite=Strict cookies; only a
SHA-256 of the token is stored. CSRF protection uses a per-session secret echoed in a
header. Sessions have absolute and idle timeouts, are rotated after MFA and password
changes, and are revoked on logout, role change, password reset and deactivation.

**Why.** Immediate revocation is required for a government system (a JWT cannot be
revoked before expiry without a server-side list anyway). Nothing usable as a credential
is readable by JavaScript, which limits the impact of any XSS.
