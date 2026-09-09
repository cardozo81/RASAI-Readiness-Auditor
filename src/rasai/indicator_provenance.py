"""User-facing provenance for indicators projected into RASAi reports.

This module classifies methodology and the role each signal has in SARI. It also
normalizes known legacy presentation wording so final HTML cannot contradict the
active SCORE-GEO-004 contract. It never recalculates persisted measurements,
findings or scores.
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

# Exact RASAi-owned presentation strings from development iterations. A generic
# M<number> replacement is intentionally forbidden because audited page content
# may legitimately contain model/product names such as M3 or M25. These exact
# phrases are safe to normalize because they were emitted by RASAi templates.
_PUBLIC_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("M18/M20", "análise semântica e remediação textual"),
    ("M21/M22", "Web Performance e Acessibilidade"),
    ("M21 + M22 · domínio Web Performance", "Domínio Web Performance"),
    ("M23 · domínio Web Performance", "Domínio Synthetic Apdex"),
    ("Web Performance · M23", "Synthetic Apdex"),
    ("M23 · performance sintética transacional", "Performance sintética transacional"),
    ("M23 · metodologia", "Metodologia Synthetic Apdex"),
    ("M22 · domínio independente", "Domínio independente"),
    ("M22 · diagnóstico técnico", "Diagnóstico técnico"),
    ("M22 · fronteiras de domínio", "Fronteiras de domínio"),
    ("M20 · remediação opcional", "Remediação opcional"),
    ("Estado M23", "Estado"),
    ("Synthetic Apdex M23", "Synthetic Apdex"),
    ("M23 não chama", "Synthetic Apdex não chama"),
    ("regras conservadoras do M23", "regras conservadoras do Synthetic Apdex"),
    ("M20 é projeção auxiliar", "A remediação textual é uma projeção auxiliar"),
    ("Nenhuma chamada M20.", "Nenhuma chamada de remediação textual."),
    ("análise semântica M18", "análise semântica principal"),
    ("pelo M21", "pela coleta de Web Performance"),
    ("M22 Acessibilidade", "Acessibilidade automatizada"),
    ("M21/M23", "Web Performance/Synthetic Apdex"),
    ("M18 análise semântica", "Análise semântica por IA"),
    ("M20 remediação textual", "Remediação textual por IA"),
    ("M24-CD-001", "CRAWLING-DISCOVERY-001"),
    ("Rastreamento e descoberta M24", "Rastreamento e descoberta"),
    ("m20-no-eligible-note", "content-remediation-no-eligible-note"),
    ("m23-apdex-summary", "apdex-summary"),
)


def _normalize_public_owned_wording(html: str) -> str:
    for old, new in _PUBLIC_PRESENTATION_REPLACEMENTS:
        html = html.replace(old, new)
    return html


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


def _normalize_current_sari_wording(html: str, *, page_name: str) -> str:
    """Remove presentation remnants from the pre-recalibration SCORE-GEO-004 contract."""
    if page_name not in {"readiness.html", "scoring.html", "mobile.html", "desktop.html"}:
        return html

    replacements = (
        (
            "Média de igual peso das dimensões aplicáveis com medição suficiente. Dimensão legitimamente NOT_APPLICABLE sai do denominador e não recebe zero.",
            "Média ponderada pelos pesos versionados das dimensões medidas e aplicáveis. Dimensão legitimamente NOT_APPLICABLE sai do denominador e os pesos restantes são normalizados.",
        ),
        (
            "O Overall usa a média dessa Coverage entre dimensões aplicáveis; ela não representa percentual de URLs do domínio rastreadas ou auditadas.",
            "O Overall Coverage é ponderado pelos pesos das dimensões aplicáveis; ele não representa percentual de URLs do domínio rastreadas ou auditadas.",
        ),
        (
            "O Overall usa a menor Confidence entre as dimensões aplicáveis. Para consolidar, exige Coverage média de pelo menos 80% e Confidence mínima MEDIUM. A presença de IA não é requisito: uma execução NO_AI pode atingir MEDIUM/HIGH quando Coverage, evidências e integridade da execução forem suficientes.",
            "O Overall usa Confidence ponderada, com rigor adicional para Discovery, Indexability e Extraction. Para consolidar, exige Coverage ponderada de pelo menos 80%, Confidence HIGH/MEDIUM e ausência de bloqueador crítico de medição. A presença de IA não é requisito.",
        ),
        (
            "O gate de consolidação exige Coverage Overall de pelo menos 80% e Confidence mínima MEDIUM. O Overall herda a menor Confidence entre as dimensões aplicáveis; por isso uma nota relativamente alta pode permanecer parcial sem contradição.",
            "O gate de consolidação exige Coverage Overall ponderada de pelo menos 80%, Confidence HIGH/MEDIUM e nenhuma dimensão crítica aplicável sem medição suficiente. Por isso uma nota relativamente alta pode permanecer parcial ou não consolidada sem contradição.",
        ),
        (
            "Os gates mínimos de Coverage e Confidence foram atendidos para esta medição.",
            "Os gates ponderados de Coverage, Confidence e medição crítica foram atendidos para esta medição.",
        ),
        (
            "peso máximo versionado 0,25",
            "peso versionado 0,05 dentro de DISCOVERY_ACCESS",
        ),
        (
            "peso máximo versionado 0,60",
            "peso versionado 0,15 dentro de DISCOVERY_ACCESS",
        ),
    )
    for old, new in replacements:
        html = html.replace(old, new)

    html = html.replace(">DISCOVERY_ACCESS<", ">Acesso e descoberta<")
    html = html.replace(">CONTENT_VALUE<", ">Valor do conteúdo<")
    return html


def enrich_indicator_provenance_html(html: str, *, page_name: str) -> str:
    # This function is in the shared report-semantics path. Normalize public
    # delivery labels before the idempotence marker check so newly injected blocks
    # are also cleaned on subsequent report passes.
    html = _normalize_public_owned_wording(html)
    html = _normalize_current_sari_wording(html, page_name=page_name)
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
