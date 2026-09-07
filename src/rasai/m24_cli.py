"""CLI contract for M24 Crawling, Discovery & AI Access."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os

TECHNICAL_AI_ENV = "RASAI_AI_TECHNICAL_REMEDIATION"


@dataclass(frozen=True, slots=True)
class M24Config:
    technical_ai: bool = False


def register_m24_arguments(audit_parser: argparse.ArgumentParser) -> None:
    audit_parser.add_argument(
        "--ai-technical-remediation",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "enable evidence-bound AI explanation/remediation for M24 crawling/discovery "
            f"diagnostics; default OFF or {TECHNICAL_AI_ENV}"
        ),
    )


def configured_m24(args: argparse.Namespace) -> M24Config:
    cli_value = getattr(args, "ai_technical_remediation", None)
    if cli_value is not None:
        return M24Config(technical_ai=bool(cli_value))
    raw = os.environ.get(TECHNICAL_AI_ENV)
    if raw is None or not raw.strip():
        return M24Config(False)
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return M24Config(True)
    if normalized in {"0", "false", "no", "off"}:
        return M24Config(False)
    raise ValueError(
        f"{TECHNICAL_AI_ENV} must be one of: true/false, 1/0, yes/no, on/off"
    )
