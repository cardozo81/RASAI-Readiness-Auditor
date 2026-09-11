"""CLI for provider discovery and credential onboarding metadata."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from rasai.provider_onboarding import (
    ProviderOnboardingRecord,
    find_provider_onboarding,
    provider_onboarding_integrity_issues,
    provider_onboarding_records,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai providers",
        description=(
            "Lista providers de IA/SERP, variável de credencial, status configurado, "
            "URL oficial de obtenção da chave e metadados operacionais sem exibir secrets."
        ),
    )
    parser.add_argument(
        "--kind",
        choices=("all", "ai", "serp"),
        default="all",
        help="filtra o catálogo por tipo de provider",
    )
    parser.add_argument(
        "--provider",
        help="filtra por ID ou alias (ex.: copilot, github-copilot, zenserp)",
    )
    parser.add_argument(
        "--configured-only",
        action="store_true",
        help="mostra somente providers cuja variável de credencial está definida",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emite JSON machine-readable; nenhum valor de credencial é incluído",
    )
    return parser


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "sim" if value else "não"


def _render_human(records: tuple[ProviderOnboardingRecord, ...]) -> None:
    for index, item in enumerate(records):
        if index:
            print()
        print(f"[{item.kind.upper()}] {item.id} - {item.display_name}")
        if item.aliases:
            print(f"Aliases         : {', '.join(item.aliases)}")
        print(f"Credencial      : {item.credential_env} [{'SET' if item.configured else 'NÃO CONFIGURADA'}]")
        print(f"Obter/login     : {item.credential_url}")
        print(f"Documentação    : {item.documentation_url}")
        if item.kind == "ai":
            print(f"Modelo público  : {item.default_model or '-'}")
            print(f"Reasoning       : {', '.join(item.reasoning_values) if item.reasoning_values else '-'}")
            print(f"Qualificação    : {item.qualification or '-'}")
            print(f"AUTO elegível   : {_yes_no(item.auto_eligible)}")
            print(f"Explicit-only   : {_yes_no(item.explicit_only)}")
        else:
            print(f"Engine          : {item.engine or '-'}")
            print(f"Free tier       : {_yes_no(item.free_tier)}")
            if item.free_tier_note:
                print(f"Franquia/nota   : {item.free_tier_note}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    issues = provider_onboarding_integrity_issues()
    if issues:
        for issue in issues:
            print(f"PROVIDER_CATALOG_ERROR: {issue}", file=sys.stderr)
        return 3

    if args.provider:
        records = find_provider_onboarding(args.provider, kind=args.kind)
        if args.configured_only:
            records = tuple(item for item in records if item.configured)
        if not records:
            print(
                f"provider não encontrado/configurado para o filtro: {args.provider}",
                file=sys.stderr,
            )
            return 2
    else:
        records = provider_onboarding_records(
            kind=args.kind,
            configured_only=args.configured_only,
        )

    if args.json:
        print(
            json.dumps(
                [item.public_dict() for item in records],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _render_human(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
