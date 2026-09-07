# Outputs e artifacts

## Workspace de auditoria

Cada auditoria materializa:

```text
audits/<AUD-ID>/
├─ audit.db
├─ observability.db            # condicional; sidecar pós-auditoria
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
   ├─ score-geo-003.html
   ├─ mobile.html              # condicional
   ├─ desktop.html             # condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html  # condicional/materializado
   ├─ accessibility.html       # condicional
   ├─ web-performance.html     # condicional/materializado
   ├─ apdex.html               # Synthetic Navigation Apdex, condicional
   ├─ apdex-experience.html    # Synthetic User Experience Apdex, condicional
   ├─ ai-visibility.html       # Observed Generative Visibility, condicional
   ├─ observability.html       # Search & AI Observability, condicional
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

O menu final lista somente páginas existentes e preserva ordem canônica.

## Fonte de verdade

`audit.db` + artifacts da auditoria são a fonte de verdade para o AUD. HTML é projeção humana.

`observability.db` é **sidecar derivado/complementar** para outcomes coletados/importados após a auditoria. Não substitui nem migra `audit.db`.

Identidade/metodologia atual:

```text
SARI-001       = índice público de readiness
SCORE-GEO-003  = scoring vigente para novas auditorias
SCORE-GEO-002  = histórico
```

Nenhum report recalcula silenciosamente auditoria histórica para outra `scoring_version`.

## `audit.db`

Grupos relevantes incluem, conforme materialização:

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

`readiness.html` e `score-geo-003.html` projetam dados persistidos/estado do modelo. O HTML não deve fabricar Overall quando `SCORE-GEO-003` não está consolidável.

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

### Crawling/discovery enrichment

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

Lab e field data permanecem semanticamente separados.

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

## `observability.db`

Criado somente quando uma operação de observability persiste dataset externo.

Tabelas atuais:

```text
datasets
search_performance
index_observations
crux_history
```

Proveniência inclui source type, capture method, período, artifact path/SHA-256, metadata e timestamp de coleta/importação.

Não persistir bearer token/API key.

## Artifacts

### Web Performance

```text
artifacts/web-performance/*.pagespeed.json
artifacts/web-performance/*.crux.json
```

Somente quando resposta externa foi efetivamente obtida/preservada.

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

Artifact normalizado `OGV-IMPORT-001`, com SHA-256 persistido.

### Search & AI Observability

```text
artifacts/observability/
```

Contém responses/exports normalizados preservados pelos collectors/importers. São dados externos untrusted e não se tornam evidence original do AUD.

## Relatórios por domínio

### `index.html`

Dashboard executivo. Pode resumir vários domínios, mas não os pondera em um score comum.

### `readiness.html`

Página canônica de `SARI-001`: dimensões, Coverage, Confidence, Consolidation e limitações.

### `score-geo-003.html`

Contrato/status do `SCORE-GEO-003`: model version, dataset, gates, calibração e estado do Overall.

### `mobile.html` / `desktop.html`

Evidências/findings por contexto materializado.

### `remediation.html`

Plano de correção evidence-bound, agrupamento e detalhes por ocorrência.

### `content-suggestions.html`

Sugestões textuais/JSON-LD advisory.

### `crawling-discovery.html`

Robots, sitemaps, crawler policies, feeds/`llms.txt` e remediação técnica opcional. Non-scoring.

### `accessibility.html`

Diagnóstico automatizado; não equivale a certificação WCAG integral.

### `web-performance.html`

Lighthouse/PageSpeed/CrUX e diagnósticos de performance. Separado de SARI/Apdex.

### `apdex.html`

Synthetic Navigation Apdex.

### `apdex-experience.html`

Synthetic User Experience Apdex calibrável. Não é RUM.

### `ai-visibility.html`

Observed Generative Visibility import-first; source-reported metrics e controlled query-runs. Não produz GEO score universal nem altera `SCORE-GEO-003`.

### `observability.html`

Search & AI Observability, podendo conter:

- datasets/proveniência;
- Indexability Reality Matrix;
- Search Performance;
- URL Inspection state;
- CrUX History;
- Query × Intent Alignment;
- Potential Search Cannibalization candidates;
- Structured Data/entity/freshness/hreflang/retrieval diagnostics;
- template/root-cause clusters.

Non-scoring e non-causal por contrato.

### `ai-usage.html`

Provider/model/tentativas/tokens/custo estimado. Operational telemetry.

### `references.html`

Metodologia, natureza das fontes e referências públicas.

## Relatórios históricos/consolidados

Cache derivado:

```text
audits/.searchgeo/consolidated-index.db
```

Snapshots:

```text
audits/consolidated/CONS-*/
├─ report.html
└─ manifest.json
```

O consolidador abre AUDs read-only, não chama APIs e não reexecuta scoring.

## RASAI Monitor

Saída derivada entre dois AUDs:

```text
audits/monitoring/MON-*/
├─ report.html
├─ manifest.json
└─ impact.html                 # quando `monitor impact` é solicitado
```

Monitoring não escreve em nenhum `audit.db` fonte.

`manifest.json` registra baseline/current, fingerprints, comparabilidade, classificações e limitações. `impact.html` usa associação temporal, nunca prova automática de causalidade.

## Calibration dataset

`rasai scoring dataset` gera manifest/fingerprint pré-fit no destino definido pelo comando/implementação. Esse artifact descreve suficiência da base, não model validation. `READY_FOR_MODEL_FIT != VALIDATED`.

## Navegação canônica

Ordem atual, condicionada à existência do arquivo:

```text
Visão geral
Readiness SARI
SCORE-GEO-003
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
Uso de IA
Referências e metodologia
```

Apenas a página atual recebe estado ativo.

## Segurança e integridade

- secrets não devem aparecer em SQLite, artifacts, report, INI ou log;
- custo estimado não é invoice;
- cross-origin acquisition exige política explícita segura;
- Observed Generative Visibility/Observability preservam proveniência e não fazem scraping de portais sem contrato;
- Monitoring/consolidation abrem bancos fonte read-only;
- remover `observability.db`, cache consolidado ou `MON-*` não remove a evidência original do AUD;
- hash do `audit.db` deve permanecer inalterado após operações `monitor` e `observe` pós-auditoria.

Detalhes: [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [SCORE_GEO_003.md](SCORE_GEO_003.md).
