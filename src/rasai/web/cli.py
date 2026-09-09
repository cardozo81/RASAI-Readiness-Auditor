"""Explicit launcher for the optional RASAi ASGI API."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .app import ApiSettings, create_app
from .auth import ApiAuthSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rasai api", description="Run the optional RASAi control-plane API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--audits-root", default="audits")
    parser.add_argument("--auth-mode", choices=("deny", "trusted-header"), default=None)
    parser.add_argument("--trusted-user-header", default=None)
    parser.add_argument("--docs", action="store_true", help="Expose /docs and /openapi.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("RASAi web dependencies are not installed; install with: pip install -e '.[web]'") from exc

    settings = ApiSettings.from_environment()
    auth = settings.auth
    if args.auth_mode is not None:
        auth = replace(auth, mode=args.auth_mode)
    if args.trusted_user_header is not None:
        header = args.trusted_user_header.strip().casefold()
        if not header or any(character.isspace() for character in header):
            raise SystemExit("--trusted-user-header must be a valid non-empty header name")
        auth = ApiAuthSettings(mode=auth.mode, trusted_user_header=header)
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
