# Outputs e artifacts

## Workspace de auditoria

Cada auditoria materializa, conforme as capacidades executadas:

```text
audits/<AUD-ID>/
├─ audit.db
├─ observability.db            # condicional; sidecar RASAI-OBS-002
├─ artifacts/
│  ├─ web-performance/         # condicional
│  ├─ m24/                     # condicional
│  ├─ m26/                     # condicional
│  └─ observability/           # condicional
├─ logs/
│  └─ audit.log                # quando logging persistente estiver ativo
└─ report/
   ├─ index.html
   ├─ readiness.html
   ├─ scoring.html             # canônico; método vigente e versão persistida
   ├─ score-geo-004.html       # alias de compatibilidade
   ├─ mobile.html              # condicional
   ├─ desktop.html             # condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html  # condicional
   ├─ accessibility.html       # condicional
   ├─ web-performance.html     # condicional
   ├─ apdex.html               # condicional
   ├─ apdex-experience.html    # condicional
   ├─ ai-visibility.html       # condicional
   ├─ observability.html       # condicional
   ├─ quality.html             # condicional
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

O menu final lista somente páginas canônicas existentes e preserva ordem estável. O alias versionado do scoring não recebe item próprio de navegação.

## Fonte de verdade

`audit.db` + artifacts originais da auditoria são a fonte de verdade do AUD. HTML é projeção humana.

`observability.db` é um sidecar derivado/reconstruível para outcomes coletados/importados após a auditoria. Ele não substitui nem migra `audit.db`.

```text
SARI-001       = índice público de readiness
SCORE-GEO-004  = scoring vigente para novas auditorias
RASAI-OBS-002  = contrato atual do sidecar observacional
```

Nenhuma projeção recalcula silenciosamente auditoria histórica para outra `scoring_version`.

## `audit.db`

Grupos relevantes, conforme materialização:

### Evidência, regras e scoring

```text
pages
page_snapshots
evidence
rule_executions
findings
scores
score_contributions
```

### IA

```text
ai_audit_sessions
ai_provider_attempts
content_remediation_runs
content_remediation_attempts
content_remediation_suggestions
provider_pricing_catalog
```

Telemetria/custo não participa do score.

### Crawling/discovery

```text
m24_runs
m24_diagnostics
m24_ai_results
```

`scoring_impact=NONE`.

### Web Performance

```text
web_performance_runs
web_performance_attempts
web_performance_observations
```

### Synthetic Navigation Apdex

```text
synthetic_apdex_runs
synthetic_apdex_samples
synthetic_apdex_summaries
lighthouse_execution_profiles
```

### Synthetic User Experience Apdex

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

Ambos os Apdex são sintéticos e não são RUM/SARI.

### Observed Generative Visibility

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

Essas tabelas preservam outcomes observados/importados e não recalculam `scores`, `rule_executions` ou `findings`.

## `observability.db` - `RASAI-OBS-002`

Criado somente quando uma operação observacional persiste dataset externo.

Tabelas atuais:

```text
datasets
search_performance
index_observations
crux_history
```

Identidade de uma linha observacional:

```text
(dataset_id, record_id)
```

Isso permite que coletas independentes reutilizem IDs locais como `GSC-SA-00000001` sem colisão. Sidecars OBS-001 são migrados automaticamente preservando linhas.

Proveniência inclui:

- source type;
- capture method;
- período;
- artifact path/SHA-256;
- metadata;
- timestamp de coleta/importação.

Bearer token/API key nunca deve ser persistido.

### Source types observacionais relevantes

Conforme uso, podem existir datasets de:

```text
GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS
GOOGLE_SEARCH_CONSOLE_SEARCH_APPEARANCE
GOOGLE_SEARCH_CONSOLE_URL_INSPECTION
GOOGLE_SEARCH_CONSOLE_PROPERTIES
GOOGLE_SEARCH_CONSOLE_SITEMAPS
GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT_SEARCH
GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT_DISCOVER
GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_CONTROL
CHROME_UX_REPORT_HISTORY
Bing/imports normalizados
```

Search/Discover GenAI permanecem fontes distintas. O export GenAI não recebe clicks/CTR/position/query artificiais quando esses campos não existem na fonte.

## Artifacts

### Web Performance

```text
artifacts/web-performance/*.pagespeed.json
artifacts/web-performance/*.crux.json
```

### Crawling/discovery

```text
artifacts/m24/
artifacts/m24/llms.txt          # somente se obtido
```

Ausência de `llms.txt` não gera penalidade/readiness failure.

### Observed Generative Visibility

```text
artifacts/m26/observed-generative-visibility-<sha16>.json
```

### Search & AI Observability

```text
artifacts/observability/
```

Pode conter responses JSON oficiais, CSVs importados e fatos observacionais normalizados. Esses artifacts são untrusted external input e não se tornam evidence original do AUD.

## Relatórios por domínio

### `index.html`

Dashboard executivo; não pondera domínios complementares em score comum.

### `readiness.html`

Página canônica de `SARI-001`.

### `scoring.html`

Página canônica da metodologia de scoring. Exibe `scoring_version`, contrato do Overall, Coverage, Confidence, Consolidation e rastreabilidade. O método vigente é `SCORE-GEO-004`.

### `score-geo-004.html`

Alias de compatibilidade para links antigos. Redireciona para `scoring.html` e não deve ser usado como contrato por novas integrações.

### `mobile.html` / `desktop.html`

Evidências/findings por contexto materializado.

### `remediation.html`

Plano de correção evidence-bound.

### `content-suggestions.html`

Sugestões textuais/JSON-LD advisory.

### `crawling-discovery.html`

Robots, sitemaps, crawler policies, feeds/`llms.txt` e remediação técnica opcional. Non-scoring.

### `accessibility.html`

Diagnóstico automatizado; não equivale a certificação WCAG integral.

### `web-performance.html`

Lighthouse/PageSpeed/CrUX. Separado de SARI/Apdex.

### `apdex.html`

Synthetic Navigation Apdex.

### `apdex-experience.html`

Synthetic User Experience Apdex calibrável. Não é RUM.

### `ai-visibility.html`

Observed Generative Visibility import-first; não produz score universal de Search & AI Readiness nem altera `SCORE-GEO-004`.

### `observability.html`

Pode conter:

- datasets/proveniência;
- Indexability Reality Matrix;
- Search Performance / Search Appearance;
- URL Inspection;
- CrUX History;
- Google/Bing/GenAI imports;
- Query × Intent;
- Potential Search Cannibalization;
- structured-data/entity/freshness/hreflang/retrieval diagnostics;
- template/root-cause clusters.

Non-scoring e non-causal.

### `quality.html`

Pode conter:

- Audit Health / Data Quality;
- Evidence Confidence por finding;
- Operational Priority `P0`-`P3`;
- Coverage Map;
- `nosnippet`, `max-snippet`, `data-nosnippet`, `X-Robots-Tag`;
- Recommendation Validation;
- top prioridades executivas.

Quality não é um novo readiness score.

### `ai-usage.html`

Provider/model/tentativas/tokens/custo estimado. Telemetria operacional.

### `references.html`

Metodologia, natureza das fontes e referências públicas.

## Relatórios históricos/consolidados

```text
audits/.rasai/consolidated-index.db

audits/consolidated/CONS-*/
├─ report.html
└─ manifest.json
```

O consolidador abre AUDs read-only, não chama APIs e não reexecuta scoring.

## RASAi Monitor

```text
audits/monitoring/MON-*/
├─ report.html
├─ manifest.json
└─ impact.html                 # quando solicitado
```

`impact.html` seleciona um dataset mais recente por fonte, não soma históricos sobrepostos e só emite associação temporal para janelas elegíveis.

## Fix Verification

```text
audits/verification/VER-*/
└─ report.html
```

Compara transições persistidas de regras entre dois AUDs. Não prova downstream Search/AI impact.

## Evidence Timeline

```text
audits/quality/TIMELINE-*/
└─ report.html
```

Projeção longitudinal read-only de AUDs existentes.

## Scoring CLI vigente

O comando suportado atualmente é:

```text
rasai scoring inspect
```

Ele inspeciona versão, fórmula e gates do `SCORE-GEO-004`. Fluxos antigos de dataset/model artifact do `SCORE-GEO-003` são históricos e não fazem parte do runtime de scoring 004.

## Navegação canônica

Ordem atual, condicionada à existência do arquivo:

```text
Visão geral
Readiness SARI
Metodologia de scoring
Relatório Mobile
Relatório Desktop
Remediações
Conteúdo e JSON-LD
Rastreamento e descoberta
Acessibilidade
Web Performance
Apdex de navegação
Apdex de experiência
Visibilidade em IA
Search & AI observados
Quality & decisão
Uso de IA
Referências e metodologia
```

Apenas a página atual recebe estado ativo.

## Segurança e integridade

- secrets não devem aparecer em SQLite, artifacts, report, INI ou log;
- custo estimado não é invoice;
- cross-origin acquisition exige política explícita segura;
- Observed Generative Visibility/Observability preservam proveniência e não fazem scraping de portais sem contrato;
- Monitoring, Quality, Timeline, Verification e consolidation abrem bancos fonte read-only;
- `NULL` de fonte externa não vira zero observado;
- publisher controls não são penalidades SARI;
- remover `observability.db`, cache consolidado, `MON-*`, `VER-*` ou timeline não remove a evidência original do AUD;
- hash do `audit.db` deve permanecer inalterado após operações `monitor`, `observe` e `quality` pós-auditoria.

Detalhes: [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md), [SCORE_GEO_004.md](SCORE_GEO_004.md) e [specification/28_AUDIT_QUALITY_VERIFICATION.md](specification/28_AUDIT_QUALITY_VERIFICATION.md).
