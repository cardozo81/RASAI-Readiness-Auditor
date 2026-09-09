"""User-facing provenance for indicators projected into RASAi reports.

This module classifies methodology and the role each signal has in SARI.  It does
not recalculate persisted measurements, findings or scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

VERIFIED_ON = "2026-09-09"
PROVENANCE_MARKER = "rasai-indicator-provenance-v2"


@dataclass(frozen=True, slots=True)
class IndicatorProvenance:
    indicator: str
    classification: str
    score_role: str
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

_ROLE_LABELS = {
    "COMPOSITE_OUTPUT": "Saída composta",
    "MEASUREMENT_QUALITY": "Qualidade da medição",
    "CORE_SCORE_INPUT": "Input do SARI",
    "CORROBORATIVE_EVIDENCE": "Evidência corroborativa",
    "CONTEXT_ONLY": "Contexto; não pontua diretamente",
    "OBSERVED_OUTCOME": "Outcome observado",
    "OPERATIONAL_TELEMETRY": "Telemetria; não pontua",
}

INDICATORS: tuple[IndicatorProvenance, ...] = (
    IndicatorProvenance(
        "Search & AI Readiness Index (SARI-001)",
        "RASAI_HEURISTIC",
        "COMPOSITE_OUTPUT",
        "RASAi",
        "SCORE-GEO-004 / SCORING_GUIDE",
        None,
        "Não existe score GEO/AEO universal homologado usado por esta saída.",
        "SCORE-GEO-004 agrega dimensões e grupos com pesos estáticos/versionados, separados de Coverage, Confidence e critical readiness gates. O índice não é probabilidade de ranking ou citação.",
    ),
    IndicatorProvenance(
        "Coverage / Confidence / Consolidation / Critical Gates",
        "RASAI_HEURISTIC",
        "MEASUREMENT_QUALITY",
        "RASAi",
        "SCORING_GUIDE",
        None,
        "Não há thresholds GEO universais externos para estes estados.",
        "Coverage mede completude ponderada; Confidence combina confiança das dimensões com rigor adicional para Discovery, Indexability e Extraction; Consolidation mede suficiência da medição. Critical Gates descrevem bloqueios de readiness e não alteram artificialmente a nota numérica.",
    ),
    IndicatorProvenance(
        "BR-GEO-001..059",
        "RASAI_HEURISTIC",
        "CORE_SCORE_INPUT",
        "RASAi + fontes primárias por regra",
        "RULES_GUIDE / referências por BR-GEO",
        None,
        "Cada regra pode ter base OFFICIAL, STANDARD, HEURISTIC ou executor interno; a natureza é individual.",
        "Somente regras presentes no manifesto do SCORE-GEO-004 entram no SARI. Regras de integridade/telemetria permanecem fora da aritmética.",
    ),
    IndicatorProvenance(
        "HTTP / status / redirects",
        "EXTERNAL_STANDARD",
        "CORE_SCORE_INPUT",
        "IETF / RFC Editor",
        "RFC 9110 - HTTP Semantics",
        "https://www.rfc-editor.org/rfc/rfc9110.html",
        "Semântica normativa de HTTP e status de resposta.",
        "RASAi observa a resposta e aplica regras versionadas de discovery, recuperação e materialidade.",
    ),
    IndicatorProvenance(
        "robots.txt",
        "EXTERNAL_STANDARD",
        "CORE_SCORE_INPUT",
        "IETF / RFC Editor",
        "RFC 9309 - Robots Exclusion Protocol",
        "https://www.rfc-editor.org/rfc/rfc9309.html",
        "Especificação formal do Robots Exclusion Protocol.",
        "RASAi resolve crawlers separadamente. Avaliação IA opcional é corroborativa e não substitui fato determinístico conclusivo.",
    ),
    IndicatorProvenance(
        "Core Web Vitals - LCP / INP / CLS p75",
        "EXTERNAL_DEFINED_METRIC",
        "CONTEXT_ONLY",
        "Chrome / web.dev",
        "Web Vitals",
        "https://web.dev/articles/vitals",
        "Métricas, percentil 75 e thresholds recomendados são definidos pelo programa Core Web Vitals.",
        "RASAi preserva source/scope. O valor CWV não é convertido em SARI; consequências materiais de rendering/extractability são avaliadas pelas próprias BR-GEO.",
    ),
    IndicatorProvenance(
        "Lighthouse Performance",
        "EXTERNAL_DEFINED_METRIC",
        "CONTEXT_ONLY",
        "Chrome for Developers / Lighthouse",
        "Performance scoring",
        "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring",
        "Score, pesos e curvas pertencem ao Lighthouse e podem evoluir com a versão da ferramenta.",
        "O score da categoria permanece separado do SARI-001.",
    ),
    IndicatorProvenance(
        "Lighthouse SEO / Best Practices / Accessibility - category scores",
        "EXTERNAL_DEFINED_METRIC",
        "CONTEXT_ONLY",
        "Chrome for Developers / Lighthouse",
        "Lighthouse categories",
        "https://developer.chrome.com/docs/lighthouse/overview/",
        "Cada categoria possui seu próprio conjunto de auditorias e metodologia Lighthouse.",
        "Nenhum score de categoria é multiplicado por peso SARI. Um audit técnico individual só pode ser usado como evidência corroborativa quando houver mapeamento explícito para a mesma condição BR-GEO, sem dupla pontuação.",
    ),
    IndicatorProvenance(
        "Lighthouse audit-level evidence",
        "EXTERNAL_DEFINED_METRIC",
        "CORROBORATIVE_EVIDENCE",
        "Chrome for Developers / Lighthouse",
        "Lighthouse audits",
        "https://developer.chrome.com/docs/lighthouse/overview/",
        "Audit individual descreve um check específico daquela execução Lighthouse.",
        "Pode corroborar uma BR-GEO equivalente quando o mapeamento estiver contratado. Não cria score próprio e nunca usa a nota da categoria como atalho para o SARI.",
    ),
    IndicatorProvenance(
        "WCAG 2.2",
        "EXTERNAL_STANDARD",
        "CONTEXT_ONLY",
        "W3C",
        "Web Content Accessibility Guidelines (WCAG) 2.2",
        "https://www.w3.org/TR/WCAG22/",
        "Recommendation W3C com Success Criteria e requisitos de conformidade.",
        "RASAi associa evidências automatizáveis quando possível, sem declarar conformidade integral por automação e sem transformar WCAG em score SARI.",
    ),
    IndicatorProvenance(
        "Synthetic Navigation Apdex",
        "EXTERNAL_STANDARD",
        "CONTEXT_ONLY",
        "Apdex Users Group / Apdex Alliance",
        "Apdex Technical Specification",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Fórmula, zonas Satisfied/Tolerating/Frustrated e tratamento de small groups vêm da especificação Apdex.",
        "T é configurado pelo operador; o resultado permanece fora do SARI.",
    ),
    IndicatorProvenance(
        "E-E-A-T / YMYL / people-first",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "CONTEXT_ONLY",
        "Google Search Central",
        "Creating helpful, reliable, people-first content",
        "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
        "Google usa esses conceitos como orientação de qualidade; não expõe um E-E-A-T Score oficial.",
        "RASAi usa o contexto para calibrar rigor de análise, sem criar score oficial E-E-A-T/YMYL.",
    ),
    IndicatorProvenance(
        "Content Value - BR-GEO-057..059",
        "RASAI_HEURISTIC",
        "CORE_SCORE_INPUT",
        "RASAi",
        "CONTENT-VALUE-BASELINE-001",
        None,
        "Não existe fórmula externa universal para utilidade, diferenciação e profundidade de conteúdo.",
        "A baseline local conclui somente quando sinais explícitos e persistidos sustentam a avaliação. Diferenciação não provada fica UNKNOWN; ausência de evidência nunca é convertida em FAIL.",
    ),
    IndicatorProvenance(
        "Structured Data / JSON-LD guidance",
        "OFFICIAL_PLATFORM_GUIDANCE",
        "CORE_SCORE_INPUT",
        "Google Search Central",
        "General Structured Data Guidelines",
        "https://developers.google.com/search/docs/appearance/structured-data/sd-policies",
        "Políticas de coerência, relevância e elegibilidade são documentadas pelo Google; Schema.org fornece o vocabulário.",
        "Structured Data representa 5% do contrato SARI quando aplicável; ausência legitimamente não aplicável não recebe zero nem bônus.",
    ),
    IndicatorProvenance(
        "IA semântica evidence-bound",
        "AI_DERIVED_ADVISORY",
        "CORE_SCORE_INPUT",
        "RASAi + provider configurado",
        "Contrato semantic assessment",
        None,
        "Não existe homologação externa da conclusão do LLM para a página auditada.",
        "Uma resposta normalizada pode materializar RuleExecution contratada. O provider não escolhe pesos e fatos determinísticos conclusivos têm precedência no mesmo scoring_group.",
    ),
    IndicatorProvenance(
        "Sugestões de conteúdo por IA",
        "AI_DERIVED_ADVISORY",
        "CONTEXT_ONLY",
        "RASAi + provider configurado",
        "Contrato de remediação",
        None,
        "Texto proposto pelo LLM não é validação externa da página.",
        "Sugestões exigem revisão humana e não alteram automaticamente ScoreContributions.",
    ),
    IndicatorProvenance(
        "SERP / Search Console / Observed Generative Visibility",
        "RAW_OBSERVATION",
        "OBSERVED_OUTCOME",
        "Mecanismo/provider observado",
        "Outcome externo",
        None,
        "Posição, impressão, clique, menção ou citação descrevem resultado observado em um mecanismo/período.",
        "Outcomes permanecem fora do SARI operacional e são usados para observabilidade e futura validação/calibração empírica.",
    ),
    IndicatorProvenance(
        "Tokens / duração / custo estimado de IA",
        "OPERATIONAL_TELEMETRY",
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
        "SARI-001 é proprietário; Lighthouse, Core Web Vitals, Apdex e outcomes externos mantêm metodologias independentes.",
    ),
    "readiness.html": (
        "Heurística RASAi evidence-based",
        "SARI-001 usa SCORE-GEO-004 hierárquico/ponderado, com Coverage, Confidence, Consolidation e Critical Gates separados.",
    ),
    "scoring.html": (
        "Metodologia RASAi reproduzível",
        "A página expõe pesos fixos de dimensão/grupo, gates e limites do scoring sem recalcular a auditoria.",
    ),
    "mobile.html": (
        "Evidências RASAi por dispositivo",
        "Findings e evidências Mobile; a agregação SARI fica em Search & AI Readiness.",
    ),
    "desktop.html": (
        "Evidências RASAi por dispositivo",
        "Findings e evidências Desktop; a agregação SARI fica em Search & AI Readiness.",
    ),
    "remediation.html": (
        "Recomendação derivada de finding evidence-bound",
        "A origem normativa varia por BR-GEO; heurística permanece identificada como interna.",
    ),
    "content-suggestions.html": (
        "IA advisory + contexto oficial de conteúdo",
        "E-E-A-T/YMYL podem aumentar o rigor; texto proposto por IA requer revisão humana.",
    ),
    "accessibility.html": (
        "Standard W3C + métrica Lighthouse",
        "WCAG 2.2 e Lighthouse Accessibility permanecem fora da aritmética SARI.",
    ),
    "web-performance.html": (
        "Métricas externas definidas",
        "Scores Lighthouse e Core Web Vitals permanecem independentes. Audit-level evidence só pode corroborar regra equivalente por mapeamento explícito.",
    ),
    "apdex.html": (
        "Método Apdex externo + T configurado",
        "Apdex é complementar e não entra no SARI.",
    ),
    "ai-usage.html": (
        "Telemetria operacional",
        "Provider, modelo, reasoning, tokens, tempo e custo estimado não medem qualidade do site.",
    ),
}


def enrich_indicator_provenance_html(html: str, *, page_name: str) -> str:
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
            "<a href='references.html#indicator-provenance'>Ver fonte, função no SARI e limite metodológico</a></section>"
        )
    return html.replace("</header>", "</header>" + addition, 1)


def _reference_panel() -> str:
    rows: list[str] = []
    for item in INDICATORS:
        label = _CLASS_LABELS[item.classification]
        role = _ROLE_LABELS[item.score_role]
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
            f"<td><span class='badge'>{escape(role)}</span></td>"
            f"<td>{source}</td>"
            f"<td>{escape(item.external_logic)}</td>"
            f"<td>{escape(item.rasai_logic)}</td>"
            "</tr>"
        )
    return (
        f"<section id='indicator-provenance' class='panel' data-provenance='{PROVENANCE_MARKER}'>"
        "<div class='kicker'>Proveniência metodológica</div><h2>De onde vem cada indicador e como ele participa do SARI</h2>"
        "<p class='intro'>Fontes externas sustentam fenômenos, standards ou métricas específicas. "
        "Elas não homologam automaticamente o SARI-001 nem o SCORE-GEO-004.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Classe</th><th>Função no SARI</th><th>Fonte/autoridade</th><th>Parte externa</th><th>Parte RASAi</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<p class='intro'>Referências verificadas em {VERIFIED_ON}.</p></section>"
    )
