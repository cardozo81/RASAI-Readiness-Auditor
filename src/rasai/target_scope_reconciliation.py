"""Single-AUD-target provenance checks for independent Search inputs (no I/O)."""
from __future__ import annotations

from typing import Any

from rasai.url_utils import normalize_url, normalized_origin


def canonical_target(value: object) -> str:
    try:
        return normalize_url(str(value or ""))
    except (TypeError, ValueError, UnicodeError):
        return ""


def scope_state(target: object, bound_target: object, *, requested: bool) -> str:
    if not requested:
        return "NOT_REQUESTED"
    current = canonical_target(target)
    if not current:
        return "TARGET_INVALID"
    bound = canonical_target(bound_target)
    if not bound:
        return "SOURCE_UNVERIFIED"
    if bound == current:
        return "SAME_TARGET"
    return "ORIGIN_CHANGED" if normalized_origin(bound) != normalized_origin(current) else "PATH_CHANGED"


def consumer_status(state: Any, consumer: str) -> str:
    if consumer == "SERP":
        bound = getattr(state, "search_scope_target", "")
        requested = bool(getattr(state, "search_queries", ()))
    elif consumer == "PERPLEXITY":
        bound = getattr(state, "perplexity_scope_target", "")
        requested = bool(getattr(state, "perplexity_queries", ()) or getattr(state, "perplexity_draft_queries", ()))
    else:
        raise ValueError("invalid consumer")
    return scope_state(getattr(state, "target", ""), bound, requested=requested)


def bind(state: Any, consumer: str) -> None:
    attr = {"SERP": "search_scope_target", "PERPLEXITY": "perplexity_scope_target"}[consumer]
    setattr(state, attr, canonical_target(getattr(state, "target", "")))


def scope_preflight(target: str, effective: str) -> None:
    if not canonical_target(target) or canonical_target(target) != canonical_target(effective):
        raise ValueError("TARGET_SCOPE_MISMATCH")


def notices(state: Any) -> tuple[str, ...]:
    labels = {
        "ORIGIN_CHANGED": "origem diferente do alvo atual",
        "PATH_CHANGED": "caminho ou query da URL alterado",
        "SOURCE_UNVERIFIED": "proveniência dos termos não verificada (INI legado)",
    }
    return tuple(f"{source}: {labels[result]}" for source in ("SERP", "PERPLEXITY")
                 if (result := consumer_status(state, source)) in labels)


def must_review(state: Any) -> bool:
    return any(consumer_status(state, source) == "ORIGIN_CHANGED"
               for source in ("SERP", "PERPLEXITY"))


def execution_matrix(state: Any, environment: dict[str, str] | None = None) -> tuple[tuple[str, str, str], ...]:
    """Read-only catalog/consumer source matrix, never a replacement for the URL."""
    from rasai.gsc_scope import assess_gsc_target
    import os

    target = canonical_target(getattr(state, "target", ""))
    if target:
        try:
            gsc = assess_gsc_target(target, os.environ if environment is None else environment)
            gsc_status = str(gsc.state)
        except (TypeError, ValueError):
            gsc_status = "NOT_VERIFIABLE"
    else:
        gsc_status = "TARGET_INVALID"
    return (
        ("CAT-01/02/03/04/06/07/08/09/10", "HERDADA", target or "URL NÃO CONFIGURADA"),
        ("CAT-05 / SERP", "TERMOS INDEPENDENTES", consumer_status(state, "SERP")),
        ("CAT-05 / PERPLEXITY", "CONSENTIMENTO INDEPENDENTE", consumer_status(state, "PERPLEXITY")),
        ("GSC", "PROPRIEDADE EXTERNA", gsc_status),
    )
