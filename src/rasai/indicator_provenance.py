"""User-facing provenance for indicators projected into RASAi reports.

This module classifies methodology and the role each signal has in SARI. It also
normalizes compatibility presentation wording so final HTML cannot contradict the
active SCORE-GEO-004 contract. It never recalculates persisted measurements,
findings or scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from rasai.public_report_safety import normalize_owned_public_report_text

VERIFIED_ON = "2026-09-14"
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
    "RASAI_HEURISTIC": "Heurística Interna do RASAi",
    "OPERATIONAL_TELEMETRY": "Telemetria operacional",
    "AI_DERIVED_ADVISORY": "Análise/sugestão por IA",
}

_ROLE_LABELS = {
    "COMPOSITE_OUTPUT": "Saída composta",
    "MEASUREMENT_QUALITY": "Qualidade da medição",
    "CORE_SCORE_INPUT": "Entrada do Índice de Prontidão",
    "CORROBORATIVE_EVIDENCE": "Evidência corroborativa",
    "CONTEXT_ONLY": "Contexto; não pontua diretamente",
    "OBSERVED_OUTCOME": "Outcome observado",
    "OPERATIONAL_TELEMETRY": "Telemetria; não pontua",
}


INDICATORS: tuple[IndicatorProvenance, ...] = (
    IndicatorProvenance(
        "Search & AI Readiness Index - Índice de Prontidão Search & IA (ID técnico SARI-001)",
        "RASAI_HEURISTIC",
        "COMPOSITE_OUTPUT",
        "RASAi",
        "SCORE-GEO-004 / SCORING_GUIDE",
        None,
        "Não existe score GEO/AEO universal homologado usado por esta saída.",
        "O Método de Pontuação de Prontidão (contrato técnico SCORE-GEO-004) agrega dimensões e grupos com pesos estáticos/versionados, separados de Cobertura, Confiança e Critérios Críticos de Prontidão. O índice não é probabilidade de ranking ou citação.",
    ),
    IndicatorProvenance(
        "Coverage - Cobertura / Confidence - Confiança / Consolidation - Consolidação / Critical Gates - Critérios Críticos",
        "RASAI_HEURISTIC",
        "MEASUREMENT_QUALITY",
        "RASAi",
        "SCORING_GUIDE",
        None,
        "Não há thresholds GEO universais externos para estes estados.",
        "Coverage mede completude ponderada; Confidence combina confiança das dimensões com rigor adicional para Discovery, Indexability e Extraction; Consolidation mede suficiência da medição. Critical Gates descrevem bloqueios de readiness e não alteram artificialmente a nota numérica.",
    ),
    IndicatorProvenance(
        "Regras de Avaliação de Prontidão - IDs técnicos BR-GEO-001..059",
        "RASAI_HEURISTIC",
        "CORE_SCORE_INPUT",
        "RASAi + fontes primárias por regra",
        "RULES_GUIDE / referências por BR-GEO",
        None,
        "Cada regra pode ter base OFFICIAL, STANDARD, HEURISTIC ou executor interno; a natureza é individual. BR-GEO-060 é a regra externa corroborativa do mesmo ruleset e está descrita separadamente abaixo.",
        "O conjunto vigente compreende os IDs técnicos BR-GEO-001..060. Somente regras presentes no manifesto do Método de Pontuação de Prontidão (contrato técnico SCORE-GEO-004) entram no Índice de Prontidão Search & IA; regras de integridade e telemetria permanecem fora da aritmética.",
    ),
    IndicatorProvenance(
        "BR-GEO-060 / Common Crawl",
        "RAW_OBSERVATION",
        "CORE_SCORE_INPUT",
        "Common Crawl + RASAi",
        "Common Crawl Index API / SCORE-GEO-004",
        "https://index.commoncrawl.org/",
        "Common Crawl fornece uma observação externa de histórico de rastreamento. Ausência na amostra consultada não prova ausência de descoberta nem falha do site.",
        "RASAi usa BR-GEO-060 como corroboração positive-only em DISCOVERY_ACCESS/EXTERNAL_CRAWL_CORROBORATION. Evidência ausente, erro, timeout ou alvo inelegível não gera FAIL, zero, redução de Coverage/Confidence nem Critical Gate.",
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
        "Outcomes permanecem fora do SARI operacional e são usados para observabilidade e validação/calibração empírica quando houver série apropriada.",
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
        "O Índice de Prontidão Search & IA é proprietário do RASAi; Lighthouse, Core Web Vitals, Apdex e resultados externos mantêm metodologias independentes.",
    ),
    "readiness.html": (
        "Heurística RASAi evidence-based",
        "O Índice de Prontidão Search & IA usa o Método de Pontuação de Prontidão, com Cobertura, Confiança, Consolidação e Critérios Críticos separados. IDs técnicos: SARI-001 e SCORE-GEO-004.",
    ),
    "scoring.html": (
        "Método de Pontuação de Prontidão reproduzível",
        "A página expõe pesos fixos de dimensão/grupo, critérios críticos e limites da pontuação sem recalcular a auditoria.",
    ),
    "mobile.html": (
        "Evidências RASAi por dispositivo",
        "Achados e evidências Mobile; a agregação do Índice de Prontidão fica na superfície de Search & AI Readiness.",
    ),
    "desktop.html": (
        "Evidências RASAi por dispositivo",
        "Achados e evidências Desktop; a agregação do Índice de Prontidão fica na superfície de Search & AI Readiness.",
    ),
    "remediation.html": (
        "Recomendação derivada de finding evidence-bound",
        "A origem normativa varia por Regra de Avaliação de Prontidão; o ID técnico BR-GEO-* permanece disponível e a heurística é identificada como interna.",
    ),
    "content-suggestions.html": (
        "IA advisory + contexto oficial de conteúdo",
        "E-E-A-T/YMYL podem aumentar o rigor; texto proposto por IA requer revisão humana.",
    ),
    "accessibility.html": (
        "Standard W3C + métrica Lighthouse",
        "WCAG 2.2 e Lighthouse Accessibility permanecem fora da aritmética do Índice de Prontidão Search & IA.",
    ),
    "web-performance.html": (
        "Métricas externas definidas",
        "Scores Lighthouse e Core Web Vitals permanecem independentes. Audit-level evidence só pode corroborar regra equivalente por mapeamento explícito.",
    ),
    "apdex.html": (
        "Método Apdex externo + T configurado",
        "Apdex é complementar e não entra no Índice de Prontidão Search & IA.",
    ),
    "ai-usage.html": (
        "Telemetria operacional",
        "Provider, modelo, reasoning, tokens, tempo e custo estimado não medem qualidade do site.",
    ),
}


def _normalize_current_sari_wording(html: str, *, page_name: str) -> str:
    """Normalize presentation text to the active SCORE-GEO-004 contract."""
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
    html = normalize_owned_public_report_text(html)
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
        "<div class='kicker'>Proveniência metodológica</div><h2>De onde vem cada indicador e como ele participa do Índice de Prontidão</h2>"
        "<p class='intro'>Fontes externas sustentam fenômenos, standards ou métricas específicas. "
        "Elas não homologam automaticamente o Índice de Prontidão Search & IA nem o Método de Pontuação de Prontidão. IDs técnicos: SARI-001 e SCORE-GEO-004.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Indicador</th><th>Classe</th><th>Função no Índice de Prontidão</th><th>Fonte/autoridade</th><th>Parte externa</th><th>Parte RASAi</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<p class='intro'>Referências verificadas em {VERIFIED_ON}.</p></section>"
    )