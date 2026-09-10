# Outputs e artifacts

## Contrato de workspace da auditoria

Cada execução de `rasai audit` persiste a evidência no workspace `audits/<AUD-ID>/`. O banco `audit.db` e os artifacts coletados são a fonte de verdade; HTML, CSS e manifests são projeções reconstruíveis para leitura e integração.

```text
audits/<AUD-ID>/
├─ audit.db
├─ observability.db            # somente quando operações observacionais persistirem dados externos
├─ artifacts/
│  ├─ web-performance/         # quando houver coleta externa
│  ├─ observability/           # quando houver observabilidade
│  └─ outros artifacts internos por capacidade, quando aplicável
├─ logs/
│  └─ audit.log                # quando logging persistente estiver ativo
└─ report/
   ├─ index.html
   ├─ readiness.html
   ├─ scoring.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html
   ├─ accessibility.html
   ├─ web-performance.html
   ├─ remediation.html
   ├─ ai-usage.html
   ├─ references.html
   ├─ mobile.html              # quando houver snapshot Mobile
   ├─ desktop.html             # quando houver snapshot Desktop
   ├─ apdex.html               # quando Synthetic Navigation Apdex tiver execução habilitada
   ├─ apdex-experience.html    # quando Synthetic User Experience Apdex tiver execução habilitada
   ├─ report-manifest.json
   └─ css/site.css
```

### Páginas que uma auditoria normal deve materializar

O término bem-sucedido de uma análise de URLs exige que existam fisicamente as seguintes superfícies pertencentes à própria auditoria:

```text
index.html
readiness.html
scoring.html
content-suggestions.html
crawling-discovery.html
accessibility.html
web-performance.html
remediation.html
ai-usage.html
references.html
```

Essas páginas existem mesmo quando uma capacidade opcional está desabilitada ou sem dado externo. Nesse caso, a página deve representar explicitamente estados como desabilitado, indisponível, não solicitado ou não observado; ausência de coleta não deve ser mascarada pela ausência do HTML.

`mobile.html` e `desktop.html` são esperados somente para os contextos efetivamente materializados em `page_snapshots`. `apdex.html` e `apdex-experience.html` são esperados somente quando as respectivas execuções sintéticas estiverem habilitadas e persistidas.

Ao final de `rasai audit`, o runtime reconstrói as projeções audit-owned a partir do workspace persistido, compara o conjunto esperado com os arquivos físicos e retorna status não zero se alguma página obrigatória daquela execução continuar ausente. O `audit.db` não é descartado em caso de falha exclusiva de projeção.

### Superfícies especializadas pós-auditoria

Os arquivos abaixo pertencem ao catálogo canônico de reports, mas **não são outputs obrigatórios de toda execução `rasai audit`**. Eles são materializados por capacidades/comandos especializados quando houver dados correspondentes:

```text
search-intelligence.html
ai-visibility.html
observability.html
quality.html
```

Portanto, a ausência desses quatro arquivos dentro de um `AUD-*` recém-criado não representa, por si só, auditoria incompleta.

O menu final contém apenas páginas canônicas que existem fisicamente e preserva a ordem definida pelo contrato `ReportSurface`. `scoring.html` é a única URL canônica da metodologia.

## `report/report-manifest.json`

O manifest é metadado de projeção, não segunda fonte de verdade. Além das versões e páginas materializadas, o contrato atual registra a completude da projeção pertencente à auditoria:

```text
audit_id
auditor_version
ruleset_version
sari_version
scoring_version
report_contract_version
observability_contract_version
generated_pages
audit_expected_pages
audit_missing_pages
audit_report_complete
generated_at
source_db
```

Para uma auditoria íntegra quanto à projeção HTML:

```json
{
  "audit_report_complete": true,
  "audit_missing_pages": []
}
```

`generated_pages` pode conter também uma superfície especializada já criada posteriormente. Isso não altera o conjunto `audit_expected_pages` da execução de URL.

## Fonte de verdade e versões

```text
SARI-001       = índice público de readiness
SCORE-GEO-004  = scoring vigente para novas auditorias
RASAI-OBS-002  = contrato atual do sidecar observacional
```

Nenhuma projeção recalcula silenciosamente uma auditoria para outra `scoring_version`. HTML e manifest podem ser regenerados, mas `audit.db` + artifacts originais permanecem a evidência fonte.

`observability.db` é sidecar derivado/reconstruível para outcomes coletados ou importados após a auditoria. Ele não substitui nem migra `audit.db`.

## Conteúdo relevante do `audit.db`

A presença física de tabelas varia conforme capacidades e migrações, mas os grupos abaixo representam os principais dados persistidos.

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

Telemetria e custo estimado de IA não participam do score.

### Crawling e descoberta

A persistência inclui diagnósticos, evidências e, quando habilitada, análise técnica de IA vinculada a evidências. Robots, sitemap, feeds e `llms.txt` efetivamente capturados podem ser preservados como artifacts e projetados em `crawling-discovery.html` sem nova coleta.

Diagnósticos auxiliares permanecem advisory. Quando uma avaliação técnica evidence-bound válida de robots/sitemap participa do scoring, ela usa somente o grupo e os fatores estáticos definidos pelo método; a IA não escolhe peso nem cria bônus duplicado.

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

Os dois Apdex são sintéticos e não são RUM nem SARI.

### Observed Generative Visibility

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

Esses dados preservam outcomes observados/importados e não recalculam `scores`, `rule_executions` ou `findings`.

## `observability.db` - `RASAI-OBS-002`

Criado somente quando uma operação observacional persiste dataset externo. Tabelas atuais incluem:

```text
datasets
search_performance
index_observations
crux_history
```

A identidade de uma linha observacional é `(dataset_id, record_id)`, permitindo históricos independentes sem colisão de IDs locais. Proveniência deve preservar fonte, método de captura, período, artifact/SHA-256, metadata e timestamp. Bearer token e API key nunca são persistidos.

Fontes observacionais suportadas podem incluir Search Console, URL Inspection, sitemaps/properties, exports de desempenho generativo, controles do publisher, CrUX History e imports Bing normalizados. Métricas inexistentes na fonte não são fabricadas.

## Artifacts

### Web Performance

```text
artifacts/web-performance/*.pagespeed.json
artifacts/web-performance/*.crux.json
```

### Crawling e descoberta

Artifacts textuais capturados podem incluir robots, sitemap/feed e `llms.txt`. O nome físico dos subdiretórios internos não é contrato público; consumidores devem usar referências persistidas, manifest e reports. Ausência de `llms.txt` não constitui penalidade de readiness.

### Search & AI Observability

```text
artifacts/observability/
```

Pode conter responses JSON oficiais, CSVs importados e fatos observacionais normalizados. Esses artifacts são input externo não confiável e não se tornam automaticamente evidência original da auditoria.

## Relatórios por domínio

### `index.html`

Dashboard executivo; não agrega metodologias complementares em uma nota comum.

### `readiness.html`

Página canônica do `SARI-001`, com Score, Coverage, Confidence, Consolidation e limitações persistidas.

### `scoring.html`

Página canônica da metodologia vigente. Expõe `scoring_version`, pesos, grupos, gates e rastreabilidade. Para novas auditorias, o motor atual é `SCORE-GEO-004` com agregação hierárquica ponderada.

### `mobile.html` / `desktop.html`

Evidências e findings dos contextos de dispositivo efetivamente auditados.

### `content-suggestions.html`

Estado e sugestões textuais/JSON-LD advisory. Se IA estiver desabilitada, a página continua existindo e deixa esse estado explícito.

### `crawling-discovery.html`

Robots, sitemaps, crawler policies, feeds/`llms.txt`, conteúdo capturado disponível e remediação técnica opcional.

### `accessibility.html`

Diagnóstico automatizado ou estado explícito de ausência/desabilitação da fonte. Lighthouse accessibility não equivale a certificação WCAG integral.

### `web-performance.html`

Estado da integração e, quando coletados, Lighthouse/PageSpeed/CrUX. Permanece separado do SARI e do Apdex.

### `remediation.html`

Plano de correção evidence-bound derivado dos findings persistidos.

### `ai-usage.html`

Estado de uso de IA, provider/modelo, tentativas, tokens e custo estimado quando aplicável. Não gera nova chamada de IA.

### `references.html`

Metodologia, natureza das fontes e referências públicas.

### `search-intelligence.html`

Superfície especializada de SERP Observation, classificação competitiva e análises associadas. É observacional/advisory e não altera automaticamente `SARI-001`/`SCORE-GEO-004`.

### `apdex.html`

Synthetic Navigation Apdex quando habilitado.

### `apdex-experience.html`

Synthetic User Experience Apdex calibrável quando habilitado. Não é RUM.

### `ai-visibility.html`

Observed Generative Visibility import-first. Não produz score universal nem altera o scoring da auditoria.

### `observability.html`

Superfície especializada de datasets/proveniência e outcomes externos pós-auditoria, incluindo Search Console, URL Inspection, CrUX History e diagnósticos derivados. É non-scoring e não prova causalidade.

### `quality.html`

Superfície especializada de qualidade da evidência e apoio à decisão. Não cria um segundo readiness score.

## Relatórios históricos e consolidados

Essas saídas não pertencem ao diretório `report/` de um único AUD:

```text
audits/.rasai/consolidated-index.db

audits/consolidated/CONS-*/report.html
audits/consolidated/CONS-*/manifest.json

audits/search-history/SH-*/report.html
audits/search-history/SH-*/manifest.json

audits/monitoring/MON-*/report.html
audits/monitoring/MON-*/manifest.json
audits/monitoring/MON-*/impact.html        # quando solicitado

audits/verification/VER-*/report.html

audits/quality/TIMELINE-*/report.html
```

Essas projeções abrem os AUDs fonte em modo read-only quando aplicável e não reexecutam scoring por conta própria.

## Scoring CLI vigente

```text
rasai scoring inspect
```

## Navegação canônica

A ordem do catálogo é estável; itens sem arquivo materializado são omitidos do menu:

```text
Visão geral
Readiness SARI
Metodologia de scoring
Relatório Mobile
Relatório Desktop
Rastreamento e descoberta
Acessibilidade
Web Performance
Search Intelligence
Apdex de navegação
Apdex de experiência
Conteúdo e JSON-LD
Remediações
Visibilidade em IA
Search & AI observados
Quality & decisão
Uso de IA
Referências e metodologia
```

Apenas a página atual recebe estado ativo.

## Segurança e integridade

- secrets não devem aparecer em SQLite, artifacts, HTML, INI ou logs;
- custo estimado não é invoice;
- cross-origin acquisition exige política explícita e segura;
- dados externos ausentes não viram zero observado;
- controles do publisher não são penalidades automáticas do SARI;
- apagar sidecars ou projeções derivadas não remove a evidência original do AUD;
- operações pós-auditoria não devem alterar o hash do `audit.db` fonte.

Detalhes: [REPORT_GUIDE.md](REPORT_GUIDE.md), [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [SCORE_GEO_004.md](SCORE_GEO_004.md).
