# Outputs e artifacts

## Contrato de workspace da auditoria

Cada execução de `rasai audit` persiste a evidência no workspace `audits/<AUD-ID>/`. O banco `audit.db` e os artifacts coletados são a fonte de verdade. O HTML é uma projeção reconstruível para leitura e integração.

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

O runtime de `rasai audit` não materializa:

```text
<AUD>/report/
<AUD>/report.html
<AUD>/remediation.html
```

A remoção é exclusivamente da projeção HTML convencional. Permanecem inalterados os dados e processamentos funcionais que alimentam outras capacidades, incluindo:

```text
findings
evidence
recommendations
root_cause_analyses
root_cause_precision
scores
score_contributions
telemetria/custos de IA
fulfillment e rastreabilidade
```

Nenhum collector, crawler, integração externa, scoring, análise determinística ou chamada de IA é eliminado por essa mudança.

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

### Improvement Intelligence

Quando executada, a análise profunda adiciona tabelas aditivas no mesmo `audit.db`:

```text
improvement_intelligence_runs
improvement_intelligence_findings
improvement_intelligence_recommendations
```

A chamada de IA usa a telemetria canônica `ai_provider_attempts` com `semantic_contract_version=IMPROVEMENT-INTELLIGENCE-001`. Provider, modelo, reasoning, tokens e custo permanecem separados do cálculo de readiness.

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

### `context.html`

Topologia de captura por URL/device e informações de runtime. É read-only e não recalcula score.

### `mobile.html` / `desktop.html`

Superfícies estáveis de evidências e findings por dispositivo. Quando não existe snapshot para o contexto correspondente, exibem estado neutro/não aplicável em vez de desaparecer do menu.

### `crawling-discovery.html`

Robots, sitemaps, crawler policies, feeds/`llms.txt`, conteúdo capturado disponível e remediação técnica opcional.

### `accessibility.html`

Diagnóstico automatizado ou estado explícito de ausência/desabilitação da fonte. Lighthouse accessibility não equivale a certificação WCAG integral.

### `web-performance.html`

Estado da integração e, quando coletados, Lighthouse/PageSpeed/CrUX. Permanece separado do SARI e do Apdex.

### `standards.html`

Superfície canônica de métricas e serviços de padrões. Pode conter W3C HTML/CSS, MDN Observatory, Web Platform Baseline/WebDX e métricas derivadas quando disponíveis. Sem coleta/dataset, mantém estado explícito e não dispara serviço apenas para preencher o HTML.

### `report-catalog/cat-10.html`

Página de **Segurança passiva**. Projeta somente dados já persistidos e não dispara coleta durante o HTML. Apresenta cobertura, findings, severidade/classificação, rastreabilidade, recursos first/third-party, componentes/versionamento identificáveis, MDN HTTP Observatory/Lighthouse já coletados, OSV/CISA KEV e remediação por finding.

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

### `ai-usage.html`

Estado de uso de IA, provider/modelo, tentativas, tokens e custo estimado quando aplicável. Não gera nova chamada de IA.

### `improvement-intelligence.html`

Análise profunda opcional de uma única URL. Correlaciona evidências persistidas, HTML/semântica, Lighthouse/PageSpeed, Search/SERP quando disponível, arquivos de descoberta e postura de segurança passiva. Materializa findings, backlog priorizado e sugestões evidence-bound sem alterar `SARI-001`/`SCORE-GEO-004`. HTML sugerido e recomendações continuam sujeitos a revisão humana e o ganho só é comprovado por nova auditoria/before-after.

### `content-suggestions.html`

Estado e sugestões textuais/JSON-LD advisory. Se IA estiver desabilitada, a página continua existindo e deixa esse estado explícito.

### `remediation.html`

Plano de correção evidence-bound derivado dos findings persistidos.

### `references.html`

Metodologia, natureza das fontes e referências públicas.

### `search-intelligence.html`

Superfície canônica de SERP Observation, classificação competitiva e análises associadas. Sem observações persistidas, exibe estado neutro. É observacional/advisory e não altera automaticamente `SARI-001`/`SCORE-GEO-004`.

### `apdex.html`

Superfície canônica de Synthetic Navigation Apdex. Exibe resultados quando executado e estado neutro quando não solicitado; a existência do HTML não inicia navegação sintética.

### `apdex-experience.html`

Superfície canônica de Synthetic User Experience Apdex calibrável. Não é RUM. Exibe estado neutro quando não executado.

### `ai-visibility.html`

Observed Generative Visibility import-first. Sem dataset/import, exibe estado neutro. Não produz score universal nem altera o scoring da auditoria.

### `observability.html`

Superfície canônica de datasets/proveniência e outcomes externos pós-auditoria, incluindo Search Console, URL Inspection, CrUX History e diagnósticos derivados. Sem sidecar/dado, exibe estado neutro. É non-scoring e não prova causalidade.

### `quality.html`

Superfície canônica de qualidade da evidência e apoio à decisão. Sem processamento especializado, exibe estado neutro. Não cria um segundo readiness score.

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

A ordem do catálogo é estável e todos os itens abaixo fazem parte do menu de uma auditoria finalizada. A configuração controla o estado/conteúdo de cada domínio, não a existência do link:

```text
Visão geral
Readiness SARI
Metodologia de scoring
Contexto de captura
Domínio e descoberta
Relatório Mobile
Relatório Desktop
Acessibilidade
Web Performance
Métricas e padrões
Apdex de navegação
Apdex de experiência
Search Intelligence
Visibilidade em IA
Search & AI observados
Uso de IA
Análise profunda e melhorias
Conteúdo e JSON-LD
Remediações
Quality & decisão
Referências e metodologia
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
