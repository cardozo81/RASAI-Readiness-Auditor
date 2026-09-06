# SearchGEO Readiness Auditor — Specification Index

**Status:** APPROVED BASELINE + M14/M15/M16/M17/M18/M20/M21/M22/M23/M24 + SCORE-GEO-002 + SGRI-001 + REPORT-SITE-GEO-001  
**Baseline:** MVP Functional Specification  
**Idioma normativo:** Português, preservando identificadores e termos técnicos quando necessário.

## 1. Objetivo

Este diretório constitui a fonte normativa do SearchGEO Readiness Auditor.

Uma IA, desenvolvedor ou ferramenta que assuma o projeto não deve depender do histórico de chats para descobrir requisitos formalizados.

Os documentos presentes neste diretório prevalecem sobre interpretações informais do histórico de conversa.

## 2. Ordem obrigatória de leitura

1. `00_SPEC_INDEX.md`
2. `12_AI_HANDOFF.md`
3. `10_DECISIONS.md`
4. `01_PROJECT_CHARTER_SCOPE.md`
5. `07_FUNCTIONAL_REQUIREMENTS.md`
6. `02_DOMAIN_MODEL.md`
7. `03_BUSINESS_RULES.md`
8. `04_WORKFLOWS.md`
9. `05_SCORING_MODEL.md`
10. `06_PRIORITIZATION_MODEL.md`
11. `08_TECHNICAL_ARCHITECTURE.md`
12. `09_IMPLEMENTATION_PLAN.md`
13. `11_REPORTING_LANGUAGE_GLOSSARY.md`
14. `13_MODEL_ROUTING_POLICY.md`
15. `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md`
16. `15_ERROR_CENTRIC_REPORT_UX.md`
17. `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md`
18. `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md`
19. `18_MULTI_AI_PROVIDER_ROUTING.md`
20. `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`
21. `20_AI_CONTENT_REMEDIATION.md`
22. `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`
23. `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`
24. `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`
25. `24_CRAWLING_DISCOVERY_AI_ACCESS.md`

## 3. Precedência documental

Em caso de conflito:

1. decisões explicitamente aprovadas em `10_DECISIONS.md`;
2. requisitos funcionais em `07_FUNCTIONAL_REQUIREMENTS.md`;
3. escopo em `01_PROJECT_CHARTER_SCOPE.md`;
4. modelos normativos de domínio, regras, workflows, scoring e priorização;
5. arquitetura técnica;
6. plano de implementação;
7. AI handoff e política operacional de modelos;
8. especificações de evolução de marco, quando não conflitarem com os itens anteriores.

Nenhuma decisão funcional deve ser alterada silenciosamente durante implementação.

## 4. Documentos

### `01_PROJECT_CHARTER_SCOPE.md`
Propósito, escopo, princípios, exclusões e critérios de aceite.

### `02_DOMAIN_MODEL.md`
Entidades, relacionamentos, identificadores, estados e invariantes.

### `03_BUSINESS_RULES.md`
Business Rules `BR-GEO-001` a `BR-GEO-054`.

### `04_WORKFLOWS.md`
Workflows `WF-GEO-001` a `WF-GEO-012` e ordem de execução.

### `05_SCORING_MODEL.md`
Score, Coverage, Confidence, Consolidation, aplicabilidade e agregações. Baseline vigente: `SCORE-GEO-002`. Confidence representa força da conclusão, não qualidade textual isolada.

### `06_PRIORITIZATION_MODEL.md`
Severity, Impact, Effort, Confidence e Priority.

### `07_FUNCTIONAL_REQUIREMENTS.md`
Requisitos `FR-GEO-*` e `NFR-GEO-*`. Inclui device context, report site, contrato M20 de remediação opcional, M21 de evidência externa, fronteiras M22, M23 Synthetic Navigation Apdex e M24 Crawling/Discovery sem alterar scoring GEO.

### `08_TECHNICAL_ARCHITECTURE.md`
Arquitetura local/modular, seleção de dispositivo, finalização do report site, M20 downstream de scoring/findings, M21 externo não-scoring, projeção M22, M23 Synthetic Navigation Apdex/rastreabilidade Lighthouse e M24 técnico não-scoring.

### `09_IMPLEMENTATION_PLAN.md`
Baseline de marcos e evoluções formalizadas. Quando descrição histórica de output conflitar com `FR-GEO-046`/REPORT-SITE-GEO-001, prevalece o contrato final `report/`.

### `10_DECISIONS.md`
Decisões humanas consolidadas e pendências corporativas. D-037 formaliza `SCORE-GEO-002`; M21/M22/M23/M24 não o substituem nem recalibram implicitamente.

### `11_REPORTING_LANGUAGE_GLOSSARY.md`
Linguagem e apresentação do relatório.

### `12_AI_HANDOFF.md`
Instruções para continuidade por IA/desenvolvedor.

### `13_MODEL_ROUTING_POLICY.md`
Política de uso de modelos conforme esforço/criticidade.

### `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md`
M14: multi-URL, recursos de domínio, screenshots, ElementObservation, actionability, referências e distinção entre zero calculado e ausência de cálculo.

### `15_ERROR_CENTRIC_REPORT_UX.md`
M15 histórico evoluído por `REPORT-SITE-GEO-001`: visão por domínio, páginas Mobile/Desktop, remediação, telemetria IA, referências, menu compartilhado e CSS externo.

### `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md`
M16: causa raiz evidence-backed, localização, observado versus esperado, mudança exata, aceite e revalidação.

### `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md`
M17: reason code, observado versus alvo técnico, consistência e redução de duplicação.

### `18_MULTI_AI_PROVIDER_ROUTING.md`
M18: multi-provider, routing determinístico, failover, quarantine, URL lock e telemetria. Não altera scoring.

### `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`
`SCORE-GEO-002`, `NOT_APPLICABLE` versus `NOT_CONSOLIDATED`, JSON-LD opcional e premissas mínimas/contextuais.

### `20_AI_CONTENT_REMEDIATION.md`
M20: sugestões textuais opcionais/evidence-bound, default OFF, separação de scoring, reutilização do routing M18, telemetria por finalidade e orientação determinística de JSON-LD.

### `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`
M21: coleta opcional de Lighthouse/PageSpeed e Core Web Vitals/CrUX, persistência própria, artifacts, `report/web-performance.html`, zero chamadas LLM adicionais e separação rígida de `SCORE-GEO-002`.

### `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`
M22: projeção separada de Acessibilidade e Web Performance a partir dos artifacts M21, `report/accessibility.html`, diagnóstico técnico e regra de não inferência de Apdex a partir de Lighthouse/CrUX.

### `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`
M23 integrado: Synthetic Navigation Apdex com Task/`T`/amostras explícitas, profiles determinísticos, pacing/concorrência limitados, `report/apdex.html`, rastreabilidade de `lighthouseResult.configSettings` e separação rígida de `SCORE-GEO-002`.

### `24_CRAWLING_DISCOVERY_AI_ACCESS.md`
M24 integrado: diagnóstico determinístico de robots/crawlers/sitemaps/discovery, `llms.txt` experimental, IndexNow não determinável sem evidência explícita, remediação técnica por IA default OFF e `report/crawling-discovery.html`, sempre separado de scoring.

## 5. REPORT-SITE-GEO-001

A evolução de apresentação está formalizada pelos requisitos de report site e pelos marcos M20/M21/M22/M23/M24. O contrato final continua condicional por existência do arquivo.

```text
<AUD-ID>/report/index.html
<AUD-ID>/report/searchgeo.html           # SGRI-001 / SearchGEO
<AUD-ID>/report/mobile.html              # condicional
<AUD-ID>/report/desktop.html             # condicional
<AUD-ID>/report/remediation.html
<AUD-ID>/report/content-suggestions.html
<AUD-ID>/report/crawling-discovery.html  # M24
<AUD-ID>/report/accessibility.html       # M22, condicional
<AUD-ID>/report/web-performance.html
<AUD-ID>/report/apdex.html               # M23, condicional
<AUD-ID>/report/ai-usage.html
<AUD-ID>/report/references.html
<AUD-ID>/report/css/site.css
```

Default de dispositivo da CLI: `mobile`. `desktop` e `both` são seleções explícitas/parametrizáveis.

## 6. Fonte externa e heurística

O SearchGEO não deve representar seu score ou thresholds como standard GEO/AEO universal.

Referências primárias atuais incluem Google Search Central/Crawling Infrastructure, OpenAI Help Center, Schema.org, WHATWG, IETF/RFC, Chrome Developers, PageSpeed Insights, Chrome UX Report, W3C/WAI e, exclusivamente para a semântica Apdex, a especificação pública da Apdex Alliance.

Structured Data/JSON-LD é reforço opcional, não requisito universal GEO. Quando M20 propõe ou revisa JSON-LD, deve usar somente conteúdo/evidência persistidos.

M21 introduz métricas externas documentadas para fenômenos específicos. Lighthouse e Core Web Vitals não homologam `SCORE-GEO-002` e não são combinados silenciosamente com ele.

M22 mantém Acessibilidade e Web Performance independentes do GEO. Acessibilidade automatizada Lighthouse não equivale a conformidade WCAG.

M23 resolve a lacuna de Apdex sem inferi-lo de Lighthouse/CrUX: usa Task de navegação, `T` explícito e tempos sintéticos repetidos. Synthetic Apdex é evidência separada do Score GEO e não equivale a RUM/APM de usuários reais.

M24 usa RFC 9309, Google Search/Crawling Infrastructure, OpenAI publisher guidance e protocolos públicos para fundamentar os fenômenos técnicos. `llms.txt` permanece proposta comunitária experimental e a sua ausência não é requisito/falha de SearchGEO.

Heurísticas BR-GEO sem equivalente normativo devem permanecer identificadas como heurísticas/baseline interna.

## 7. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context público, conteúdo sugerido por IA, consumo externo M21, fronteiras M22, carga sintética M23, aquisição/política M24 ou requisitos corporativos devem ser reconciliadas nesta baseline antes da conclusão do merge.

Decisões puramente internas de implementação podem ser tomadas sem aprovação humana quando não alterarem comportamento funcional.

## M18 — Multi-AI Provider Abstraction, Reliability Routing & Usage Telemetry

Fonte normativa: `18_MULTI_AI_PROVIDER_ROUTING.md`. M18 não altera Business Rules, PRIORITY-GEO-001, actionability nem semântica de UNKNOWN.

## SCORE-GEO-002 — Aplicabilidade e premissas mínimas GEO

Fonte normativa: `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md`. Dimensões integralmente e legitimamente `NOT_APPLICABLE` não bloqueiam nem reduzem o Overall.

## M20 — Optional AI Content Remediation + JSON-LD Guidance

Fonte normativa: `20_AI_CONTENT_REMEDIATION.md`. Sugestões textuais são default OFF, downstream de scoring e dependentes de finding/evidência. Revisão JSON-LD é determinística e disponível sem provider externo.

## M21 — External Web Performance Evidence

Fonte normativa: `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md`.

M21:

- default OFF;
- PageSpeed Insights/Lighthouse e CrUX quando habilitado/configurado;
- limite de páginas, timeout e política de field data configuráveis;
- zero chamadas LLM;
- telemetria e raw artifacts próprios;
- `report/web-performance.html`;
- não altera RuleExecution, Finding, Recommendation, Score, Coverage, Confidence, Consolidation ou `SCORE-GEO-002`.

## M22 — Domain-Separated Web Quality Diagnostics

Fonte normativa: `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md`.

M22:

- reutiliza artifacts PageSpeed/Lighthouse M21;
- zero chamadas externas adicionais e zero chamadas LLM;
- cria `report/accessibility.html` como domínio separado;
- mantém Performance em `report/web-performance.html`;
- projeta selector/snippet/URL/savings somente quando fornecidos pela fonte;
- não inventa selector ausente;
- não declara conformidade WCAG a partir de Lighthouse;
- **não calcula Apdex a partir de Lighthouse/CrUX**;
- não altera `BR-GEO-*`, RuleExecution, Finding GEO, Recommendation GEO ou `SCORE-GEO-002`.

Após M23, a frase “M22 não calcula Apdex” deve ser lida como fronteira de origem/metodologia: o cálculo Synthetic Apdex pertence exclusivamente ao M23.

## M23 — Synthetic Navigation Apdex + Lighthouse Traceability

Fonte normativa: `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`.

M23:

- está integrado ao baseline;
- default OFF;
- exige `T` explícito quando habilitado;
- mede `NAVIGATION_LOAD` em BrowserContext frio por amostra;
- usa profiles CPU/rede determinísticos e versionados;
- limita concorrência a 2 e possui pacing configurável;
- usa 100 amostras válidas por contexto como grupo final normal default;
- marca grupos 1–99 com `small_group=*`;
- persiste runs, samples, summaries e configuração Lighthouse observada;
- não chama LLM, PageSpeed ou CrUX por si só;
- cria `report/apdex.html` quando habilitado;
- é fail-open em relação à auditoria principal;
- não altera `BR-GEO-*`, RuleExecution, Finding GEO, Recommendation GEO ou `SCORE-GEO-002`;
- teve smoke humano controlado aprovado antes da integração em `main`;
- exige autorização específica para carga relevante em produção.

## M24 — Crawling, Discovery & AI Access

Fonte normativa: `24_CRAWLING_DISCOVERY_AI_ACCESS.md`.

M24:

- está integrado ao baseline;
- executa diagnóstico determinístico de robots/crawlers/sitemaps/discovery;
- suporta XML, sitemap index, gzip, RSS 2.0, Atom 1.0 e sitemap texto no runtime M24;
- preserva declaração de sitemap externo sem fazer fetch cross-origin automático;
- trata `llms.txt` como proposta comunitária experimental e non-scoring;
- separa Googlebot, OAI-SearchBot, GPTBot e Google-Extended conforme finalidade documentada;
- não infere configuração/submissão IndexNow sem evidência explícita;
- disponibiliza `--ai-technical-remediation`/`SEARCHGEO_AI_TECHNICAL_REMEDIATION`, default OFF;
- cria `report/crawling-discovery.html`;
- persiste dados aditivos M24 e mantém `scoring_impact=NONE`;
- é fail-open e respeita hard source blocker;
- não altera `BR-GEO-*`, RuleExecution, Finding GEO, Recommendation GEO, `SCORE-GEO-002` ou `SGRI-001`.
