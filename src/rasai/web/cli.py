"""Explicit launcher for the optional RASAi ASGI API and SaaS pilot UI."""
from __future__ import annotations

import argparse
from dataclasses import replace
import ipaddress
from pathlib import Path
from typing import Sequence

from .app import ApiSettings
from .auth import ApiAuthSettings
from .pilot_app import create_app


def _is_loopback_host(value: str) -> bool:
    host = value.strip().casefold()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai api",
        description="Run the optional RASAi control-plane API and zero-build SaaS pilot UI",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--audits-root", default="audits")
    parser.add_argument("--auth-mode", choices=("deny", "trusted-header", "oidc"), default=None)
    parser.add_argument("--trusted-user-header", default=None)
    parser.add_argument("--docs", action="store_true", help="Expose /docs and /openapi.json")
    parser.add_argument(
        "--allow-public-bind",
        action="store_true",
        help="explicitly acknowledge binding beyond localhost; use only behind trusted TLS/auth infrastructure",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if not _is_loopback_host(args.host) and not args.allow_public_bind:
        raise SystemExit(
            "non-loopback API bind requires --allow-public-bind and trusted TLS/auth deployment controls"
        )
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("RASAi web dependencies are not installed; install with: pip install -e '.[web]'") from exc

    settings = ApiSettings.from_environment()
    auth = settings.auth
    if args.auth_mode is not None and args.auth_mode != auth.mode:
        if args.auth_mode == "oidc":
            # Re-read the complete OIDC contract from environment instead of
            # constructing a partially configured auth object from CLI flags.
            previous = __import__("os").environ.get("RASAI_API_AUTH_MODE")
            __import__("os").environ["RASAI_API_AUTH_MODE"] = "oidc"
            try:
                auth = ApiAuthSettings.from_environment()
            finally:
                if previous is None:
                    __import__("os").environ.pop("RASAI_API_AUTH_MODE", None)
                else:
                    __import__("os").environ["RASAI_API_AUTH_MODE"] = previous
        else:
            auth = replace(auth, mode=args.auth_mode, oidc=None)
    if args.trusted_user_header is not None:
        header = args.trusted_user_header.strip().casefold()
        if not header or any(character.isspace() for character in header):
            raise SystemExit("--trusted-user-header must be a valid non-empty header name")
        auth = replace(auth, trusted_user_header=header)
    settings = ApiSettings(
        audits_root=Path(args.audits_root),
        docs_enabled=bool(args.docs or settings.docs_enabled),
        auth=auth,
    )
    application = create_app(settings)
    uvicorn.run(application, host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
