"""Canonical CLI adapter for the RASAi product control plane.

The original platform CLI remains the broad additive command surface. This
adapter selects the integrity-hardened/multi-domain store and adds commands that
belong specifically to the canonical multi-user/data-governance layer.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from typing import Any

from .database import open_platform_store, resolve_platform_database_config
from .identity_directory import IdentityDirectory
from .postgres_admin import migrate_postgres, postgres_schema_status
from .secure_store import SecurePlatformStore
from . import cli as _cli


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _global_options(argv: list[str]) -> tuple[str, str | None, list[str]]:
    audits_root = "audits"
    platform_db: str | None = None
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--audits-root" and index + 1 < len(argv):
            audits_root = argv[index + 1]
            index += 2
            continue
        if value.startswith("--audits-root="):
            audits_root = value.split("=", 1)[1]
            index += 1
            continue
        if value == "--platform-db" and index + 1 < len(argv):
            platform_db = argv[index + 1]
            index += 2
            continue
        if value.startswith("--platform-db="):
            platform_db = value.split("=", 1)[1]
            index += 1
            continue
        remaining.append(value)
        index += 1
    return audits_root, platform_db, remaining


def _custom_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rasai platform")
    sub = parser.add_subparsers(dest="canonical_command", required=True)

    database = sub.add_parser("database", help="status e migrations explícitas do control plane")
    database_sub = database.add_subparsers(dest="database_command", required=True)
    database_sub.add_parser("status")
    database_sub.add_parser("migrate")

    user = sub.add_parser("user", help="usuários do control plane local/SaaS-ready")
    user_sub = user.add_subparsers(dest="user_command", required=True)
    user_add = user_sub.add_parser("add")
    user_add.add_argument("--name", required=True)
    user_add.add_argument("--email")
    user_sub.add_parser("list")

    identity = sub.add_parser("identity", help="vínculos OIDC issuer+subject para usuários internos")
    identity_sub = identity.add_subparsers(dest="identity_command", required=True)
    identity_link = identity_sub.add_parser("link")
    identity_link.add_argument("--user", required=True)
    identity_link.add_argument("--issuer", required=True)
    identity_link.add_argument("--subject", required=True)
    identity_link.add_argument("--email")
    identity_list = identity_sub.add_parser("list")
    identity_list.add_argument("--user")
    identity_unlink = identity_sub.add_parser("unlink")
    identity_unlink.add_argument("--identity", required=True)

    member = sub.add_parser("member", help="memberships e roles com escopo")
    member_sub = member.add_subparsers(dest="member_command", required=True)
    member_add = member_sub.add_parser("add")
    member_add.add_argument("--organization", required=True)
    member_add.add_argument("--user", required=True)
    member_add.add_argument(
        "--role",
        required=True,
        choices=["OWNER", "ADMIN", "ANALYST", "OPERATOR", "VIEWER", "INTEGRATION_MANAGER", "BILLING"],
    )
    member_add.add_argument("--workspace")
    member_add.add_argument("--project")
    member_list = member_sub.add_parser("list")
    member_list.add_argument("--organization")
    member_list.add_argument("--user")

    scope = sub.add_parser("scope", help="escopos Property/Environment vinculados a um AUD")
    scope_sub = scope.add_subparsers(dest="scope_command", required=True)
    scope_list = scope_sub.add_parser("list")
    scope_list.add_argument("--audit", required=True)

    data = sub.add_parser("data", help="governança dos bancos/índices locais")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    data_sub.add_parser("status")
    return parser


def _custom_main(argv: list[str], audits_root: str, platform_db: str | None) -> int:
    args = _custom_parser().parse_args(argv)
    try:
        config = resolve_platform_database_config(audits_root=audits_root, platform_db=platform_db)
        if args.canonical_command == "database":
            if config.backend == "sqlite":
                if args.database_command == "migrate":
                    raise ValueError(
                        "explicit 'platform database migrate' is PostgreSQL-only; SQLite schema remains managed by the local store"
                    )
                _json({
                    "backend": "sqlite",
                    "database": config.display,
                    "state": "LOCAL_DEFAULT",
                    "migration_required": False,
                })
                return 0
            assert config.database_url is not None
            if args.database_command == "migrate":
                status, applied = migrate_postgres(config.database_url)
                _json({**status.as_dict(), "backend": "postgresql", "applied_migrations": list(applied)})
            else:
                status = postgres_schema_status(config.database_url)
                _json({**status.as_dict(), "backend": "postgresql", "migration_required": status.state != "CURRENT"})
            return 0

        with open_platform_store(audits_root=audits_root, platform_db=platform_db) as store:
            if args.canonical_command == "user":
                if args.user_command == "add":
                    _json(asdict(store.get_or_create_user(args.name, email=args.email)))
                else:
                    _json(store.list_users())
                return 0
            if args.canonical_command == "identity":
                directory = IdentityDirectory(store)
                if args.identity_command == "link":
                    _json(directory.link(
                        user_id=args.user,
                        issuer=args.issuer,
                        subject=args.subject,
                        email=args.email,
                    ).as_dict())
                elif args.identity_command == "list":
                    _json([item.as_dict() for item in directory.list(user_id=args.user)])
                else:
                    if not directory.unlink(args.identity):
                        raise KeyError(f"external identity not found: {args.identity}")
                    _json({"external_identity_id": args.identity, "unlinked": True})
                return 0
            if args.canonical_command == "member":
                if args.member_command == "add":
                    membership_id = store.add_membership(
                        args.organization,
                        args.user,
                        args.role,
                        workspace_id=args.workspace,
                        project_id=args.project,
                    )
                    _json({"membership_id": membership_id})
                else:
                    _json(store.list_memberships(organization_id=args.organization, user_id=args.user))
                return 0
            if args.canonical_command == "scope":
                _json(store.audit_scopes(args.audit))
                return 0
            if args.canonical_command == "data":
                _json({**store.data_governance_status(), "counts": store.counts()})
                return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"RASAi platform error: {exc}", file=sys.stderr)
        return 2
    return 2


def main(argv: list[str] | None = None) -> int:
    effective = list(argv or [])
    audits_root, platform_db, remaining = _global_options(effective)
    try:
        config = resolve_platform_database_config(audits_root=audits_root, platform_db=platform_db)
    except (ValueError, RuntimeError) as exc:
        print(f"RASAi platform error: {exc}", file=sys.stderr)
        return 2
    if remaining and remaining[0] in {"database", "user", "identity", "member", "scope", "data"}:
        return _custom_main(remaining, audits_root, platform_db)
    if config.backend == "sqlite":
        _cli.PlatformStore = SecurePlatformStore  # type: ignore[attr-defined]
    else:
        # The broad legacy parser still derives a SQLite-shaped path before store
        # construction. Ignore that derived path when PostgreSQL is explicitly selected;
        # authority comes only from RASAI_PLATFORM_DATABASE_URL.
        _cli.PlatformStore = lambda _database: open_platform_store(  # type: ignore[attr-defined]
            audits_root=audits_root,
            backend="postgresql",
        )
    return _cli.main(effective)
