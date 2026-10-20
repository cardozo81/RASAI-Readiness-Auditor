"""Evidence-only HTML projection of trusted offline claim-review batch (#603)."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


_STATES = {
    "CLAIM_CORROBORATED": "Corroboração documental por revisor autenticado",
    "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE": (
        "Contradição documental apontada por revisor autenticado"
    ),
    "CLAIM_UNVERIFIED_EXTERNAL": (
        "Não validado contra documentação oficial vigente"
    ),
}


def render_claim_review_batch_html(projection: Mapping[str, Any]) -> str:
    def e(value: object) -> str:
        return escape(str(value) if value is not None else "N/D", quote=True)

    admitted = (
        isinstance(projection, Mapping)
        and projection.get("contract") == "RASAI-CLAIM-REVIEW-BATCH-603-001"
        and projection.get("status") == "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
        and isinstance(projection.get("claims"), list)
        and type(projection.get("claims_total")) is int
        and projection["claims_total"] == len(projection["claims"])
        and len(projection["claims"]) <= 50
    )
    rows: list[str] = []
    if admitted:
        for claim in projection["claims"]:
            if not isinstance(claim, Mapping):
                admitted = False
                break
            state = claim.get("state")
            if state not in _STATES:
                admitted = False
                break
            authenticated = (
                state != "CLAIM_UNVERIFIED_EXTERNAL"
                and claim.get("source_version_verified") is True
            )
            provenance = (
                "Versão: " + e(claim.get("document_version"))
                + "; Emissor declarado: " + e(claim.get("issuer_asserted_by_trusted_reviewer"))
                + "; Produto: " + e(claim.get("product_scope"))
                + "; Fonte atestada: " + e(claim.get("source_url_attested"))
                + "; Coleta: " + e(claim.get("collected_on"))
                + "; Revisão: " + e(claim.get("reviewed_on"))
                + "; Recibo: " + e(claim.get("reviewer_receipt_id"))
                if authenticated else "N/D - não existe fonte primária autenticada"
            )
            binding = claim.get("audit_binding")
            link = (
                e(binding.get("status")) + "; SNP: "
                + e(binding.get("snapshot_id"))
                + "; SHA-256 texto: " + e(binding.get("main_content_sha256"))
                if isinstance(binding, Mapping)
                and projection.get("audit_binding_mode")
                == "OBSERVATIONAL_BINDING_CHECKED"
                else "N/D — vínculo com AUD física não solicitado"
            )
            rows.append(
                "<tr><td>" + e(claim.get("claim_id")) + "</td><td>"
                + e(_STATES[state]) + "</td><td>"
                + provenance + "</td><td>" + link + "</td></tr>"
            )
    if not admitted:
        rows = []
    body = (
        "<table><thead><tr><th>Identificador da alegação</th>"
        "<th>Verificação documental</th><th>Fonte e versão</th>"
        "<th>Vínculo textual à captura AUD</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        if admitted else
        "<p>N/D - manifesto, recibos ou conjunto de alegações não comprovados.</p>"
    )
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Revisão documental consultiva</title><style>"
        "body{font:16px system-ui,sans-serif;color:#203147;max-width:1000px;"
        "margin:auto;padding:24px}table{width:100%;border-collapse:collapse}"
        "td,th{border-bottom:1px solid #dbe4ee;padding:10px;text-align:left;"
        "vertical-align:top;overflow-wrap:anywhere}"
        "</style></head><body><h1>Revisão documental consultiva</h1>"
        "<p>AUD (identidade declarada no manifesto; vínculo literal verificável "
        "por captura somente quando o modo físico foi solicitado e aprovado): " +
        e(projection.get("audit_id_operator_label_only") if admitted else "N/D")
        + "</p>" + (
            "<p>Vínculo físico consultivo: " +
            e(projection.get("audit_binding_mode") if admitted else "NOT_VERIFIED")
            + ". Hash do SQLite AUD: " +
            e(projection.get("audit_db_sha256") if admitted else None)
            + ". Correspondência literal não autentica o conteúdo, a fonte oficial "
            "ou o momento da sessão de navegador.</p>"
        ) + body
        + "<p>Atestado documental independente não equivale a conformidade "
        "regulatória ou jurídica. Contradição indicada por revisor não é "
        "infração verificada. Texto comercial não confirmado não é afirmação "
        "falsa. Nenhum dado desta apresentação modifica CAT-03, SARI ou "
        "a auditoria original.</p></body></html>"
    )


__all__ = ["render_claim_review_batch_html"]
