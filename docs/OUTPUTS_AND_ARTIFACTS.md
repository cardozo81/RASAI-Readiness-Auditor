# Outputs e artifacts

## Contrato de workspace da auditoria

Cada execução de `rasai audit` persiste a evidência no workspace `audits/<AUD-ID>/`. O banco `audit.db` e os artifacts coletados são a fonte de verdade. O HTML é uma projeção reconstruível para leitura e integração.

```text
audits/<AUD-ID>/
├─ audit.db
├─ artifacts/
│  ├─ web-performance/         # quando houver coleta externa
│  ├─ observability/
│  │  └─ observability.db      # quando operações observacionais persistirem dados externos
│  └─ outros artifacts internos por capacidade, quando aplicável
├─ logs/
│  └─ audit.log                # quando logging persistente estiver ativo
└─ report-catalog/
   ├─ index.html
   ├─ sari.html
   ├─ cat-01.html ... cat-10.html
   ├─ capture-context.html
   ├─ execution-evidence.html
   ├─ ai-integrations.html
   ├─ methodology.html
   ├─ metrics.html
   ├─ manifest.json
   └─ css/site.css
```

### Caminhos fora do contrato de saída de `rasai audit`

Não fazem parte do workspace contratual de uma AUD:

```text
<AUD>/report/
<AUD>/report.html
<AUD>/remediation.html
<AUD>/observability.db
```

Os dados funcionais pertencem a `audit.db` e `artifacts/`, incluindo findings, evidências, recomendações, análises de causa, scoring, telemetria/custos de IA, fulfillment e rastreabilidade. Collectors, crawlers, integrações externas, scoring, análises determinísticas e chamadas de IA persistem seus resultados nessas superfícies contratuais.

### Relatório suportado por auditoria

A projeção HTML audit-owned suportada é `report-catalog/`. Sua materialização continua usando a fonte persistida da AUD e não executa collectors, APIs, providers, IA ou scoring para preencher HTML.

O catálogo possui contrato próprio e inclui as páginas CAT selecionadas e suas páginas de governança. CAT-01 ... CAT-10, Matriz de encerramento estrutural, regras de catálogo e rastreabilidade dependem dos dados persistidos, não de uma árvore HTML paralela.

Saídas standalone como `monitoring/`, `verification/`, `quality/TIMELINE-*`, `search-history/` e `consolidated/` mantêm seus contratos próprios e ficam fora do contrato HTML audit-owned de `report-catalog/`.

### SaaS / Web

Os endpoints `/api/v1/audits/{audit_id}/reports...` continuam disponíveis, mas servem somente arquivos autorizados dentro de `<AUD>/report-catalog/`. A rota não expõe `audit.db`, artifacts privados ou caminhos internos.

## Fonte de verdade e versões

```text
SARI-001       = índice público de readiness
SCORE-GEO-004  = scoring vigente para novas auditorias
RASAI-OBS-002  = contrato atual do sidecar observacional
```

Nenhuma projeção recalcula silenciosamente uma auditoria para outra `scoring_version`. HTML e manifest podem ser regenerados, mas `audit.db` + artifacts originais permanecem a evidência fonte.

`artifacts/observability/observability.db` é o sidecar derivado/reconstruível para outcomes observacionais. Ele não substitui `audit.db`.

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

### Improvement Intelligence

Quando executada, a análise profunda adiciona tabelas aditivas no mesmo `audit.db`:

```text
improvement_intelligence_runs
improvement_intelligence_findings
improvement_intelligence_recommendations
```

A chamada de IA usa a telemetria canônica `ai_provider_attempts` com `semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001`. Provider, modelo, reasoning, tokens e custo permanecem separados do cálculo de readiness.

### Crawling e descoberta

A persistência inclui diagnósticos, evidências e, quando habilitada, análise técnica de IA vinculada a evidências. Robots, sitemap, feeds e `llms.txt` efetivamente capturados podem ser preservados como artifacts e projetados no CAT-01 sem nova coleta.

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

## Superfícies do `report-catalog/`

O relatório audit-owned é composto somente pelas superfícies do catálogo:

- `index.html`: visão geral, estados dos CATs e Matriz de encerramento estrutural;
- `sari.html`: leitura persistida do SARI;
- `cat-01.html` a `cat-10.html`: resultados por catálogo, inclusive Segurança passiva no CAT-10;
- `capture-context.html`: contexto e topologia da captura;
- `execution-evidence.html`: estados de execução, fulfillment e evidências operacionais;
- `ai-integrations.html`: uso de IA, integrações, tentativas, tokens, custos e falhas/retries persistidos;
- `directed-analysis.html`: análise direcionada quando materializada;
- `methodology.html`: contratos e metodologia aplicáveis;
- `metrics.html`: inventário de métricas persistidas;
- `manifest.json` e `integrity/`: integridade e verificação offline do pacote;
- `css/site.css`: apresentação compartilhada.

A existência de uma página do catálogo não dispara coleta, provider, IA ou scoring. Estados como `SEM RESULTADO`, `PARCIAL`, `NO_DATA` ou indisponibilidade externa são projetados a partir da evidência persistida.

### CAT-10 — Segurança passiva

`report-catalog/cat-10.html` projeta somente dados já persistidos e não executa active scanning durante a renderização. Apresenta cobertura, findings, severidade/classificação, rastreabilidade, recursos first/third-party, componentes/versionamento identificáveis, MDN HTTP Observatory, OSV/CISA KEV e remediação por finding.

Persistência própria:

```text
passive_security_runs
passive_security_resources
passive_security_components
passive_security_integrations
passive_security_advisories
passive_security_findings
passive_security_remediations
```

Artifacts externos de vulnerability intelligence ficam em `artifacts/security/` quando a integração efetivamente produz resposta. Valores de cookies e nonces brutos não são copiados para as tabelas do CAT-10. Consulte [PASSIVE_SECURITY_CATALOG.md](PASSIVE_SECURITY_CATALOG.md).

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

A navegação da AUD aponta exclusivamente para as páginas materializadas em `report-catalog/`:

```text
Visão geral
Readiness SARI
CAT-01 ... CAT-10
Contexto de captura
Evidências de execução
IA e integrações
Análise direcionada
Metodologia
Métricas
```

Apenas a página atual recebe estado ativo.

## Segurança e integridade

- secrets não devem aparecer em SQLite, artifacts, HTML, INI ou logs;
- custo estimado não é invoice;
- cross-origin acquisition exige política explícita e segura;
- dados externos ausentes não viram zero observado;
- controles do publisher não são penalidades automáticas do SARI;
- Improvement Intelligence usa somente postura de segurança passiva, sem exploração/pentest ativo;
- gerar páginas neutras não dispara collectors, APIs, providers ou IA;
- apagar sidecars ou projeções derivadas não remove a evidência original do AUD;
- operações pós-auditoria não devem alterar o hash do `audit.db` fonte.

Detalhes: [REPORT_GUIDE.md](REPORT_GUIDE.md), [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md), [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [SCORE_GEO_004.md](SCORE_GEO_004.md).
