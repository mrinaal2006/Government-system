#!/usr/bin/env bash
# Create a local .env from .env.example, replacing every CHANGE_ME placeholder with
# a freshly generated secret of the right format. Development use only: production
# secrets must come from the deployment's secret manager.
#
#   ./scripts/init-dev-env.sh                 create .env (refuses to overwrite)
#   ./scripts/init-dev-env.sh --add-missing   append keys added to .env.example since
#                                             .env was created; existing values are kept
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=create
[ "${1:-}" = "--add-missing" ] && MODE=add
if [ "$MODE" = create ] && [ -e .env ]; then
  echo ".env already exists; not overwriting (use --add-missing to add new keys)." >&2
  exit 1
fi

MODE="$MODE" python3 - <<'PY'
import os, re, secrets

def generate(placeholder: str) -> str:
    if placeholder == "CHANGE_ME_HEX64":
        return secrets.token_hex(32)
    if placeholder == "CHANGE_ME_GARAGE_KEY_ID":
        return "GK" + secrets.token_hex(12)
    return secrets.token_urlsafe(32)

existing = {}
if os.environ["MODE"] == "add" and os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m:
            existing[m.group(1)] = True

out = []
for line in open(".env.example", encoding="utf-8"):
    m = re.match(r"^([A-Z0-9_]+)=(CHANGE_ME\w*)\s*$", line)
    key = re.match(r"^([A-Z0-9_]+)=", line)
    if os.environ["MODE"] == "add":
        if key and key.group(1) not in existing:
            out.append(f"{key.group(1)}={generate(m.group(2))}\n" if m else line)
        continue
    out.append(f"{m.group(1)}={generate(m.group(2))}\n" if m else line)

mode = "a" if os.environ["MODE"] == "add" else "w"
with open(".env", mode, encoding="utf-8") as fh:
    if mode == "a" and out:
        fh.write("\n# --- Added by init-dev-env.sh --add-missing ---\n")
    fh.writelines(out)
print(f"{'Added' if mode == 'a' else 'Wrote'} {sum(1 for l in out if re.match(r'^[A-Z0-9_]+=', l))} settings.")
PY
chmod 600 .env
