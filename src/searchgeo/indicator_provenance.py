"""User-facing provenance for indicators projected into SearchGEO reports.

This module classifies methodology only. It does not recalculate persisted
measurements, findings or scores. External links are primary/official sources
and internal heuristics are explicitly labelled as SearchGEO decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

VERIFIED_ON = "2026-09-06"
PROVENANCE_MARKER = "searchgeo-indicator-provenance-v1"


@dataclass(frozen=True, slots=True)
class IndicatorProvenance:
    indicator: str
    classification: str
    authority: str
    source_title: str
    source_url: str | None
    external_logic: str
    searchgeo_logic: str


_CLASS_LABELS = {
    "RAW_OBSERVATION": "Observação coletada",
    "EXTERNAL_STANDARD": "Standard externo",
    "OFFICIAL_PLATFORM_GUIDANCE": "Orientação oficial de plataforma",
    "EXTERNAL_DEFINED_METRIC": "Métrica externa definida",
    "SEARCHGEO_HEURISTIC": "Heurística SearchGEO",
    "OPERATIONAL_TELEMETRY": "Telemetria operacional",
    "AI_DERIVED_ADVISORY": "Análise/sugestão por IA",
}

INDICATORS: tuple[IndicatorProvenance, ...] = (
    IndicatorProvenance(
        "SearchGEO Readiness Index (SGRI-001)",
        "SEARCHGEO_HEURISTIC",
        "SearchGEO",
        "SEARCHGEO_READINESS_INDEX / SCORING_GUIDE / SCORING_VALIDATION",
        None,
        "Não existe score GEO/AEO 0–100 universal homologado usado por esta saída.",
        "SGRI-001 é a identidade pública do índice composto. Enquanto a aritmética não mudar, o motor persistido continua SCORE-GEO-002 para preservar comparabilidade histórica.",
    ),
    IndicatorProvenance(
        "Coverage / Confidence / Consolidation",
        "SEARCHGEO_HEURISTIC",
        "SearchGEO",
        "SCORING_GUIDE",
        None,
        "Não há thresholds GEO universais externos para estes estados.",
        "Coverage mede universo aplicável avaliado; Confidence e Consolidation usam thresholds internos versionados.",
    ),
    IndicatorProvenance(
        "BR-GEO-001..054",
        "SEARCHGEO_HEURISTIC",
        "SearchGEO + fontes primárias por regra",
        "RULES_GUIDE / referências por BR-GEO",
        None,
        "Cada regra pode ter base OFFICIAL, STANDARD, HEURISTIC ou executor interno; a natureza é individual.",
        "O report preserva a base e a fonte por regra; uma referência externa não transforma uma heurística em standard.",
    ),
    IndicatorProvenance(
        "HTTP / status / redirects",
        "EXTERNAL_STANDARD",
        "IETF / RFC Editor",
        "RFC 9110 — HTTP Semantics",
        "https://www.rfc-editor.org/rfc/rfc9110.html",
        "Semântica normativa de HTTP e status de resposta.",
        "SearchGEO observa a resposta e aplica regras de auditabilidade/materialidade documentadas.",
    ),
    IndicatorProvenance(
        "robots.txt",
        "EXTERNAL_STANDARD",
        "IETF / RFC Editor",
        "RFC 9309 — Robots Exclusion Protocol",
        "https://www.rfc-editor.org/rfc/rfc9309.html",
        "Especificação formal do Robots Exclusion Protocol.",
        "SearchGEO resolve crawlers separadamente e não converte controles distintos em uma conclusão única indevida.",
    ),
    IndicatorProvenance(
        "Core Web Vitals — LCP / INP / CLS p75",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome / web.dev",
        "Web Vitals",
        "https://web.dev/articles/vitals",
        "Métricas, avaliação no percentil 75 e thresholds recomendados são definidos externamente pelo programa Core Web Vitals.",
        "SearchGEO coleta PageSpeed/CrUX, preserva source/scope e não converte CWV em SGRI-001.",
    ),
    IndicatorProvenance(
        "Lighthouse Performance",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome for Developers / Lighthouse",
        "Performance scoring",
        "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring",
        "Score, pesos e curvas pertencem ao Lighthouse e podem evoluir com a versão da ferramenta.",
        "SearchGEO persiste versão/resultado e o apresenta separado do índice SearchGEO.",
    ),
    IndicatorProvenance(
        "Lighthouse Accessibility",
        "EXTERNAL_DEFINED_METRIC",
        "Chrome for Developers / Lighthouse",
        "Accessibility scoring",
        "https://developer.chrome.com/docs/lighthouse/accessibility/scoring",
        "Score automatizado definido pelo Lighthouse sobre audits de acessibilidade.",
        "SearchGEO não o apresenta como percentual de conformidade WCAG; critérios não automatizáveis exigem avaliação humana.",
    ),
    IndicatorProvenance(
        "WCAG 2.2",
        "EXTERNAL_STANDARD",
        "W3C",
        "Web Content Accessibility Guidelines (WCAG) 2.2",
        "https://www.w3.org/TR/WCAG22/",
        "Recommendation W3C com Success Criteria e requisitos de conformidade.",
        "SearchGEO associa evidências automatizáveis quando possível, sem declarar conformidade integral apenas por automação.",
    ),
    IndicatorProvenance(
        "Synthetic Navigation Apdex",
        "EXTERNAL_STANDARD",
        "Apdex Users Group / Apdex Alliance",
        "Apdex Technical Specification",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Fórmula, zonas Satisfied/Tolerating/Frustrated, faixas qualitativas e tratamento de small groups vêm da especificação Apdex.",
        "O threshold T é configurado pelo operador; perfil sintético, limites operacionais e coleta Chromium são declarados separadamente pelo SearchGEO.",
    ),
    IndicatorProvenance(
        "E-E-A-T / YMYL / people-first",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "Google Search Central",
        "Creating helpful, reliable, people-first content",
        "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
        "Google usa E-E-A-T/YMYL como orientação conceitual de qualidade; E-E-A-T não é exposto como fator numérico específico de ranking.",
        "SearchGEO usa o contexto para tornar a análise de conteúdo menos generalista, sem criar score E-E-A-T/YMYL oficial.",
    ),
    IndicatorProvenance(
        "Structured Data / JSON-LD guidance",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "Google Search Central",
        "General Structured Data Guidelines",
        "https://developers.google.com/search/docs/appearance/structured-data/sd-policies",
        "Políticas de coerência, relevância e elegibilidade são documentadas pelo Google; Schema.org fornece o vocabulário.",
        "SearchGEO propõe/revisa marcação de forma conservadora e não promete rich result nem benefício GEO.",
    ),
    IndicatorProvenance(
        "IA semântica / sugestões de conteúdo",
        "AI_DERIVED_ADVISORY",
        "SearchGEO + provider configurado",
        "Contrato evidence-bound M18/M20",
        None,
        "Não existe homologação externa da conclusão produzida pelo LLM para a página auditada.",
        "Provider/model/reasoning/evidências/confiança da sugestão são rastreados; saída é advisory e requer revisão humana.",
    ),
    IndicatorProvenance(
        "Tokens / duração / custo estimado de IA",
        "OPERATIONAL_TELEMETRY",
        "Provider + SearchGEO",
        "Telemetria persistida por tentativa",
        None,
        "Tokens/duração podem vir do provider/runtime; não medem qualidade do website.",
        "Custo é estimativa local baseada em pricing versionado quando disponível e nunca é apresentado como invoice.",
    ),
)

_PAGE_SUMMARY: dict[str, tuple[str, str]] = {
    "index.html": (
        "Painel multimetodológico",
        "O dashboard resume resultados finais sem fundir metodologias: SGRI-001 é proprietário; Core Web Vitals, Lighthouse e Apdex mantêm suas definições externas.",
    ),
    "searchgeo.html": (
        "Heurística SearchGEO evidence-based",
        "SGRI-001 centraliza Overall, dimensões, Coverage, Confidence e Consolidation. O motor persistido SCORE-GEO-002 é mantido como compatibilidade enquanto a aritmética não muda.",
    ),
    "mobile.html": (
        "Evidências SearchGEO por dispositivo",
        "Esta página contém findings e evidências Mobile. Indicadores agregados SearchGEO ficam exclusivamente em SearchGEO Readiness; a base de cada BR-GEO é rastreável em Referências e metodologia.",
    ),
    "desktop.html": (
        "Evidências SearchGEO por dispositivo",
        "Esta página contém findings e evidências Desktop. Indicadores agregados SearchGEO ficam exclusivamente em SearchGEO Readiness; a base de cada BR-GEO é rastreável em Referências e metodologia.",
    ),
    "remediation.html": (
        "Recomendação derivada de finding evidence-backed",
        "A origem normativa varia por BR-GEO. A referência oficial aplicável é exibida quando existe; heurística permanece identificada como interna.",
    ),
    "content-suggestions.html": (
        "IA advisory + orientação oficial de conteúdo",
        "E-E-A-T/YMYL condicionam a análise como contexto oficial do Google; o texto proposto é saída de IA evidence-bound e requer revisão humana.",
    ),
    "accessibility.html": (
        "Standard W3C + métrica automatizada Lighthouse",
        "WCAG 2.2 é standard externo; Lighthouse Accessibility é avaliação automatizada e não equivale a certificação de conformidade WCAG.",
    ),
    "web-performance.html": (
        "Métricas externas definidas",
        "Core Web Vitals e Lighthouse preservam metodologia/thresholds externos. SearchGEO coleta e contextualiza sem convertê-los em SGRI-001.",
    ),
    "apdex.html": (
        "Método Apdex externo + T configurado pelo operador",
        "Fórmula/faixas vêm da especificação Apdex; T e o perfil sintético efetivamente usados devem ser lidos junto ao resultado.",
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
            "<a href='references.html#indicator-provenance'>Ver fonte, fórmula e parte interna de cada indicador →</a></section>"
        )
    return html.replace("</header>", "</header>" + addition, 1)


def _reference_panel() -> str:
    rows: list[str] = []
    for item in INDICATORS:
        label = _CLASS_LABELS[item.classification]
        if item.source_url:
            source = (
                f"<a href='{escape(item.source_url, quote=True)}' target='_blank' rel='noopener'>"
                f"{escape(item.authority)} — {escape(item.source_title)} ↗</a>"
            )
        else:
            source = f"{escape(item.authority)} — {escape(item.source_title)}"
        rows.append(
            "<tr>"
            f"<td><strong>{escape(item.indicator)}</strong></td>"
            f"<td><span class='badge info' title='Classificação metodológica do indicador'>{escape(label)}</span></td>"
            f"<td>{source}</td>"
            f"<td>{escape(item.external_logic)}</td>"
            f"<td>{escape(item.searchgeo_logic)}</td>"
            "</tr>"
        )
    legend = " · ".join(f"<span class='badge'>{escape(label)}</span>" for label in _CLASS_LABELS.values())
    return (
        f"<section id='indicator-provenance' class='panel' data-provenance='{PROVENANCE_MARKER}'>"
        "<div class='kicker'>Proveniência metodológica</div><h2>De onde vem cada indicador</h2>"
        "<p class='intro'>Esta tabela separa standard externo, orientação oficial, métrica definida por terceiros, observação, "
        "heurística SearchGEO, IA advisory e telemetria. Uma fonte oficial sustenta apenas o fenômeno indicado; não homologa automaticamente o SGRI-001.</p>"
        f"<p class='intro'><strong>Classificações:</strong> {legend}</p>"
        f"<div class='notice'><strong>Referências verificadas em:</strong> {VERIFIED_ON}. Links externos apontam para fontes primárias/oficiais quando disponíveis.</div>"
        "<div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Natureza</th><th>Fonte / entidade</th><th>Lógica externa</th><th>Aplicação SearchGEO</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )
