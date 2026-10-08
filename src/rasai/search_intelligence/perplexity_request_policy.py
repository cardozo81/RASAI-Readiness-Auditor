"""Search API request options resolved from canonical, nonsecret RASAi settings.

No network access, no implicit queries, no SERP engine coupling and no secrets.
All optional filters are opt-in; the consumer validates again at the transport edge.
"""
from __future__ import annotations

from datetime import datetime
import os
import re
from typing import Any, Mapping

PREFIX = "RASAI_PERPLEXITY_"
OPTION_FIELDS = {
    "MAX_RESULTS": "max_results",
    "COUNTRY": "country",
    "SEARCH_LANGUAGE_FILTER": "search_language_filter",
    "SEARCH_DOMAIN_FILTER": "search_domain_filter",
    "SEARCH_RECENCY_FILTER": "search_recency_filter",
    "SEARCH_AFTER_DATE": "search_after_date_filter",
    "SEARCH_BEFORE_DATE": "search_before_date_filter",
    "LAST_UPDATED_AFTER": "last_updated_after_filter",
    "LAST_UPDATED_BEFORE": "last_updated_before_filter",
    "MAX_CONTENT_UNITS": "max_tokens",
    "MAX_CONTENT_UNITS_PER_PAGE": "max_tokens_per_page",
}
VALID_OPTION_FIELDS = frozenset(OPTION_FIELDS.values())
_DATE_FIELDS = frozenset({
    "search_after_date_filter", "search_before_date_filter",
    "last_updated_after_filter", "last_updated_before_filter",
})
_POSITIVE_FIELDS = frozenset({"max_results", "max_tokens", "max_tokens_per_page"})
_LIST_FIELDS = frozenset({"search_language_filter", "search_domain_filter"})
_RECENCY = frozenset({"hour", "day", "week", "month", "year"})
_DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _tokens(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = re.split(r"[,;]", value)
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ValueError("Perplexity filtro requer lista ou texto separado por vírgulas")
    items = [str(item).strip().casefold() for item in items]
    if not all(items):
        raise ValueError("Perplexity filtro não aceita entradas vazias")
    return tuple(dict.fromkeys(items))


def validate_request_options(values: Mapping[str, Any], *, search_type: str = "web") -> dict[str, Any]:
    """Normalize all supplied provider options; unknown options are rejected."""
    if str(search_type).casefold() not in {"web", "fast"}:
        raise ValueError("Perplexity Search API suporta WEB ou FAST neste contrato")
    unknown = set(values) - VALID_OPTION_FIELDS
    if unknown:
        raise ValueError("Parâmetro Perplexity desconhecido: " + ", ".join(sorted(unknown)))

    result: dict[str, Any] = {}
    for key, raw in values.items():
        if raw is None or raw == "":
            continue
        if key in _POSITIVE_FIELDS:
            if isinstance(raw, bool):
                raise ValueError(f"{key}: use inteiro válido")
            try:
                value = int(str(raw))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{key}: use inteiro válido") from exc
            upper = 20 if key == "max_results" else 1000000
            if value < 1 or value > upper:
                raise ValueError(f"{key}: use inteiro entre 1 e {upper}")
            result[key] = value
        elif key == "country":
            value = str(raw).strip().upper()
            if not re.fullmatch(r"[A-Z]{2}", value):
                raise ValueError("country: use país ISO 3166-1 alfa-2 (ex.: BR)")
            result[key] = value
        elif key in _LIST_FIELDS:
            tokens = _tokens(raw)
            if len(tokens) > 20:
                raise ValueError(f"{key}: máximo de 20 entradas")
            if key == "search_language_filter":
                if any(not re.fullmatch(r"[a-z]{2}", item) for item in tokens):
                    raise ValueError("search_language_filter: códigos ISO 639-1 de duas letras")
            else:
                if any(not _DOMAIN.fullmatch(item) for item in tokens):
                    raise ValueError("search_domain_filter: domínios sem URL, caminho ou wildcard")
            result[key] = list(tokens)
        elif key == "search_recency_filter":
            value = str(raw).strip().casefold()
            if value not in _RECENCY:
                raise ValueError("search_recency_filter: use hour, day, week, month ou year")
            result[key] = value
        elif key in _DATE_FIELDS:
            value = str(raw).strip()
            try:
                parsed = datetime.strptime(value, "%m/%d/%Y")
            except ValueError as exc:
                raise ValueError(f"{key}: use MM/DD/YYYY com data válida") from exc
            if parsed.strftime("%m/%d/%Y") != value:
                raise ValueError(f"{key}: use MM/DD/YYYY")
            result[key] = value

    for after, before in (
        ("search_after_date_filter", "search_before_date_filter"),
        ("last_updated_after_filter", "last_updated_before_filter"),
    ):
        if after in result and before in result:
            if datetime.strptime(result[after], "%m/%d/%Y") > datetime.strptime(result[before], "%m/%d/%Y"):
                raise ValueError(f"{after}: data posterior a {before}")
    return result


def validate_console_override(name: str, value: str) -> str:
    """Same contract for console editors and the actual outbound request."""
    suffix = name.removeprefix(PREFIX)
    if suffix not in OPTION_FIELDS or name != PREFIX + suffix:
        raise ValueError("Opção Perplexity não registrada")
    field = OPTION_FIELDS[suffix]
    normalized = validate_request_options({field: value})
    if field not in normalized:
        raise ValueError(f"{name}: informe um valor ou remova o override")
    validated = normalized[field]
    return ",".join(validated) if isinstance(validated, list) else str(validated)


def resolve_request_options(
    env: Mapping[str, str] | None = None,
    *,
    explicit_brazil: bool = False,
    search_type: str = "web",
) -> dict[str, Any]:
    """AUD-explicit BR wins over optional integration country, then defaults.

    No market is inferred from URL TLD, IP or site content; only the caller's
    explicit SERP region and canonical integration overrides are consulted.
    """
    values = os.environ if env is None else env
    selected = {
        field: raw
        for suffix, field in OPTION_FIELDS.items()
        if (raw := str(values.get(PREFIX + suffix) or "").strip())
    }
    selected.setdefault("max_results", 10)
    if explicit_brazil:
        selected["country"] = "BR"
        selected.setdefault("search_language_filter", ("pt",))
    return validate_request_options(selected, search_type=search_type)
