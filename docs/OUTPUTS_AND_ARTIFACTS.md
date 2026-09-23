# Saídas e artefatos

## Contrato do espaço de trabalho da auditoria

Cada execução de `rasai audit` persiste a evidência no espaço de trabalho `audits/<AUD-ID>/`. O banco `audit.db` e os artefatos coletados são a fonte de verdade. O HTML é uma projeção reconstruível para leitura e integração.

```text
audits/<AUD-ID>/
├─ audit.db
├─ artifacts/
│  ├─ web-performance/         # quando houver coleta externa
│  ├─ observability/
│  │  └─ observability.db      # quando operações observacionais persistirem dados externos
│  └─ outros artefatos internos por capacidade, quando aplicável
├─ logs/
│  └─ audit.log                # quando logging persistente estiver ativo
└─ report-catalog/
   ├─ index.html
   ├─ sari.html
   ├─ cat-01.html ... cat-10.html
   ├─ directed-analysis.html
   ├─ capture-context.html
   ├─ execution-evidence.html
   ├─ ai-integrations.html
   ├─ methodology.html
   ├─ metrics.html
   ├─ manifest.json
   └─ css/site.css
```

### Caminhos fora do contrato de saída de `rasai audit`

Não fazem parte do espaço de trabalho contratual de uma AUD:

```text
<AUD>/report/
<AUD>/report.html
<AUD>/cat-09.html
<AUD>/observability.db
```

Os dados funcionais pertencem a `audit.db` e `artifacts/`, incluindo achados, evidências, recomendações, análises de causa, pontuação, telemetria/custos de IA, atendimento do contrato e rastreabilidade. Coletores, rastreadores, integrações externas, cálculo de pontuação, análises determinísticas e chamadas de IA persistem seus resultados nessas superfícies contratuais.

### Relatório suportado por auditoria

A projeção HTML pertencente à auditoria e suportada é `report-catalog/`. Sua materialização continua usando a fonte persistida da AUD e não executa coletores, APIs, provedores, IA ou cálculo de pontuação para preencher HTML.

O catálogo possui contrato próprio e inclui as páginas CAT selecionadas e suas páginas de governança. CAT-01 ... CAT-10, Matriz de encerramento estrutural, regras de catálogo e rastreabilidade dependem dos dados persistidos, não de uma árvore HTML paralela.

Saídas independentes como `monitoring/`, `verification/`, `quality/TIMELINE-*`, `search-history/` e `consolidated/` mantêm seus contratos próprios e ficam fora do contrato HTML pertencente à auditoria em `report-catalog/`.

### SaaS / Web

Os endpoints `/api/v1/audits/{audit_id}/reports...` continuam disponíveis, mas servem somente arquivos autorizados dentro de `<AUD>/report-catalog/`. A rota não expõe `audit.db`, artefatos privados ou caminhos internos.

## Fonte de verdade e versões

| Conceito apresentado | Versão pública | Identificador técnico |
|---|---:|---|
| **Search & AI Readiness Index - Índice de Prontidão Search & IA** | **001** | `SARI-001` |
| **Método de Pontuação de Prontidão** | **001** | `SCORE-GEO-004` |
| Sidecar observacional | contrato técnico | `RASAI-OBS-002` |

Nenhuma projeção recalcula silenciosamente uma auditoria para outra `scoring_version`. HTML e manifest podem ser regenerados, mas `audit.db` + artefatos originais permanecem a evidência fonte.

`artifacts/observability/observability.db` é o banco auxiliar derivado e reconstruível para resultados observacionais. Ele não substitui `audit.db`.

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

Quando executada, a análise profunda adiciona tabelas no mesmo `audit.db`:

```text
improvement_intelligence_runs
improvement_intelligence_findings
improvement_intelligence_recommendations
```

A chamada de IA usa a telemetria canônica `ai_provider_attempts` com `semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001`. Provedor, modelo, esforço de raciocínio, tokens e custo permanecem separados do cálculo de prontidão.

### Crawling e descoberta

A persistência inclui diagnósticos, evidências e, quando habilitada, análise técnica de IA vinculada a evidências. Robots, sitemap, feeds e `llms.txt` efetivamente capturados podem ser preservados como artefatos e projetados no CAT-01 sem nova coleta.

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

Esses dados preservam resultados observados/importados e não recalculam `scores`, `rule_executions` ou `findings`.

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

Pode conter responses JSON oficiais, CSVs importados e fatos observacionais normalizados. Esses artefatos são entrada externa não confiável e não se tornam automaticamente evidência original da auditoria.

## Superfícies do `report-catalog/`

O relatório audit-owned é composto somente pelas superfícies do catálogo:

- `index.html`: visão geral, estados dos CATs e Matriz de encerramento estrutural;
- `sari.html`: leitura persistida do SARI;
- `cat-01.html` a `cat-10.html`: resultados dos dez catálogos segundo a mesma estrutura contratual;
- `capture-context.html`: contexto e topologia da captura;
- `execution-evidence.html`: estados de execução, fulfillment e evidências operacionais;
- `ai-integrations.html`: uso de IA, integrações, tentativas, tokens, custos e falhas/retries persistidos;
- `directed-analysis.html`: análise direcionada quando materializada;
- `methodology.html`: contratos e metodologia aplicáveis;
- `metrics.html`: inventário de métricas persistidas;
- `manifest.json` e `integrity/`: integridade e verificação offline do pacote;
- `css/site.css`: apresentação compartilhada.

A existência de uma página do catálogo não dispara coleta, provider, IA ou scoring. Estados como `SEM RESULTADO`, `PARCIAL`, `NO_DATA` ou indisponibilidade externa são projetados a partir da evidência persistida.

### Referência uniforme por catálogo

CAT-01 a CAT-10 possuem o mesmo nível contratual e a mesma estrutura explicativa em [`CATALOG_AND_REPORT_SURFACES.md`](CATALOG_AND_REPORT_SURFACES.md). Persistências e integrações específicas permanecem documentadas nos aprofundamentos de cada domínio, sem transformar um CAT em exceção estrutural.

| CAT | Aprofundamento principal |
|---|---|
| CAT-01 | `DISCOVERY_RESOURCES.md`, `RULES_GUIDE.md`, `STANDARDS_METRICS_AND_SERVICES.md` |
| CAT-02 | `LIGHTHOUSE_WEB_QUALITY.md`, `ACCESSIBILITY_PERFORMANCE_DOMAINS.md` |
| CAT-03 | `CONTENT_ANALYSIS_CONTEXT.md`, `SEMANTIC_COHERENCE_AUDIT.md` |
| CAT-04 | `LIGHTHOUSE_WEB_QUALITY.md`, `OPEN_WEB_METRICS.md` |
| CAT-05 | `SEARCH_INTELLIGENCE_REPORT.md`, `EXTERNAL_OBSERVABILITY_INTEGRATIONS.md` |
| CAT-06 | `SYNTHETIC_APDEX.md` |
| CAT-07 | `SYNTHETIC_USER_EXPERIENCE_APDEX.md` |
| CAT-08 | `IMPROVEMENT_INTELLIGENCE.md` |
| CAT-09 | `RECOMMENDATION_GOVERNANCE.md`, `ROOT_CAUSE_REMEDIATION_GUIDE.md` |
| CAT-10 | `PASSIVE_SECURITY_CATALOG.md` |

Os detalhes de tabelas, artifacts, fórmulas e integrações ficam nesses documentos especializados. A definição funcional primária permanece uniforme.

## Saídas derivadas e consolidadas

Essas saídas possuem contratos próprios e não integram o `report-catalog/` de uma única AUD:

```text
audits/.rasai/consolidated-index.db

audits/consolidated/executions/CONRUN-*/execution.json
audits/consolidated/executions/CONRUN-*/ai-exchanges.json

audits/consolidated/CONS-*/report.html
audits/consolidated/CONS-*/manifest.json
audits/consolidated/CONS-*/specialist-analysis.json
audits/consolidated/CONS-*/decision-context.json
audits/consolidated/CONS-*/ai-exchanges.json
audits/consolidated/CONS-*/longitudinal-evidence.json
audits/consolidated/CONS-*/execution.json
audits/consolidated/CONS-*/rules-reference.html   # quando houver regras citadas

audits/search-history/SH-*/report.html
audits/search-history/SH-*/manifest.json

audits/monitoring/MON-*/report.html
audits/monitoring/MON-*/manifest.json
audits/monitoring/MON-*/impact.html        # quando solicitado

audits/verification/VER-*/report.html

audits/quality/TIMELINE-*/report.html
```

Os logs humanos de execução externa não pertencem ao pacote de uma AUD nem de um CONS. Eles ficam no sidecar operacional:

```text
<audits_root>/.rasai/logs/execution-commands/AUD-....log
<audits_root>/.rasai/logs/execution-commands/CONS-....log
```

Esses arquivos são texto UTF-8 secret-free, mantêm blocos separados para Windows, Linux e macOS e não participam de `audit.db`, manifestos, hashes ou HTMLs. Detalhes: [EXECUTION_SCHEDULING.md](EXECUTION_SCHEDULING.md).

Essas projeções abrem os AUDs fonte em modo read-only quando aplicável e não reexecutam scoring por conta própria. O `CONS-5` exige pelo menos duas auditorias da mesma URL e do mesmo dispositivo. Cada tentativa de consolidação cria uma **Execução de Consolidação** (`CONRUN-*`) preservada, inclusive em falha; quando a IA conclui, o **Relatório Consolidado Longitudinal**, formato público **001** (ID técnico `CONS-5`), materializa a análise em `specialist-analysis.json`, o contexto de decisão em `decision-context.json`, a comunicação sanitizada em `ai-exchanges.json`, a evidência longitudinal integral em `longitudinal-evidence.json` e uma cópia final de `execution.json` dentro do próprio pacote. O manifesto registra SHA-256 das fontes SQLite e dos artifacts principais.

## Scoring CLI vigente

```text
rasai scoring inspect
```

## Navegação canônica

A navegação da AUD aponta exclusivamente para as páginas materializadas em `report-catalog/`:

```text
Visão geral
Índice de Prontidão Search & IA
CAT-01 ... CAT-10
Contexto de captura
Evidências de execução
IA e integrações
Análise direcionada
Metodologia
Métricas
```

Apenas a página atual recebe o estado ativo.

## Segurança e integridade

- segredos não devem aparecer em SQLite, artifacts, HTML, INI ou logs;
- custo estimado não é fatura;
- aquisição entre origens exige política explícita e segura;
- dados externos ausentes não viram zero observado;
- controles do publisher não são penalidades automáticas do SARI;
- Improvement Intelligence usa somente postura de segurança passiva, sem exploração/pentest ativo;
- gerar páginas neutras não dispara collectors, APIs, providers ou IA;
- apagar bancos auxiliares ou projeções derivadas não remove a evidência original do AUD;
- operações pós-auditoria não devem alterar o hash do `audit.db` de origem.

Detalhes: [CATALOG_AND_REPORT_SURFACES.md](CATALOG_AND_REPORT_SURFACES.md), [REPORT_GUIDE.md](REPORT_GUIDE.md), [IMPROVEMENT_INTELLIGENCE.md](IMPROVEMENT_INTELLIGENCE.md), [MONITORING_OBSERVABILITY.md](MONITORING_OBSERVABILITY.md), [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md) e [SCORE_GEO_004.md](SCORE_GEO_004.md).
