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


def propagate_target(state: Any, value: str) -> bool:
    """Set the single effective URL and its purely derived display state.

    Search query provenance and authenticated GSC properties are independent
    operator inputs. Never silently re-bind them to conceal stale scopes.
    """
    old = canonical_target(getattr(state, "target", ""))
    supplied = str(value or "").strip()
    current = canonical_target(supplied) if supplied else ""
    if supplied and not current:
        raise ValueError("URL inválida para a auditoria")
    state.target = current
    state.current_url = current or "-"
    # A provenance marker with no corresponding terms is not meaningful.
    # The next explicit query edit will bind its actual target as usual.
    if old != current and not tuple(getattr(state, "search_queries", ()) or ()) and hasattr(state, "search_scope_target"):
        state.search_scope_target = current
    if not (
        tuple(getattr(state, "perplexity_queries", ()) or ())
        or tuple(getattr(state, "perplexity_draft_queries", ()) or ())
    ) and old != current and hasattr(state, "perplexity_scope_target"):
        state.perplexity_scope_target = current
    return old != current


def adjustment_guidance(consumer: str) -> str:
    """Operator routes, not arbitrary state fields or provider approvals."""
    routes = {
        "SERP": "Preparar auditoria > CAT-05 > 1 > 1 (termos); 2 (localidade)",
        "PERPLEXITY": "Preparar auditoria > CAT-05 > 1 > P > 1 (queries) ou 9 (rascunho)",
        "GSC": "Todas as configurações > 23579716 (propriedade GSC)",
    }
    if consumer not in routes:
        raise ValueError("consumer desconhecido")
    return routes[consumer]


def related_scope_summary(state: Any, *, environment: dict[str, str] | None = None) -> tuple[str, ...]:
    """Non-mutating, no-API summary for the URL editor and persistence prompt."""
    import os
    from rasai.gsc_scope import GSC_SITE_URL_ENV, gsc_property_covers_url
    target = canonical_target(getattr(state, "target", ""))
    if not target:
        return ("URL não informada: os catálogos não possuem alvo efetivo.",)
    lines = (
        f"URL única: {target}",
        "CATs técnicos/Apdex/IA: URL herdada automaticamente do alvo acima.",
        "SERP: domínio derivado da URL; termos/localidade mantidos até revisão.",
        "Perplexity: consultas e consentimento mantidos independentes.",
    )
    output = list(lines)
    for consumer in ("SERP", "PERPLEXITY"):
        result = consumer_status(state, consumer)
        if result in {"ORIGIN_CHANGED", "PATH_CHANGED", "SOURCE_UNVERIFIED"}:
            output.append(
                f"{consumer}: {result}; associado a {bound_url_label(state, consumer)}. "
                f"Ajustar: {adjustment_guidance(consumer)}"
            )
    effective_env = os.environ if environment is None else environment
    configured_gsc = str(effective_env.get(GSC_SITE_URL_ENV) or "").strip()
    if configured_gsc:
        try:
            covers = gsc_property_covers_url(configured_gsc, target)
        except ValueError:
            covers = False
        if not covers:
            output.append(
                f"GSC: propriedade {configured_gsc!r} não cobre o alvo. "
                f"Ajustar: {adjustment_guidance('GSC')}. "
                "A propriedade GSC não pode ser alterada automaticamente."
            )
        else:
            output.append(f"GSC: propriedade {configured_gsc!r} compatível com o endereço.")
    return tuple(output)


def scope_preflight(target: str, effective: str) -> None:
    if not canonical_target(target) or canonical_target(target) != canonical_target(effective):
        raise ValueError("TARGET_SCOPE_MISMATCH")


def bound_url_label(state: Any, consumer: str) -> str:
    """Display only attested operator-provided scope, never infer one from terms."""
    if consumer not in {"SERP", "PERPLEXITY"}:
        raise ValueError("invalid consumer")
    state_name = "search_scope_target" if consumer == "SERP" else "perplexity_scope_target"
    current_status = consumer_status(state, consumer)
    if current_status == "NOT_REQUESTED":
        return "<sem consultas configuradas>"
    bound = canonical_target(getattr(state, state_name, ""))
    return bound or "<URL anterior não registrada no INI>"


def scope_display_rows(state: Any, consumer: str) -> tuple[tuple[str, str], ...]:
    """One canonical source for summaries, editors and consent gates."""
    if consumer not in {"SERP", "PERPLEXITY"}:
        raise ValueError("invalid consumer")
    return (
        ("URL da auditoria", canonical_target(getattr(state, "target", "")) or "<não informada>"),
        ("URL vinculada aos termos" if consumer == "SERP" else "URL vinculada às queries",
         bound_url_label(state, consumer)),
        ("Situação do vínculo", consumer_status(state, consumer)),
    )


def notices(state: Any) -> tuple[str, ...]:
    labels = {
        "ORIGIN_CHANGED": "origem diferente do alvo atual",
        "PATH_CHANGED": "caminho ou query da URL alterado",
        "SOURCE_UNVERIFIED": "proveniência dos termos não verificada (INI legado)",
    }
    return tuple(
        f"{source}: {labels[result]}; "
        f"URL dos termos: {bound_url_label(state, source)}; "
        f"URL atual: {canonical_target(getattr(state, 'target', '')) or '<não informada>'}; "
        f"Ajustar: {adjustment_guidance(source)}"
        for source in ("SERP", "PERPLEXITY")
        if (result := consumer_status(state, source)) in labels
    )


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
        ("SERP / URL DE ORIGEM", "VÍNCULO CONFIGURADO", bound_url_label(state, "SERP")),
        ("PERPLEXITY / URL DE ORIGEM", "VÍNCULO CONFIGURADO", bound_url_label(state, "PERPLEXITY")),
        ("GSC / PROPRIEDADE", "ESCOPO CONFIGURADO",
         str((os.environ if environment is None else environment).get(
             "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", ""
         ) or "").strip() or "<não configurada>"),
    )
