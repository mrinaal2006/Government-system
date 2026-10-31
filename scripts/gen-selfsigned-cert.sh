#!/usr/bin/env bash
# Self-signed certificate FOR LOCAL TESTING ONLY. Production must use a certificate
# issued by a trusted CA (for example via NIC or the department's PKI).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p secrets/tls
openssl req -x509 -newkey rsa:3072 -sha256 -days 30 -nodes \
  -keyout secrets/tls/tls.key -out secrets/tls/tls.crt \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
# The unprivileged nginx user (uid 101) must read the key inside the container; keep the
# secrets/ directory itself restricted to the deployment account.
chmod 644 secrets/tls/tls.key
chmod 700 secrets
echo "Wrote secrets/tls/tls.crt and tls.key (self-signed, 30 days, local testing only)."
