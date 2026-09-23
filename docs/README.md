# Documentação do RASAi

## Estado do produto

O RASAi está em **desenvolvimento e validação pré-publicação**. A documentação descreve exclusivamente o contrato vigente do produto e deve ser lida como definição do estado atual, sem pressupor versões públicas anteriores.

O contrato funcional vigente usa:

- índice público `SARI-001`;
- método de scoring `SCORE-GEO-004`;
- `report-catalog/sari.html` como superfície canônica do índice;
- `report-catalog/methodology.html` como superfície canônica da metodologia/scoring;
- `report-catalog/index.html` como visão executiva;
- UTC como referência temporal canônica de persistência/processamento e `America/Sao_Paulo` como timezone padrão de apresentação, conforme [`TIMEZONE_CONTRACT.md`](TIMEZONE_CONTRACT.md);
- HTML e documentação contextual em português do Brasil, mantendo em inglês apenas nomes técnicos consolidados, identificadores, APIs, formatos, comandos, enums e termos cuja tradução reduziria precisão ou quebraria rastreabilidade.

A arquitetura de produto inclui Product Platform, SQLite local, PostgreSQL centralizado opt-in, Web API, workers, SaaS Pilot Web, Scheduling Management, Consumption Analytics, acesso remoto ao control plane e Identity & Access baseada em OIDC/JWT com vínculo explícito entre identidade externa e `USR-*`. Essas camadas preservam a separação entre control plane, scoring e evidência imutável de auditoria.

## Regra documental de pré-publicação

A documentação normativa deve representar **o produto como ele existe agora**.

Não documentar como contrato público:

- branch, PR ou mecanismo de entrega usado para implementar uma capacidade;
- nomenclatura interna de etapa de desenvolvimento;
- caminho, alias ou default que não faça parte do runtime vigente;
- comportamento sem função no produto atual;
- versão de scoring que não seja o contrato vigente.

Séries temporais, Evidence Timeline, Search Intelligence History e comparações before/after são funcionalidades do produto e podem ser documentadas por fazerem parte do comportamento vigente.

## Avaliações arquiteturais futuras

Documentos desta seção **não representam contrato funcional vigente nem compromisso de implementação**. Eles registram gaps e decisões ainda abertas para revisão futura.

- [`SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md`](SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md) - consolida o estado atual, gaps e requisitos candidatos para Runner gerenciado pelo SaaS, persistência central de evidências/artefatos e possível renderização dinâmica de relatórios. Rastreabilidade: [GitHub Issue #163](https://github.com/cardozo81/RASAI-Readiness-Auditor/issues/163).

Cada avaliação futura deve ser encerrada por decisão explícita de implementar, substituir, manter pendente ou descontinuar; até essa decisão, o contrato implementado e a documentação vigente prevalecem.

## Protótipos Web

A pasta `prototypes/` contém superfícies frontend-only para validação de UI, UX, navegação e contratos desejados. Ela não redefine o comportamento do core, do control plane, do console ou da Web API.

Quando um protótipo representar uma capacidade já existente, deve apontar para o contrato real correspondente. Quando representar uma capacidade ainda não oferecida pelo SaaS, o documento deve identificá-la explicitamente como contrato desejado do protótipo, sem apresentá-la como endpoint ou funcionalidade disponível.

Nenhum mock, tipo TypeScript ou fluxo visual em `prototypes/` tem precedência sobre o runtime Python, os testes e a especificação normativa vigente.

## Convenção obrigatória de idioma para `*.md`

Todo texto explicativo, normativo, operacional ou de negócio dos arquivos Markdown deve estar em **pt-BR**, com acentuação, cedilha e terminologia adequada ao português do Brasil.

Podem permanecer em inglês quando correspondem ao valor ou termo técnico real:

- nomes oficiais de produtos, APIs, bibliotecas, padrões e especificações;
- identificadores de contrato e metodologia;
- IDs de regras e evidências;
- nomes de tabelas, campos, arquivos, classes, funções e módulos;
- comandos, parâmetros de CLI e variáveis de ambiente;
- enums e estados persistidos;
- payloads, snippets e exemplos que precisem reproduzir literalmente uma interface técnica;
- termos de engenharia amplamente usados quando a tradução prejudicar precisão, desde que o contexto ao redor permaneça em pt-BR.

Títulos descritivos, status editoriais e explicações **não** devem permanecer integralmente em inglês apenas por tratarem de tema técnico. Quando um nome técnico persistido em inglês precisar ser mostrado, o texto em pt-BR deve esclarecer seu significado sem alterar o valor canônico.

## Direitos autorais, citações e traduções de fontes externas

Conteúdo externo permanece de titularidade de seu respectivo autor, mantenedor ou entidade publicadora. Uma referência do RASAi a Google, W3C, IETF, OpenAI, Microsoft, Dynatrace, Apdex, Schema.org ou qualquer outra fonte **não transfere autoria, licença ou propriedade intelectual** ao projeto.

Quando a documentação precisar reproduzir texto externo protegido para preservar precisão técnica:

1. reproduzir **somente o trecho estritamente necessário** para sustentar a explicação;
2. identificar claramente a fonte e fornecer o link primário quando disponível;
3. apresentar o trecho original como citação, sem alterá-lo;
4. imediatamente após a citação, fornecer **tradução/adaptação pt-BR** contextualizada para o RASAi;
5. informar que a tradução é explicativa e que, em caso de divergência, prevalece o texto oficial da fonte;
6. não reproduzir obra, página, manual, artigo ou documentação integral quando um excerto suficiente atender à finalidade documental, salvo quando a licença da fonte permitir explicitamente e houver necessidade técnica concreta.

Quando houver reprodução, tradução ou adaptação específica de texto protegido em uma seção, essa seção deve conter o seguinte aviso, ou redação equivalente com o mesmo sentido:

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

Uma simples lista de links, nomes de APIs, nomes de padrões, títulos de documentos ou valores técnicos não exige esse bloco local por si só. O bloco é obrigatório quando houver **texto externo efetivamente reproduzido ou traduzido/adaptado**.

### Referências externas em outro idioma

Links para referências externas podem permanecer no idioma da fonte e **não exigem reprodução integral da página externa**.

Quando for indispensável reproduzir no Markdown um trecho externo que não esteja em pt-BR, a documentação deve usar duas partes:

1. **Disclaimer - texto original da fonte:** trecho estritamente necessário e fiel ao original;
2. **Tradução/adaptação pt-BR:** explicação do conteúdo em português no contexto do RASAi.

Não copiar uma obra externa inteira quando apenas um trecho é necessário para sustentar o contrato. O link, a identificação da fonte e a tradução contextual devem ser preservados.

## Convenção obrigatória para valores configuráveis

Sempre que um `*.md` publicar variável, parâmetro, threshold, limite, enum configurável ou valor semelhante, deve deixar inequívoco, quando aplicável:

- **Default efetivo:** valor realmente usado pelo runtime quando o operador não fornece override;
- **Valores permitidos:** conjunto, tipo ou faixa realmente aceitos pela validação do código;
- **Recomendado:** valor ou política indicada para o cenário documentado;
- **Obrigatoriedade/dependência:** quando a configuração só passa a ser exigida porque uma capacidade foi habilitada;
- **Impacto operacional:** custo, carga, segurança, quota, latência ou reprodutibilidade quando relevante.

Se não existe default tecnicamente seguro, a documentação deve declarar **“sem default”**. Não inventar um valor apenas para preencher a tabela.

Se o runtime aceita aliases mas existe um valor canônico, ambos devem ser distinguidos. Exemplo: o compositor do control plane aceita `postgres`/`pg` como aliases, mas o valor canônico documentado é `postgresql`.

A referência central consolidada de variáveis é [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md). Para credenciais, tokens, API keys, criação no fornecedor, finalidade funcional e links oficiais, a referência central é [`EXTERNAL_CREDENTIALS.md`](EXTERNAL_CREDENTIALS.md).

## Ordem de leitura recomendada

1. [`GLOSSARY.md`](GLOSSARY.md) - siglas, identificadores, taxonomia e significado dos termos usados pelo RASAi.
2. [`CATALOG_AND_REPORT_SURFACES.md`](CATALOG_AND_REPORT_SURFACES.md) e [`REPORT_GUIDE.md`](REPORT_GUIDE.md) - contrato uniforme de CAT-01 a CAT-10, páginas transversais e interpretação do relatório.
3. [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) - definição, versão pública 001 e limites do **Índice de Prontidão Search & IA** (`SARI-001`).
4. [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SCORE_GEO_004.md`](SCORE_GEO_004.md) - **Método de Pontuação de Prontidão**, versão pública 001, fórmula, Cobertura, Confiança e critérios críticos; `SCORE-GEO-004` permanece como contrato técnico.
5. [`RULES_GUIDE.md`](RULES_GUIDE.md) e [`DISCOVERY_RESOURCES.md`](DISCOVERY_RESOURCES.md) - **Regras de Avaliação de Prontidão** (IDs técnicos `BR-GEO-*`), evidências, aplicabilidade e topologia de `robots.txt`, múltiplos sitemaps e `llms.txt` raiz/scoped.
6. [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md) e [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md) - experiência sintética independente do SARI.
7. [`ACCESSIBILITY_PERFORMANCE_DOMAINS.md`](ACCESSIBILITY_PERFORMANCE_DOMAINS.md), [`LIGHTHOUSE_WEB_QUALITY.md`](LIGHTHOUSE_WEB_QUALITY.md) e [`LIGHTHOUSE_CATEGORIES.md`](LIGHTHOUSE_CATEGORIES.md) - fronteiras entre Performance, Accessibility, Best Practices, SEO técnico, Agentic Browsing experimental, Core Web Vitals e readiness.
8. [`SERP_OBSERVATION.md`](SERP_OBSERVATION.md), [`CONSOLE_SEARCH_INTELLIGENCE.md`](CONSOLE_SEARCH_INTELLIGENCE.md), [`COMPETITIVE_SEARCH_INTELLIGENCE.md`](COMPETITIVE_SEARCH_INTELLIGENCE.md), [`COMPETITIVE_AI_INTELLIGENCE.md`](COMPETITIVE_AI_INTELLIGENCE.md), [`SEARCH_INTELLIGENCE_REPORT.md`](SEARCH_INTELLIGENCE_REPORT.md), [`SEARCH_INTELLIGENCE_HISTORY.md`](SEARCH_INTELLIGENCE_HISTORY.md) e [`SEARCH_INTELLIGENCE_MONITORING.md`](SEARCH_INTELLIGENCE_MONITORING.md) - observação SERP, entrada de termos no console, comparação determinística, recomendações semânticas vinculadas a evidências, superfície HTML, comparação temporal before/after e monitoramento recorrente por query registrada.
9. [`MONITORING_CAPABILITIES.md`](MONITORING_CAPABILITIES.md) e [`MONITORING_OBSERVABILITY.md`](MONITORING_OBSERVABILITY.md) - capacidades vigentes de Monitoring, Observability, Quality, Fix Verification, Evidence Timeline e seus limites em relação ao SARI.
10. [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md) - séries, comparabilidade e relatório longitudinal.
11. [`AI_GUIDE.md`](AI_GUIDE.md), [`AI_RUNTIME_ORCHESTRATION.md`](AI_RUNTIME_ORCHESTRATION.md), [`GOVERNED_EVIDENCE_AI_PIPELINE.md`](GOVERNED_EVIDENCE_AI_PIPELINE.md), [`AI_PROVIDER_EXTENSIONS.md`](AI_PROVIDER_EXTENSIONS.md), [`PROVIDER_SETUP.md`](PROVIDER_SETUP.md), [`EXTERNAL_CREDENTIALS.md`](EXTERNAL_CREDENTIALS.md) e [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md) - uso de IA, orquestração, evidência governada, providers, credenciais, contexto e limites.
12. [`AUDIT_REPROCESSING.md`](AUDIT_REPROCESSING.md), [`INTERACTIVE_CONSOLE.md`](INTERACTIVE_CONSOLE.md), [`EXECUTION_SCHEDULING.md`](EXECUTION_SCHEDULING.md), [`INTEGRATION_DIAGNOSTICS.md`](INTEGRATION_DIAGNOSTICS.md), [`DIRECTED_ANALYSIS.md`](DIRECTED_ANALYSIS.md) e [`PASSIVE_SECURITY_CATALOG.md`](PASSIVE_SECURITY_CATALOG.md) - reprocessamento seletivo, operação no console, diagnóstico de integrações, análise estratégica e segurança passiva.
13. [`UX_CONFIGURATION_AND_REPORTS.md`](UX_CONFIGURATION_AND_REPORTS.md), [`TECHNICAL_GUIDE.md`](TECHNICAL_GUIDE.md), [`CONFIGURATION.md`](CONFIGURATION.md), [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md), [`CLI_REFERENCE.md`](CLI_REFERENCE.md), [`TIMEZONE_CONTRACT.md`](TIMEZONE_CONTRACT.md), [`PRODUCT_PLATFORM_ARCHITECTURE.md`](PRODUCT_PLATFORM_ARCHITECTURE.md), [`POSTGRESQL_MIGRATION_STRATEGY.md`](POSTGRESQL_MIGRATION_STRATEGY.md), [`POSTGRESQL_LOCAL_DEVELOPMENT.md`](POSTGRESQL_LOCAL_DEVELOPMENT.md), [`WEB_API_FOUNDATION.md`](WEB_API_FOUNDATION.md), [`WEB_API_CLI.md`](WEB_API_CLI.md), [`SAAS_PILOT_WEB.md`](SAAS_PILOT_WEB.md) e [`IDENTITY_AND_ACCESS.md`](IDENTITY_AND_ACCESS.md) - UX de configuração/execução/relatórios, operação, tempo/timezone, arquitetura do control plane, implantação, desenvolvimento local, estratégia PostgreSQL, Web/API/worker e identidade SaaS.
14. [`specification/00_SPEC_INDEX.md`](specification/00_SPEC_INDEX.md) - especificação técnica detalhada.
15. [`../prototypes/README.md`](../prototypes/README.md) - escopo dos protótipos frontend-only e fronteira entre contratos atuais e contratos desejados.

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

Blocos `code`/`pre`, nomes de variáveis, IDs de regras, versões e contratos técnicos não são traduzidos porque fazem parte da rastreabilidade.

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
- Lighthouse Agentic Browsing (fonte/configuração experimental): https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js
- Web Vitals: https://web.dev/vitals/
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Apdex: https://www.apdex.org/
- proposta comunitária `llms.txt`: https://llmstxt.org/

Consulte também as páginas de governança de `report-catalog/`, especialmente metodologia, evidências da execução e IA/integrações; elas materializam a proveniência aplicável à execução, enquanto estes documentos descrevem o contrato do produto.