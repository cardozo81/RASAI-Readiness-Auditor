# Documentação do RASAi

## Estado do produto

O RASAi está em **desenvolvimento e validação**. Nenhuma combinação anterior de `SARI`, `SCORE-GEO`, relatório ou contrato interno deve ser descrita como uma versão pública legada, obsoleta ou anteriormente lançada. Quando dados de testes anteriores precisam ser preservados para reprodutibilidade, eles são tratados como **referências de desenvolvimento anteriores** e permanecem identificados pela versão persistida que efetivamente os produziu.

O baseline funcional vigente usa:

- índice público `SARI-001`;
- método de scoring `SCORE-GEO-004` para novas auditorias;
- `report/readiness.html` como superfície canônica do índice;
- `report/scoring.html` como superfície canônica da metodologia;
- `report/score-geo-004.html` somente como alias interno de compatibilidade durante o desenvolvimento;
- HTML em português do Brasil, mantendo em inglês apenas nomes técnicos consolidados, identificadores, APIs, formatos e termos cujo uso técnico melhora a precisão.

## Ordem de leitura recomendada

1. [`REPORT_GUIDE.md`](REPORT_GUIDE.md) - contrato dos relatórios e como interpretar os indicadores.
2. [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) - identidade pública e limites do SARI.
3. [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SCORE_GEO_004.md`](SCORE_GEO_004.md) - fórmula, Coverage/Cobertura, Confidence/Confiança e gates.
4. [`RULES_GUIDE.md`](RULES_GUIDE.md) - regras BR-GEO, evidências e aplicabilidade.
5. [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md) e [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md) - experiência sintética independente do SARI.
6. [`ACCESSIBILITY_PERFORMANCE_DOMAINS.md`](ACCESSIBILITY_PERFORMANCE_DOMAINS.md) - fronteiras entre performance, acessibilidade e readiness.
7. [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md) - séries, comparabilidade e relatório histórico.
8. [`AI_GUIDE.md`](AI_GUIDE.md), [`AI_PROVIDER_EXTENSIONS.md`](AI_PROVIDER_EXTENSIONS.md) e [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md) - uso de IA, contexto e limites.
9. [`TECHNICAL_GUIDE.md`](TECHNICAL_GUIDE.md), [`CONFIGURATION.md`](CONFIGURATION.md), [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) e [`CLI_REFERENCE.md`](CLI_REFERENCE.md) - operação e implantação.
10. [`specification/00_SPEC_INDEX.md`](specification/00_SPEC_INDEX.md) - especificação técnica detalhada.

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
- Web Vitals: https://web.dev/vitals/
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Apdex: https://www.apdex.org/

Consulte também `report/references.html` de cada auditoria: ele deve materializar a proveniência aplicável à execução, enquanto estes documentos descrevem o contrato do produto.
