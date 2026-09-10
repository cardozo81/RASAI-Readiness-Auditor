# Documentação do RASAi

## Estado do produto

O RASAi está em **desenvolvimento e validação pré-publicação**. A documentação descreve exclusivamente o contrato vigente do produto; histórico de branches, PRs, nomes substituídos, aliases transitórios e comportamentos descartados durante o desenvolvimento não fazem parte do contrato documental.

O contrato funcional vigente usa:

- índice público `SARI-001`;
- método de scoring `SCORE-GEO-004`;
- `report/readiness.html` como superfície canônica do índice;
- `report/scoring.html` como superfície canônica da metodologia;
- HTML em português do Brasil, mantendo em inglês apenas nomes técnicos consolidados, identificadores, APIs, formatos e termos cujo uso técnico melhora a precisão.

A arquitetura de produto inclui Product Platform, SQLite local, PostgreSQL centralizado opt-in, Web API, workers, SaaS Pilot Web, Scheduling Management, Consumption Analytics, acesso remoto ao control plane e Identity & Access baseada em OIDC/JWT com vínculo explícito entre identidade externa e `USR-*`. Essas camadas preservam a separação entre control plane, scoring e evidência imutável de auditoria.

## Regra documental de pré-publicação

A documentação normativa deve representar **o produto como ele existe agora**.

Não documentar como contrato público:

- branches ou PRs usados para implementar uma capacidade;
- nomenclaturas internas de etapas de entrega;
- caminhos/aliases descartados durante desenvolvimento;
- defaults substituídos;
- comportamento mantido apenas para acomodar artefatos de desenvolvimento;
- versões de scoring que não sejam o contrato vigente.

Histórico é documentado somente quando é uma **funcionalidade do produto**, por exemplo séries temporais, Evidence Timeline, Search Intelligence History e comparações before/after. Isso é diferente de manter histórico de implementação.

## Ordem de leitura recomendada

1. [`REPORT_GUIDE.md`](REPORT_GUIDE.md) - contrato dos relatórios e como interpretar os indicadores.
2. [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) - identidade pública e limites do SARI.
3. [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SCORE_GEO_004.md`](SCORE_GEO_004.md) - fórmula, Coverage/Cobertura, Confidence/Confiança e gates.
4. [`RULES_GUIDE.md`](RULES_GUIDE.md) e [`DISCOVERY_RESOURCES.md`](DISCOVERY_RESOURCES.md) - regras BR-GEO, evidências, aplicabilidade e topologia de `robots.txt`, múltiplos sitemaps e `llms.txt` raiz/scoped.
5. [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md) e [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md) - experiência sintética independente do SARI.
6. [`ACCESSIBILITY_PERFORMANCE_DOMAINS.md`](ACCESSIBILITY_PERFORMANCE_DOMAINS.md), [`LIGHTHOUSE_WEB_QUALITY.md`](LIGHTHOUSE_WEB_QUALITY.md) e [`LIGHTHOUSE_CATEGORIES.md`](LIGHTHOUSE_CATEGORIES.md) - fronteiras entre Performance, Accessibility, Best Practices, SEO técnico, Agentic Browsing experimental, Core Web Vitals e readiness.
7. [`SERP_OBSERVATION.md`](SERP_OBSERVATION.md), [`COMPETITIVE_SEARCH_INTELLIGENCE.md`](COMPETITIVE_SEARCH_INTELLIGENCE.md), [`COMPETITIVE_AI_INTELLIGENCE.md`](COMPETITIVE_AI_INTELLIGENCE.md), [`SEARCH_INTELLIGENCE_REPORT.md`](SEARCH_INTELLIGENCE_REPORT.md), [`SEARCH_INTELLIGENCE_HISTORY.md`](SEARCH_INTELLIGENCE_HISTORY.md) e [`SEARCH_INTELLIGENCE_MONITORING.md`](SEARCH_INTELLIGENCE_MONITORING.md) - observação SERP, comparação determinística, recomendações semânticas evidence-bound, superfície HTML, comparação temporal before/after e monitoramento recorrente por query registrada.
8. [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md) - séries, comparabilidade e relatório longitudinal.
9. [`AI_GUIDE.md`](AI_GUIDE.md), [`AI_PROVIDER_EXTENSIONS.md`](AI_PROVIDER_EXTENSIONS.md) e [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md) - uso de IA, contexto e limites.
10. [`TECHNICAL_GUIDE.md`](TECHNICAL_GUIDE.md), [`CONFIGURATION.md`](CONFIGURATION.md), [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md), [`CLI_REFERENCE.md`](CLI_REFERENCE.md), [`PRODUCT_PLATFORM_ARCHITECTURE.md`](PRODUCT_PLATFORM_ARCHITECTURE.md), [`POSTGRESQL_MIGRATION_STRATEGY.md`](POSTGRESQL_MIGRATION_STRATEGY.md), [`POSTGRESQL_LOCAL_DEVELOPMENT.md`](POSTGRESQL_LOCAL_DEVELOPMENT.md), [`WEB_API_FOUNDATION.md`](WEB_API_FOUNDATION.md), [`WEB_API_CLI.md`](WEB_API_CLI.md), [`SAAS_PILOT_WEB.md`](SAAS_PILOT_WEB.md) e [`IDENTITY_AND_ACCESS.md`](IDENTITY_AND_ACCESS.md) - operação, arquitetura do control plane, implantação, desenvolvimento local, estratégia PostgreSQL, evolução Web/API/worker e identidade SaaS.
11. [`specification/00_SPEC_INDEX.md`](specification/00_SPEC_INDEX.md) - especificação técnica detalhada.

## Convenção de linguagem de relatório

Enums e estados persistidos continuam em sua forma canônica no banco e em interfaces técnicas. Na interface HTML, valores de máquina conhecidos são apresentados com rótulos amigáveis. Exemplos:

| Valor persistido | Exibição no HTML |
|---|---|
| `SINGLE_PROVIDER` | Provedor único |
| `PASS` | Aprovado |
| `WARNING` | Alerta |
| `NOT_CONSOLIDATED` | Não consolidado |
| `NOT_APPLICABLE` | Não aplicável |
| `BOUNDED_AI_RESOURCE_ASSESSMENT` | Avaliação por IA com escopo limitado |

Blocos `code`/`pre`, nomes de variáveis, IDs de regras, versões e contratos técnicos não são traduzidos, porque fazem parte da rastreabilidade.

## Semântica visual

Relatórios usam um contrato global de estados:

- **verde**: resultado conclusivo e aprovado/consolidado;
- **amarelo/laranja**: alerta, resultado parcial, degradação ou condição que exige observação;
- **vermelho**: reprovação, falha ou erro que exige ação;
- **azul/neutro**: indisponibilidade, não aplicabilidade ou informação que não deve ser interpretada como falha do website.

A cor é apoio de leitura. O valor persistido, a evidência, o critério e a explicação textual prevalecem.

## Referências públicas primárias

As referências abaixo sustentam domínios específicos; nenhuma delas homologa o índice proprietário SARI/SCORE-GEO:

- Google Search Central: https://developers.google.com/search/docs
- Google Search - dados estruturados: https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
- RFC 9309 - Robots Exclusion Protocol: https://www.rfc-editor.org/rfc/rfc9309
- Sitemap protocol: https://www.sitemaps.org/protocol.html
- Schema.org: https://schema.org/
- Chrome Lighthouse: https://developer.chrome.com/docs/lighthouse/
- Lighthouse Performance: https://developer.chrome.com/docs/lighthouse/performance/performance-scoring
- Lighthouse Accessibility: https://developer.chrome.com/docs/lighthouse/accessibility/scoring
- Lighthouse Best Practices: https://developer.chrome.com/docs/lighthouse/best-practices/
- Lighthouse SEO: https://developer.chrome.com/docs/lighthouse/seo/
- Lighthouse Agentic Browsing (experimental source/config): https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js
- Web Vitals: https://web.dev/vitals/
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Apdex: https://www.apdex.org/
- llms.txt community proposal: https://llmstxt.org/

Consulte também `report/references.html` de cada auditoria: ele materializa a proveniência aplicável à execução, enquanto estes documentos descrevem o contrato do produto.
