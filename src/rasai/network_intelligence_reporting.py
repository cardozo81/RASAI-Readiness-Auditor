"""Read-only, evidence-bound consultation panel for network.html.

No scoring, network access, AI execution, schema changes or AUD modification.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from rasai.catalog_source_dependencies import record_source_dependency
from rasai.network_intelligence import build_network_assessment
from rasai.network_intelligence_ai import read_network_ai


_CONFIDENCE = {
    "HIGH": "Alta para a observação pontual",
    "MEDIUM": "Moderada para o escopo registrado",
    "LOW": "Limitada",
}
_OVERALL = {
    "MODERATE": "Moderada para comparar as amostras",
    "LIMITED": "Limitada para uma conclusão geral",
}


def _paragraph(label: str, value: str) -> str:
    return "<p><strong>" + escape(label) + ":</strong> " + escape(value) + "</p>"


def network_intelligence_section(workspace: str | Path, audit_id: str) -> str:
    """Present only validated records; source dependency invalidates stale catalog."""
    root = Path(workspace)
    record_source_dependency(root / "artifacts" / "network" / "intelligence")
    try:
        assessment = build_network_assessment(root, audit_id)
    except (ValueError, OSError, TypeError):
        return (
            "<section class='panel'><h2>Diagnóstico de Rede e Conectividade</h2>"
            "<p>Não foi possível validar as evidências disponíveis para análise. "
            "Nenhuma conclusão técnica foi promovida.</p></section>"
        )

    counts = assessment["coverage"]
    out = [
        "<section class='panel network-intelligence'>",
        "<h2>Diagnóstico de Rede e Conectividade</h2>",
        "<p>Análise consultiva fundamentada exclusivamente nas observações "
        "persistidas. Não altera pontuações nem executa novas sondagens.</p>",
        _paragraph("Confiabilidade da conclusão geral",
                   _OVERALL[assessment["confidence_scope"]]),
        _paragraph("Por que essa confiabilidade",
                   assessment["confidence_explanation"]),
        "<p><strong>Cobertura:</strong> "
        + str(counts["audit_captures"]) + " captura(s) da auditoria; "
        + str(counts["authorized_probes"]) + " medição(ões) complementar(es) "
        "autorizada(s).</p>",
        "<h3>Conclusões sustentadas e próximos passos</h3>",
    ]
    for finding in assessment["findings"]:
        refs = ", ".join(finding["evidence_refs"]) or "Nenhuma medição suficiente"
        out.extend([
            "<article class='network-insight'>",
            "<h4>" + escape(finding["title"]) + "</h4>",
            _paragraph("Conclusão", finding["conclusion"]),
            _paragraph("Confiabilidade", _CONFIDENCE[finding["confidence"]]),
            _paragraph("Evidências", refs),
            _paragraph("Limitação", finding["limitation"]),
            _paragraph("Ação recomendada", finding["recommendation"]),
            _paragraph("Como validar", finding["validation"]),
            "</article>",
        ])
    packet = read_network_ai(root, assessment)
    if packet:
        analysis = packet["analysis"]
        out.extend([
            "<h3>Interpretação complementar por IA</h3>",
            "<p>Texto gerado por IA, restrito às evidências identificadas. "
            "Não é constatação física independente e requer validação humana.</p>",
            _paragraph("Provedor e modelo",
                       packet["provider"] + " / " + packet["model"]),
            _paragraph("Síntese consultiva", analysis["summary"]),
        ])
        for insight in analysis["insights"]:
            out.extend([
                "<article class='network-ai-insight'>",
                "<h4>Interpretação associada: " + escape(insight["finding_id"]) + "</h4>",
                _paragraph("Interpretação", insight["interpretation"]),
                _paragraph("Confiabilidade da interpretação",
                           _CONFIDENCE[insight["confidence"]]),
                _paragraph("Evidências vinculadas", ", ".join(insight["evidence_refs"])),
                _paragraph("Limitação", insight["limitation"]),
                _paragraph("Recomendação", insight["recommendation"]),
                _paragraph("Validação", insight["validation"]),
                "</article>",
            ])
    else:
        out.append(
            "<p><strong>IA complementar:</strong> não executada ou sem análise "
            "válida para as evidências atuais. A análise consultiva baseada "
            "em regras permanece disponível sem provedor externo.</p>"
        )
    out.extend([
        "<p><strong>Limite do diagnóstico:</strong> "
        "medidas pontuais não demonstram, isoladamente, gargalo, causa, "
        "disponibilidade global, localização física ou impacto em SEO e GEO.</p>",
        "</section>",
    ])
    return "".join(out)
