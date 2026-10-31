#!/usr/bin/env bash
# Create a local .env from .env.example, replacing every CHANGE_ME with a fresh
# random secret. Refuses to overwrite an existing .env. Development use only:
# production secrets must come from the deployment's secret manager.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -e .env ]; then
  echo ".env already exists; not overwriting." >&2
  exit 1
fi

python3 - <<'PY'
import secrets
lines = []
for line in open(".env.example", encoding="utf-8"):
    if "=CHANGE_ME" in line:
        key = line.split("=", 1)[0]
        line = f"{key}={secrets.token_urlsafe(32)}\n"
    lines.append(line)
with open(".env", "w", encoding="utf-8") as fh:
    fh.writelines(lines)
PY
chmod 600 .env
echo "Created .env with random development secrets (mode 600)."
