# RASAI — Search & AI Readiness Auditor — Specification Index

**Status:** BASELINE VIGENTE — capacidades integradas e documentação reconciliada com `main` + candidato PR #82.
**Baseline:** MVP Functional Specification
**Idioma normativo:** Português, preservando identificadores e termos técnicos quando necessário.

## 1. Objetivo

Este diretório constitui a fonte normativa do RASAI — Search & AI Readiness Auditor.

Uma IA, desenvolvedor ou ferramenta que assuma o projeto não deve depender do histórico de chats para descobrir requisitos formalizados. Os documentos presentes neste diretório prevalecem sobre interpretações informais do histórico de conversa.

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
26. `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md`
27. `26_OBSERVED_GENERATIVE_VISIBILITY.md`
28. `27_MONITORING_OBSERVABILITY.md`

## 3. Precedência documental

Em caso de conflito:

1. decisões explicitamente aprovadas em `10_DECISIONS.md`;
2. requisitos funcionais em `07_FUNCTIONAL_REQUIREMENTS.md`;
3. escopo em `01_PROJECT_CHARTER_SCOPE.md`;
4. modelos normativos de domínio, regras, workflows, scoring e priorização;
5. arquitetura técnica;
6. plano de implementação;
7. AI handoff e política operacional de modelos;
8. especificações funcionais complementares, quando não conflitarem com os itens anteriores.

Nenhuma decisão funcional deve ser alterada silenciosamente durante implementação.

## 4. Catálogo normativo

### Core

- `01_PROJECT_CHARTER_SCOPE.md` — propósito, escopo, princípios e exclusões.
- `02_DOMAIN_MODEL.md` — entidades, relacionamentos, identificadores, estados e invariantes.
- `03_BUSINESS_RULES.md` — Business Rules `BR-GEO-001` a `BR-GEO-054`.
- `04_WORKFLOWS.md` — workflows e ordem de execução.
- `05_SCORING_MODEL.md` — Score, Coverage, Confidence, Consolidation, aplicabilidade e Overall calibrado. Baseline: `SCORE-GEO-003`.
- `06_PRIORITIZATION_MODEL.md` — Severity, Impact, Effort, Confidence e Priority.
- `07_FUNCTIONAL_REQUIREMENTS.md` — requisitos funcionais e não funcionais vigentes.
- `08_TECHNICAL_ARCHITECTURE.md` — arquitetura local/modular e fronteiras entre domínios.
- `09_IMPLEMENTATION_PLAN.md` — histórico e ordem de implementação das capacidades.
- `10_DECISIONS.md` — decisões humanas consolidadas e pendências corporativas.
- `11_REPORTING_LANGUAGE_GLOSSARY.md` — linguagem e apresentação do relatório.
- `12_AI_HANDOFF.md` — continuidade operacional por IA/desenvolvedor.
- `13_MODEL_ROUTING_POLICY.md` — política de modelos e esforço.

### Especificações funcionais complementares

- `14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md` — auditoria multi-URL e evidência visual.
- `15_ERROR_CENTRIC_REPORT_UX.md` — experiência de leitura e organização dos relatórios.
- `16_ROOT_CAUSE_ELEMENT_REMEDIATION.md` — remediação por causa raiz e elemento.
- `17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md` — precisão e consistência das recomendações.
- `18_MULTI_AI_PROVIDER_ROUTING.md` — análise semântica por IA, roteamento, fallback e telemetria.
- `19_SCORE_APPLICABILITY_GEO_MINIMUMS.md` — semântica de aplicabilidade introduzida no histórico `002` e preservada no `003`.
- `20_AI_CONTENT_REMEDIATION.md` — sugestões e remediação de conteúdo por IA, sem alteração retroativa do score.
- `21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md` — PageSpeed, Lighthouse e Core Web Vitals/CrUX como evidência externa complementar.
- `22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md` — acessibilidade automatizada e diagnósticos Web separados do Search & AI Readiness.
- `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md` — Synthetic Navigation Apdex.
- `24_CRAWLING_DISCOVERY_AI_ACCESS.md` — rastreamento, descoberta e políticas de crawlers.
- `25_SYNTHETIC_USER_EXPERIENCE_APDEX.md` — Synthetic User Experience Apdex calibrável, separado de RUM.
- `26_OBSERVED_GENERATIVE_VISIBILITY.md` — visibilidade generativa observada/importada e query-runs controlados.
- `27_MONITORING_OBSERVABILITY.md` — comparação longitudinal, release gate, outcomes externos, sidecar observacional e diagnósticos complementares.

## 5. Baseline vigente de scoring e método público

- motor padrão para novas auditorias: `SCORE-GEO-003`;
- `SCORE-GEO-002` permanece histórico e não é recalculado;
- identidade pública de readiness: `SARI-001`;
- dimensões legitimamente `NOT_APPLICABLE` não recebem zero;
- Coverage, Confidence e Consolidation permanecem métricas distintas do Score;
- o Overall `003` exige artifact de calibração `VALIDATED`; sem ele, permanece `NOT_CONSOLIDATED`;
- não existe alegação de score GEO/AEO universal ou homologado;
- métricas externas não são incorporadas silenciosamente ao SARI;
- outcomes controlados de Observed Generative Visibility podem ser usados pelo processo separado de calibração, sem alterar retroativamente o AUD que os contém;
- Monitoring e Observability permanecem domínios derivados/complementares e non-scoring por padrão.

Detalhes: `../SCORE_GEO_003.md` e `27_MONITORING_OBSERVABILITY.md`.

## 6. REPORT-SITE-GEO-001

O contrato final de saída é condicional pela existência/materialização do arquivo:

```text
<AUD-ID>/report/index.html
<AUD-ID>/report/readiness.html             # SARI-001 / RASAI
<AUD-ID>/report/score-geo-003.html         # método/modelo/dataset/gates do scoring vigente
<AUD-ID>/report/mobile.html                # condicional
<AUD-ID>/report/desktop.html               # condicional
<AUD-ID>/report/remediation.html
<AUD-ID>/report/content-suggestions.html
<AUD-ID>/report/crawling-discovery.html    # rastreamento e descoberta
<AUD-ID>/report/accessibility.html         # acessibilidade automatizada, condicional
<AUD-ID>/report/web-performance.html       # Lighthouse/Core Web Vitals, quando habilitados
<AUD-ID>/report/apdex.html                 # Synthetic Navigation Apdex, condicional
<AUD-ID>/report/apdex-experience.html      # Synthetic User Experience Apdex, condicional
<AUD-ID>/report/ai-visibility.html         # visibilidade observada, após importação/regeneração
<AUD-ID>/report/observability.html         # Search & AI outcomes externos + diagnósticos complementares
<AUD-ID>/report/ai-usage.html
<AUD-ID>/report/references.html
<AUD-ID>/report/css/site.css
```

Default de dispositivo da CLI: `mobile`. `desktop` e `both` são seleções explícitas/parametrizáveis.

Cada indicador/domínio possui página canônica. `index.html` pode resumir resultados para navegação executiva, mas não deve fundir metodologias em score comum.

`readiness.html` é a página canônica do SARI. `score-geo-003.html` documenta o estado de calibração. Acessibilidade, Web Performance, Apdex, visibilidade generativa e Search & AI Observability permanecem domínios separados.

O menu final é canônico e condicional à existência dos arquivos; uma projeção opcional gerada posteriormente não pode remover do menu outra página opcional já materializada.

## 7. Fronteiras dos domínios complementares

| Domínio | Finalidade | Regra de fronteira |
|---|---|---|
| Web Performance | PageSpeed/Lighthouse/CrUX | evidência externa; não entra diretamente no Overall `003` |
| Acessibilidade automatizada | diagnóstico automatizado | não declara conformidade WCAG integral nem entra diretamente no Overall `003` |
| Synthetic Navigation Apdex | navegação sintética controlada | T/4T explícito; não é RUM; permanece indicador separado |
| Rastreamento e descoberta | robots.txt, sitemaps, feeds e políticas de crawlers | diagnóstico técnico non-scoring |
| Synthetic User Experience Apdex | experiência sintética calibrável | não é RUM; separado de Navigation Apdex e SARI |
| Observed Generative Visibility | resultados observados/importados de AI Search | domínio observacional; query-runs podem alimentar calibração offline |
| Search & AI Observability | Search Console, URL Inspection, CrUX History/imports e diagnósticos derivados | sidecar separado; non-scoring; proveniência explícita |
| RASAI Monitor | comparação baseline/current, release gate e change impact | read-only; não cria score e não presume causalidade |

## 8. Observed Generative Visibility e calibração

Fonte normativa: `26_OBSERVED_GENERATIVE_VISIBILITY.md`.

A capacidade usa `OGV-IMPORT-001`, preserva artifact/SHA-256, mantém métricas reportadas pela fonte separadas de cálculos RASAI e não escreve/recalcula scores do AUD fonte. `CONTROLLED_QUERY_RUNS` elegíveis podem ser consumidos posteriormente pela calibração offline `SCORE-GEO-003`.

## 9. SCORE-GEO-003

Contrato inicial:

```text
format_version = SG003-MODEL-001
model_version = GEO-LR-001
outcome = CITED_BINARY
model = L2_REGULARIZED_LOGISTIC_REGRESSION
split = DOMAIN_HOLDOUT_70_30_V1
```

Promotion gate mínimo documentado:

- 40 domínios;
- 12 domínios no holdout;
- 2 engines;
- 10 queries por domínio;
- 3 repetições por query/engine;
- 3 dias distintos por domínio;
- 2400 observações válidas;
- AUC holdout >= 0,60;
- Brier menor que baseline por prevalência de treino.

Sem artifact `VALIDATED`, as dimensões continuam auditáveis, mas `OVERALL_READINESS` permanece sem valor consolidado. Não existe fallback silencioso para a aritmética `002`.

`rasai scoring dataset` avalia gates pré-fit e gera fingerprint/manifest; `READY_FOR_MODEL_FIT` não equivale a `VALIDATED`.

## 10. Monitoring & Observability

Fonte normativa: `27_MONITORING_OBSERVABILITY.md`.

### Monitoring

```text
rasai monitor compare
rasai monitor impact
rasai monitor gate
```

- abre `audit.db` somente leitura;
- respeita scoring version/device/URL universe;
- gate default é deterministic-only;
- impact usa associação temporal sem atribuição causal;
- saída derivada em `monitoring/MON-*`.

### Observability

```text
rasai observe ...
rasai observability ...
```

- sidecar `observability.db`;
- artifacts em `artifacts/observability/`;
- Search Analytics e URL Inspection via APIs oficiais implementadas;
- CrUX History via API oficial;
- Bing/AI outcomes import-first quando não há contrato direto implementado;
- `report/observability.html`;
- não persiste secrets;
- não altera `audit.db` nem SARI/SCORE-GEO-003.

## 11. Fontes externas e heurística

O RASAI não representa seu score ou thresholds como standard GEO/AEO universal.

Referências primárias podem incluir Google Search Central/Crawling Infrastructure, Google Search Console APIs, Chrome UX Report, OpenAI publisher/help documentation, Schema.org, WHATWG, IETF/RFC, W3C/WAI, Apdex Alliance, Dynatrace e documentação pública Bing Search/Webmaster.

Essas fontes sustentam fenômenos externos específicos; não homologam SARI-001/SCORE-GEO-003.

Heurísticas BR-GEO sem equivalente normativo permanecem identificadas como heurísticas/baseline interna.

## 12. Continuidade de branches e integração

Branches de trabalho são temporárias. Após validação e merge em `main`, confirmar que não existe conteúdo exclusivo pendente antes de excluir branch. Uma branch ativa de outro trabalho não deve ser incorporada sem necessidade técnica explícita.

## 13. Regra de mudança

Mudanças que afetem escopo, Business Rules, scoring, priorização, interpretação do relatório, device context, conteúdo sugerido por IA, Web Performance, acessibilidade, Apdex, crawling/discovery, visibilidade observada, monitoring/observability ou requisitos corporativos devem ser reconciliadas nesta baseline antes do merge.

## 14. Critério de encerramento de alteração

Uma alteração só está apta a merge quando:

- código e documentação normativa estão consistentes;
- testes dirigidos passam;
- regressões relevantes passam;
- CI está verde;
- não há conflito material com `main` atualizado;
- limitações/fail-open estão explícitos;
- HTML/menu estão coerentes;
- quando o comportamento exige inspeção visual/operacional, o estado é liberado para smoke humano antes do merge, salvo autorização humana explícita em contrário.
