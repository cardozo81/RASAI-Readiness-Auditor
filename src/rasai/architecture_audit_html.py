"""#646 F3: advisory architecture report, not an execution profile selector."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from rasai.architecture_audit_projection import VERSION

ARCH = {
    "STATIC_OR_SSR": "Estática ou renderização no servidor (sem diferenciação)",
    "HYDRATED": "Com hidratação observada",
    "CSR_SPA": "SPA, com renderização no cliente",
    "MIXED": "Arquitetura mista",
    "UNKNOWN": "Não determinada",
}
MODES = {
    "AUTO": "AUTO (conforme descoberta observada neste snapshot)",
    "DECLARED": "Declarada no plano congelado (não substitui a arquitetura observada)",
    "UNFORCED": "Sem forçar arquitetura (não herda perfil)",
}
SOURCES = {
    "AUTO_DISCOVERY": "Arquitetura identificada na captura desta auditoria",
    "USER_DECLARED": "Escolha explícita congelada na AUD",
    "UNFORCED": "Nenhuma classe foi aplicada",
}
REASONS = {
    "UNFORCED": "Opção sem forçar; apenas contexto observado",
    "UNKNOWN_OBSERVED_ARCHITECTURE": "A observação da arquitetura não comprovou uma classe concreta",
    "MISSING_CONFLICTING_OR_INVALID_EVIDENCE": (
        "Evidência ausente, conflitante ou identidade física inconclusiva"
    ),
    "CONSUMER_NOT_APPROVED": "Este consumidor não pode herdar arquitetura",
    "OBSERVATION_NOT_AVAILABLE_BEFORE_COLLECTION": (
        "Descoberta ainda não existia antes da coleta"
    ),
}


def _esc(value: object) -> str:
    return escape(str(value) if value is not None else "N/D", quote=True)


def _public_url(value: object) -> str:
    """Show scheme/host/path for provenance, never query, fragment or userinfo."""
    if not isinstance(value, str) or not value:
        return "N/D"
    try:
        parts = urlsplit(value)
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host:
            return "URL não verificável"
        port = parts.port
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            return "URL não verificável"
        authority = ("[" + host + "]" if ":" in host else host)
        if port is not None:
            authority += ":" + str(port)
        return urlunsplit((
            parts.scheme, authority, parts.path,
            "[parâmetros omitidos]" if parts.query else "", "",
        ))
    except (TypeError, ValueError, UnicodeError):
        return "URL não verificável"


def architecture_audit_context_html(projection: Mapping[str, Any]) -> str:
    """Escape URL/ID literal and protect technical tokens from humanization."""
    if (not isinstance(projection, Mapping)
            or projection.get("contract") != VERSION
            or projection.get("status") != "ADVISORY_OBSERVED"
            or not isinstance(projection.get("snapshots"), list)
            or not 0 < len(projection["snapshots"]) <= 100):
        return (
            "<div class='notice' data-contract='ARCH-CONTEXT-646'>"
            "Arquitetura por snapshot: N/D (origem selada ou identidade da captura "
            "insuficiente). Não aplicada a índices, coletores ou perfis.</div>"
        )
    table = []
    for row in projection["snapshots"]:
        if not isinstance(row, Mapping):
            return "<div class='notice'>Arquitetura por snapshot: N/D.</div>"
        expected = row.get("observed_architecture")
        declared = row.get("declared_architecture")
        effective = row.get("effective_architecture")
        reason = row.get("abstention_reason")
        explanation = (
            "Divergência entre escolha declarada e arquitetura observada; não corrigida automaticamente."
            if row.get("discrepancy") is True
            else REASONS.get(reason, "Somente leitura consultiva, sem retroação")
        )
        # A different final URL is factual provenance of the M6 snapshot,
        # not proof of a particular redirect, certificate, origin or crawler.
        if row.get("final_target_differs_from_requested") is True:
            explanation += (
                " URLs solicitada e final diferentes no mesmo snapshot; "
                "não extrapolar a outros destinos nem inferir causa."
            )
        items = (
            "<code>" + _esc(row.get("snapshot_id")) + "</code>",
            "<code>" + _esc(row.get("page_id")) + "</code>",
            "<code>" + _esc(row.get("device")) + "</code>",
            "<code>" + _esc(_public_url(row.get("requested_url"))) + "</code>",
            "<code>" + _esc(_public_url(row.get("final_url"))) + "</code>",
            _esc(ARCH.get(expected, ARCH["UNKNOWN"])),
            _esc(ARCH.get(declared, "Não informada no plano")),
            _esc(ARCH.get(effective, "N/D (não aplicada)")),
            _esc(SOURCES.get(row.get("source"), "Origem não comprovada")),
            _esc(explanation),
        )
        table.append("<tr>" + "".join("<td>" + value + "</td>" for value in items)
                     + "</tr>")
    return (
        "<div data-contract='ARCH-CONTEXT-646'>"
        "<p><strong>Modo congelado:</strong> "
        + _esc(MODES.get(projection.get("selection"), "Não comprovado"))
        + ". <strong>Origem do modo:</strong> "
        + _esc({
            "SNAPSHOT": "Configuração selada da AUD",
            "LEGACY_ABSENT": "Ausente no plano legado",
            "UNVERIFIED_OR_LEGACY": "Plano congelado não verificável",
        }.get(projection.get("choice_origin"), "Não comprovada"))
        + ".</p>"
        "<p>A arquitetura identificada durante a coleta, a arquitetura declarada "
        "no planejamento e a arquitetura considerada <strong>somente nesta análise "
        "consultiva</strong> são conceitos distintos. Esta avaliação não altera "
        "amostras já registradas, configuração do Apdex de navegação ou de "
        "experiência, índices de prontidão e GEO, análises de IA nem parâmetros "
        "externos do Dynatrace. Sem correspondência inequívoca entre URL, "
        "dispositivo e captura, o resultado é N/D. As URLs são exibidas sem "
        "credenciais, parâmetros de consulta ou fragmentos; a diferença entre "
        "destinos não comprova, por si só, o mecanismo de redirecionamento.</p>"
        "<details><summary>Ver contextos físicos de arquitetura ("
        + str(len(table))
        + " captura(s))</summary><div class='table-wrap'><table><thead><tr>"
        "<th>Snapshot</th><th>Página</th><th>Dispositivo</th>"
        "<th>URL solicitada</th><th>URL final observada</th>"
        "<th>Arquitetura observada</th><th>Declarada</th>"
        "<th>Efetiva nesta análise</th><th>Fonte</th><th>Limite</th>"
        "</tr></thead><tbody>" + "".join(table)
        + "</tbody></table></div></details>"
        "<p class='muted'>Classificação estática/SSR não diferencia "
        "estático de SSR. Controles sem evidência física não são resolvidos "
        "por preferências atuais do operador.</p></div>"
    )


__all__ = ["architecture_audit_context_html"]
