"""User-facing provenance for indicators projected into RASAi reports.

This module classifies methodology only. It does not recalculate persisted
measurements, findings or scores. External links are primary/official sources
and internal heuristics are explicitly labelled as RASAi decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

VERIFIED_ON = "2026-09-08"
PROVENANCE_MARKER = "rasai-indicator-provenance-v1"


@dataclass(frozen=True, slots=True)
class IndicatorProvenance:
    indicator: str
    classification: str
    authority: str
    source_title: str
    source_url: str | None
    external_logic: str
    rasai_logic: str


_CLASS_LABELS = {
    "RAW_OBSERVATION": "Observação coletada",
    "EXTERNAL_STANDARD": "Standard externo",
    "OFFICIAL_PLATFORM_GUIDANCE": "Orientação oficial de plataforma",
    "EXTERNAL_DEFINED_METRIC": "Métrica externa definida",
    "RASAI_HEURISTIC": "Heurística RASAi",
    "OPERATIONAL_TELEMETRY": "Telemetria operacional",
    "AI_DERIVED_ADVISORY": "Análise/sugestão por IA",
}

INDICATORS: tuple[IndicatorProvenance, ...] = (
    IndicatorProvenance(
        "Search & AI Readiness Index (SARI-001)",
        "RASAI_HEURISTIC",
        "RASAi",
        "SCORE-GEO-004 / SCORING_GUIDE",
        None,
        "Não existe score GEO/AEO universal homologado usado por esta saída.",
        "SCORE-GEO-004 calcula dimensões evidence-bound e Overall determinístico de igual peso entre dimensões aplicáveis. Coverage e Confidence qualificam a força da medição; o índice não é probabilidade de ranking ou citação.",
    ),
    IndicatorProvenance(
        "Coverage / Confidence / Consolidation",
        "RASAI_HEURISTIC",
        "RASAi",
        "SCORING_GUIDE",
        None,
        "Não há thresholds GEO universais externos para estes estados.",
        "Coverage mede completude do universo aplicável; Confidence mede força da medição; Consolidation informa se os gates internos permitem publicar uma conclusão agregada.",
    ),
    IndicatorProvenance(
        "BR-GEO-001..054",
        "RASAI_HEURISTIC",
        "RASAi + fontes primárias por regra",
        "RULES_GUIDE / referências por BR-GEO",
        None,
        "Cada regra pode ter base OFFICIAL, STANDARD, HEURISTIC ou executor interno; a natureza é individual.",
        "O relatório preserva a base e a fonte por regra; uma referência externa não transforma uma heurística RASAi em standard externo.",
    ),
    IndicatorProvenance(
        "HTTP / status / redirects",
        "EXTERNAL_STANDARD",
        "IETF / RFC Editor",
        "RFC 9110 - HTTP Semantics",
        "https://www.rfc-editor.org/rfc/rfc9110.html",
        "Semântica normativa de HTTP e status de resposta.",
        "RASAi observa a resposta e aplica regras de auditabilidade/materialidade documentadas.",
    ),
    IndicatorProvenance(
        "robots.txt",
        "EXTERNAL_STANDARD",
        "IETF / RFC Editor",
        "RFC 9309 - Robots Exclusion Protocol",
        "https://www.rfc-editor.org/rfc/rfc9309.html",
        "Especificação formal do Robots Exclusion Protocol.",
        "RASAi resolve crawlers separadamente e não converte controles distintos em uma conclusão única indevida.",
    ),
    IndicatorProvenance(
        "Core Web Vitals - LCP / INP / CLS p75",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome / web.dev",
        "Web Vitals",
        "https://web.dev/articles/vitals",
        "Métricas, avaliação no percentil 75 e thresholds recomendados são definidos pelo programa Core Web Vitals.",
        "RASAi coleta PageSpeed/CrUX, preserva source/scope e não converte esses valores em SCORE-GEO-004.",
    ),
    IndicatorProvenance(
        "Lighthouse Performance",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome for Developers / Lighthouse",
        "Performance scoring",
        "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring",
        "Score, pesos e curvas pertencem ao Lighthouse e podem evoluir com a versão da ferramenta.",
        "RASAi persiste versão/resultado e apresenta a métrica separada do SARI-001.",
    ),
    IndicatorProvenance(
        "Lighthouse Accessibility",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome for Developers / Lighthouse",
        "Accessibility scoring",
        "https://developer.chrome.com/docs/lighthouse/accessibility/scoring",
        "Score automatizado definido pelo Lighthouse sobre audits de acessibilidade.",
        "RASAi não o apresenta como percentual de conformidade WCAG; critérios não automatizáveis exigem avaliação humana.",
    ),
    IndicatorProvenance(
        "WCAG 2.2",
        "EXTERNAL_STANDARD",
        "W3C",
        "Web Content Accessibility Guidelines (WCAG) 2.2",
        "https://www.w3.org/TR/WCAG22/",
        "Recommendation W3C com Success Criteria e requisitos de conformidade.",
        "RASAi associa evidências automatizáveis quando possível, sem declarar conformidade integral apenas por automação.",
    ),
    IndicatorProvenance(
        "Synthetic Navigation Apdex",
        "EXTERNAL_STANDARD",
        "Apdex Users Group / Apdex Alliance",
        "Apdex Technical Specification",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Fórmula, zonas Satisfied/Tolerating/Frustrated e tratamento de small groups vêm da especificação Apdex.",
        "O threshold T é configurado pelo operador; perfil sintético e coleta Chromium são declarados separadamente pelo RASAi.",
    ),
    IndicatorProvenance(
        "E-E-A-T / YMYL / people-first",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "Google Search Central",
        "Creating helpful, reliable, people-first content",
        "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
        "Google usa E-E-A-T/YMYL como orientação conceitual de qualidade; não expõe um E-E-A-T Score oficial.",
        "RASAi usa o contexto para aumentar rigor da análise de conteúdo sem criar score oficial E-E-A-T/YMYL.",
    ),
    IndicatorProvenance(
        "Structured Data / JSON-LD guidance",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "Google Search Central",
        "General Structured Data Guidelines",
        "https://developers.google.com/search/docs/appearance/structured-data/sd-policies",
        "Políticas de coerência, relevância e elegibilidade são documentadas pelo Google; Schema.org fornece o vocabulário.",
        "RASAi propõe/revisa marcação de forma conservadora e não promete rich result ou benefício em AI Search.",
    ),
    IndicatorProvenance(
        "IA semântica / sugestões de conteúdo",
        "AI_DERIVED_ADVISORY",
        "RASAi + provider configurado",
        "Contrato evidence-bound da análise semântica e remediação",
        None,
        "Não existe homologação externa da conclusão produzida pelo LLM para a página auditada.",
        "Provider/model/evidências/confiança são rastreados; saída é advisory e requer revisão humana.",
    ),
    IndicatorProvenance(
        "Tokens / duração / custo estimado de IA",
        "OPERATIONAL_TELEMETRY",
        "Provider + RASAi",
        "Telemetria persistida por tentativa",
        None,
        "Tokens/duração podem vir do provider/runtime e não medem qualidade do website.",
        "Custo é estimativa local baseada em pricing versionado quando disponível e nunca é apresentado como invoice.",
    ),
)

_PAGE_SUMMARY: dict[str, tuple[str, str]] = {
    "index.html": (
        "Painel multimetodológico",
        "O dashboard resume resultados finais sem fundir metodologias: SARI-001 é proprietário; Core Web Vitals, Lighthouse e Apdex mantêm suas definições externas.",
    ),
    "readiness.html": (
        "Heurística RASAi evidence-based",
        "SARI-001 usa SCORE-GEO-004 com Overall determinístico, Coverage, Confidence e Consolidation explicitamente separados.",
    ),
    "scoring.html": (
        "Metodologia RASAi reproduzível",
        "A página canônica estável expõe a versão vigente, fórmula, gates e limites do scoring sem alterar medições persistidas.",
    ),
    "mobile.html": (
        "Evidências RASAi por dispositivo",
        "Esta página contém findings e evidências Mobile. Indicadores agregados RASAi ficam exclusivamente em Search & AI Readiness; a base de cada BR-GEO é rastreável em Referências e metodologia.",
    ),
    "desktop.html": (
        "Evidências RASAi por dispositivo",
        "Esta página contém findings e evidências Desktop. Indicadores agregados RASAi ficam exclusivamente em Search & AI Readiness; a base de cada BR-GEO é rastreável em Referências e metodologia.",
    ),
    "remediation.html": (
        "Recomendação derivada de finding evidence-bound",
        "A origem normativa varia por BR-GEO. A referência aplicável é exibida quando existe; heurística permanece identificada como interna.",
    ),
    "content-suggestions.html": (
        "IA advisory + orientação oficial de conteúdo",
        "E-E-A-T/YMYL condicionam a análise como contexto; texto proposto por IA requer revisão humana.",
    ),
    "accessibility.html": (
        "Standard W3C + métrica automatizada Lighthouse",
        "WCAG 2.2 é standard externo; Lighthouse Accessibility é avaliação automatizada e não equivale a certificação de conformidade WCAG.",
    ),
    "web-performance.html": (
        "Métricas externas definidas",
        "Core Web Vitals e Lighthouse preservam metodologia externa. RASAi coleta e contextualiza sem convertê-los em SARI-001 ou SCORE-GEO-004.",
    ),
    "apdex.html": (
        "Método Apdex externo + T configurado pelo operador",
        "Fórmula/faixas vêm da especificação Apdex; T e perfil sintético efetivamente usados devem ser lidos junto ao resultado.",
    ),
    "ai-usage.html": (
        "Telemetria operacional",
        "Provider, modelo, reasoning, tokens, tempo e custo estimado descrevem uso de IA; não são indicadores de qualidade do site.",
    ),
}


def enrich_indicator_provenance_html(html: str, *, page_name: str) -> str:
    """Make methodological provenance explicit without changing measured values."""
    if PROVENANCE_MARKER in html:
        return html
    if page_name == "references.html":
        addition = _reference_panel()
    else:
        summary = _PAGE_SUMMARY.get(page_name)
        if summary is None:
            return html
        label, detail = summary
        addition = (
            f"<section class='notice' data-provenance='{PROVENANCE_MARKER}'>"
            f"<strong>Natureza dos indicadores:</strong> {escape(label)}. {escape(detail)} "
            "<a href='references.html#indicator-provenance'>Ver fonte, fórmula e limite metodológico</a></section>"
        )
    return html.replace("</header>", "</header>" + addition, 1)


def _reference_panel() -> str:
    rows: list[str] = []
    for item in INDICATORS:
        label = _CLASS_LABELS[item.classification]
        if item.source_url:
            source = (
                f"<a href='{escape(item.source_url, quote=True)}' target='_blank' rel='noopener'>"
                f"{escape(item.authority)} - {escape(item.source_title)}</a>"
            )
        else:
            source = f"{escape(item.authority)} - {escape(item.source_title)}"
        rows.append(
            "<tr>"
            f"<td><strong>{escape(item.indicator)}</strong></td>"
            f"<td><span class='badge'>{escape(label)}</span></td>"
            f"<td>{source}</td>"
            f"<td>{escape(item.external_logic)}</td>"
            f"<td>{escape(item.rasai_logic)}</td>"
            "</tr>"
        )
    return (
        f"<section id='indicator-provenance' class='panel' data-provenance='{PROVENANCE_MARKER}'>"
        "<div class='kicker'>Proveniência metodológica</div><h2>De onde vem cada indicador</h2>"
        "<p class='intro'>Fontes externas sustentam fenômenos, standards ou métricas específicas. "
        "Elas não homologam automaticamente o SARI-001 nem o SCORE-GEO-004.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Classe</th><th>Fonte/autoridade</th><th>Parte externa</th><th>Parte RASAi</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<p class='intro'>Referências verificadas em {VERIFIED_ON}.</p></section>"
    )
