"""Administrative command line.

python -m app.cli create-superadmin --username admin --full-name "Name"
    Password is read from DGI_BOOTSTRAP_PASSWORD or prompted (never an argument).
    Refuses if an active Super Administrator already exists.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.core import security
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.modules.audit import service as audit
from app.modules.iam.models import Role, User, UserRole


def create_superadmin(username: str, full_name: str) -> int:
    password = os.environ.get("DGI_BOOTSTRAP_PASSWORD") or getpass.getpass("Temporary password: ")
    try:
        security.validate_password_policy(password, username=username, full_name=full_name)
    except security.WeakPasswordError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    with get_session_factory()() as db, db.begin():
        role_id = db.execute(select(Role.id).where(Role.code == "super_admin")).scalar_one()
        existing = db.execute(
            select(User.username)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_id == role_id, User.is_active.is_(True))
        ).first()
        if existing:
            print("An active Super Administrator already exists; refusing.", file=sys.stderr)
            return 3
        if db.execute(select(User.id).where(User.username == username)).first():
            print("Username already exists.", file=sys.stderr)
            return 4
        user = User(
            username=username,
            full_name=full_name,
            password_hash=security.hash_password(password),
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role_id))
        audit.record(
            db,
            action="iam.superadmin_bootstrapped",
            actor=audit.Actor(None, "cli"),
            resource_type="user",
            resource_id=user.id,
            details={"username": username},
        )
    print(
        f"Created Super Administrator '{username}'. MFA enrolment and a password change are required at first sign-in."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings())
    import logging

    for h in logging.getLogger().handlers:  # keep stdout clean for data streams (export-objects)
        if isinstance(h, logging.StreamHandler):
            h.setStream(sys.stderr)
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-superadmin")
    p.add_argument("--username", required=True)
    p.add_argument("--full-name", required=True)
    sub.add_parser("load-demo-data", help="DEVELOPMENT ONLY: load clearly labelled synthetic demo data")
    sub.add_parser("export-objects", help="Write all stored objects as a tar stream to stdout (backup)")
    sub.add_parser("import-objects", help="Read a tar stream from stdin into object storage (restore)")
    t = sub.add_parser("demo-totp", help="DEVELOPMENT ONLY: print the current TOTP code of a demo.* account")
    t.add_argument("username")
    args = parser.parse_args(argv)
    if args.command == "create-superadmin":
        return create_superadmin(args.username.strip().lower(), args.full_name.strip())
    if args.command == "load-demo-data":
        from app.demo import load_demo_data

        return int(load_demo_data())
    if args.command in ("export-objects", "import-objects"):
        from app import backup

        return backup.export_objects() if args.command == "export-objects" else backup.import_objects()
    if args.command == "demo-totp":
        from app.demo import demo_totp

        return demo_totp(args.username)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
