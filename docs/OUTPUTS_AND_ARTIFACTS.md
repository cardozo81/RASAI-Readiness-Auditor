# Outputs e artifacts

## Workspace

Cada auditoria materializa um workspace próprio:

```text
audits/<AUD-ID>/
├─ audit.db
├─ artifacts/
├─ logs/
│  └─ audit.log
└─ report/
   ├─ index.html               # dashboard executivo
   ├─ readiness.html           # SARI-001 e indicadores proprietários
   ├─ mobile.html              # evidências/findings; condicional
   ├─ desktop.html             # evidências/findings; condicional
   ├─ remediation.html
   ├─ content-suggestions.html
   ├─ crawling-discovery.html  # Rastreamento, descoberta e acesso de crawlers
   ├─ accessibility.html       # quando materializado
   ├─ web-performance.html
   ├─ apdex.html               # Synthetic Navigation Apdex, quando habilitado/materializado
   ├─ apdex-experience.html    # Synthetic User Experience Apdex, quando habilitado/materializado
   ├─ ai-visibility.html       # Observed Generative Visibility, quando houver dataset importado/report regenerado
   ├─ ai-usage.html
   ├─ references.html
   └─ css/site.css
```

## Fonte de verdade

`audit.db` e `artifacts/` são a persistência principal. `audit.log` registra eventos operacionais sanitizados. O HTML é projeção humana derivada desses dados.

Relatórios históricos/consolidados não mudam essa regra: `AUD-*/audit.db` continua sendo a fonte oficial e é aberto em modo somente leitura.

A criação de `SARI-001` como identidade pública não migra nem recalcula o banco. Enquanto a aritmética permanecer a mesma, `scores.scoring_version` continua registrando `SCORE-GEO-002`.

## Banco SQLite

O banco contém entidades da auditoria principal, evidências, execuções de regras, findings, scores, recomendações e telemetria opcional.

Grupos relevantes incluem:

### RASAI scoring

```text
scores
score_contributions
rule_executions
findings
```

`readiness.html` apenas projeta esses dados. Overall, dimensões, Coverage, Confidence e Consolidation não são recalculados no HTML.

### IA

```text
ai_audit_sessions
ai_provider_attempts
content_remediation_runs
content_remediation_attempts
content_remediation_suggestions
provider_pricing_catalog
```

### Rastreamento e descoberta

```text
m24_runs
m24_diagnostics
m24_ai_results
```

Essas tabelas são aditivas. Diagnósticos Rastreamento, descoberta e acesso de crawlers registram `scoring_impact=NONE` e não substituem `rule_executions`, `findings` ou `scores`.

### Web Performance

```text
web_performance_runs
web_performance_attempts
web_performance_observations
```

Essas tabelas permitem distinguir tentativa, sucesso, falha, HTTP, timeout, artifact e dados efetivamente obtidos.

### Synthetic Navigation Apdex

```text
synthetic_apdex_runs
synthetic_apdex_samples
synthetic_apdex_summaries
lighthouse_execution_profiles
```

Os nomes internos permanecem estáveis para compatibilidade de schema. A documentação operacional e os relatórios usam nomenclatura funcional.

### Synthetic User Experience Apdex

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

Synthetic User Experience Apdex é calibrável e separado do Synthetic Navigation Apdex Standard. Seus thresholds/KPM/error policy não reescrevem resultados Synthetic Navigation Apdex nem scoring RASAI.

### Observed Generative Visibility

```text
generative_visibility_imports
generative_visibility_page_citations
generative_visibility_grounding_queries
generative_visibility_trend
generative_visibility_query_runs
```

Observed Generative Visibility persiste outcomes observados/importados. Essas tabelas não escrevem nem recalculam `scores`, `score_contributions`, `rule_executions`, `findings` ou `recommendations`.

Métricas explicitamente fornecidas pela fonte, como Total Citations e Average Cited Pages do Bing AI Performance, permanecem identificadas como **source-reported**. Citation Presence Rate é calculado somente quando existem query-runs controlados válidos e exibe tamanho amostral/intervalo Wilson 95%.

## Índice analítico reconstruível

A consolidação histórica mantém um cache derivado fora de qualquer workspace `AUD-*`:

```text
audits/.searchgeo/consolidated-index.db
```

Esse banco contém somente projeções necessárias para filtro e estatística histórica, como metadados de auditoria, domínios, URLs, dispositivos, versões, scores, Web Performance, Apdex e classificações de findings.

Ele **não é fonte de verdade**. Pode ser removido e reconstruído a partir dos `AUD-*/audit.db` sem perda de evidência.

Observed Generative Visibility não entra automaticamente no consolidado histórico atual. Uma consolidação futura de visibilidade observada deve preservar fonte, período e comparabilidade de engine/surface antes de agregar datasets.

## Relatórios consolidados

Cada snapshot novo é salvo separadamente:

```text
audits/consolidated/CONS-<timestamp>/
├─ report.html
└─ manifest.json
```

`report.html` é estático: ao ser aberto não relê `audit.db`, não chama APIs e não recalcula indicadores.

`manifest.json` registra filtros, data de geração, fingerprints das fontes, AUDs considerados, período efetivamente observado, versões metodológicas, limitações e resultado da atualização do índice.

Quando versão do formato, filtros canônicos e fingerprints do conjunto elegível de AUDs são idênticos a um snapshot anterior, o `CONS-*` existente é reutilizado em vez de gerar uma duplicata. Novo AUD elegível ou alteração de filtro produz novo snapshot.

Detalhes: [CONSOLIDATED_REPORTING.md](CONSOLIDATED_REPORTING.md).

## Artifacts de Web Performance

Quando uma resposta externa é obtida, o RASAI pode persistir JSON em:

```text
artifacts/web-performance/
```

Exemplos:

```text
<WPE-ID>.pagespeed.json
<WPE-ID>.crux.json
```

Se PageSpeed falhar por timeout/HTTP/quota, não existe artifact Lighthouse correspondente. O banco/log preserva a falha e o report explica quais métricas ficaram indisponíveis.

## Artifacts Rastreamento, descoberta e acesso de crawlers

Rastreamento, descoberta e acesso de crawlers pode gravar artifacts próprios em:

```text
artifacts/m24/
```

Quando `/llms.txt` same-origin é obtido com sucesso:

```text
artifacts/m24/llms.txt
```

Quando a remediação técnica de rastreamento e descoberta por IA é habilitada e existe saída persistível, o artifact correspondente permanece nesse domínio Rastreamento, descoberta e acesso de crawlers e sua telemetria é separada da qualidade do website.

A ausência de `llms.txt` não cria artifact e não reduz score/readiness.

## Artifacts Observed Generative Visibility

Cada JSON normalizado `OGV-IMPORT-001` importado é preservado em:

```text
artifacts/m26/observed-generative-visibility-<sha16>.json
```

O SHA-256 completo e o caminho relativo ficam em `generative_visibility_imports`. Reimportar exatamente o mesmo artifact na mesma auditoria substitui sua projeção persistida, sem duplicar observações.

O Observed Generative Visibility é import-first: não faz scraping de Bing Webmaster Tools e não inventa endpoint de API para AI Performance.

## Acessibilidade

Acessibilidade automatizada não possui uma segunda chamada externa própria. Ela reutiliza a categoria `accessibility` do artifact Lighthouse obtido via PageSpeed.

Consequência:

```text
PageSpeed falha
→ artifact Lighthouse ausente
→ score/diagnostics de acessibilidade não obtidos
→ accessibility.html deve registrar a causa
```

Isso é limitação de coleta, não ausência de problemas de acessibilidade.

## Web Performance parcial

É possível ter:

```text
PageSpeed: ERROR
CrUX: SUCCESS
Web Performance: PARTIAL
```

Nesse caso, dados de campo CrUX podem ser válidos enquanto Lighthouse lab/Acessibilidade permanecem indisponíveis.

## Synthetic Apdex

Synthetic Apdex possui persistência própria e não reutiliza duração PageSpeed como amostra.

O report dedicado é:

```text
report/apdex.html
```

Grupos abaixo de 100 amostras válidas são explicitamente identificados como small-group `*`.

Synthetic User Experience Apdex possui domínio adicional em `report/apdex-experience.html`; ele é calibrável e não substitui o Synthetic Navigation Apdex Standard.

## Reports

### `index.html`

Dashboard executivo dos resultados finais disponíveis. O index não soma nem pondera metodologias distintas entre si.

Ele pode resumir:

- SARI-001 por dispositivo;
- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex.

Cada card direciona para a página canônica. Quando há múltiplos contextos externos, o dashboard deve preferir faixa/quantidade de contextos válidos a criar uma média de site não definida pela metodologia de origem.

Observed Generative Visibility permanece um domínio separado e não deve ser fundido ao SARI. Qualquer futura síntese Observed Generative Visibility no dashboard deve continuar exibindo-o como outcome observado independente, sem criar score comum.

### `readiness.html`

Página canônica do **Search & AI Readiness Index `SARI-001`** e dos indicadores agregados proprietários:

- Overall Readiness;
- dimensões;
- Coverage;
- Confidence;
- Consolidation;
- sinais de Groundability sem subscore adicional;
- proveniência das regras contribuintes;
- contexto editorial/YMYL quando persistido.

### `mobile.html` / `desktop.html`

Evidências, snapshots, findings e avaliações por contexto de dispositivo quando materializados.

Essas páginas não são a origem de Overall/dimensões e não devem duplicar Score, Coverage, Confidence ou Consolidation do RASAI.

### `remediation.html`

Findings agrupados e recomendações.

### `content-suggestions.html`

Sugestões textuais e JSON-LD advisory.

### `crawling-discovery.html`

Página canônica do Rastreamento, descoberta e acesso de crawlers para robots/crawler policy, sitemaps, discovery, `llms.txt`, feeds, IndexNow não determinável sem evidência explícita e remediação técnica opcional por IA.

Essa página é informativa e não altera o Search & AI Readiness Index: seus diagnósticos não recalculam `SCORE-GEO-002`/`SARI-001` e devem distinguir standards/guidance externos de decisões metodológicas internas.

### `accessibility.html`

Evidência Lighthouse de acessibilidade quando disponível e causa da indisponibilidade quando não disponível. WCAG continua standard externo; a automação não é certificação integral.

### `web-performance.html`

PageSpeed/Lighthouse/CrUX, Core Web Vitals, tentativas externas e diagnósticos técnicos de performance.

### `apdex.html`

Synthetic Navigation Apdex Standard.

### `apdex-experience.html`

Synthetic User Experience Apdex calibrável. Não é RUM e não substitui Synthetic Navigation Apdex.

### `ai-visibility.html`

Página canônica do Observed Generative Visibility para outcomes de visibilidade generativa observada/importada.

Exibe por dataset/período:

- origem e artifact SHA-256;
- métricas reportadas pela fonte;
- atividade por URL;
- grounding queries;
- tendência importada;
- query-runs controlados;
- Citation Presence Rate, `n` e Wilson 95% quando calculáveis.

Não contém nem produz `SARI-001`, Score GEO ou probabilidade preditiva de citação.

### `ai-usage.html`

Provider/modelo, tentativas, tokens, reasoning e custo estimado quando persistidos. A finalidade de rastreamento e descoberta deve permanecer identificável separadamente da análise semântica e da remediação textual por IA.

### `references.html`

Metodologia, proveniência e referências públicas. Deve separar fonte externa de decisão interna RASAI.

### `consolidated/CONS-*/report.html`

Snapshot histórico/consolidado de indicadores já persistidos, filtrado por domínio, período, dispositivo e opcionalmente URL, com políticas explícitas de comparabilidade.

## Regra de propriedade analítica

Cada indicador possui uma página analítica canônica. O mesmo valor pode ser resumido no `index.html` para navegação executiva, mas sua tabela, metodologia e evidências detalhadas pertencem a uma única página de domínio.

Essa regra evita que o usuário interprete o mesmo indicador como se fosse parte de duas metodologias diferentes.

## Log operacional

```text
logs/audit.log
```

Deve permitir rastrear, sem secrets:

- início/fim de etapas;
- tentativa de provider;
- rastreamento e descoberta e eventuais falhas fail-open;
- PageSpeed/CrUX;
- timeout/HTTP/quota;
- progresso Synthetic Apdex;
- importação Observed Generative Visibility com source/período/contagens e `scoring_impact=NONE`;
- falhas fail-open;
- geração de reports, incluindo as projeções `SARI-001`, Rastreamento, descoberta e acesso de crawlers e Observed Generative Visibility.

A consolidação não grava eventos em `AUD-*/logs/audit.log`; sua rastreabilidade fica no `manifest.json` do próprio `CONS-*`.

## Segurança

- API keys não devem ser persistidas no SQLite, report ou log;
- o arquivo `rasai-console.ini` também não armazena secrets;
- request IDs e diagnósticos devem ser sanitizados;
- custo estimado não é invoice;
- sitemap cross-origin declarado é evidência, mas Rastreamento, descoberta e acesso de crawlers não faz fetch externo automático sem uma política de aquisição segura;
- Observed Generative Visibility rejeita URL cross-origin no dataset e não faz scraping de portais de webmaster;
- o consolidador não escreve em `AUD-*/audit.db` e não faz chamadas externas.
