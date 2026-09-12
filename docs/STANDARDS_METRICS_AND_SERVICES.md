# Métricas, padrões e serviços de referência

## Objetivo

Este documento define o contrato vigente das métricas fundamentadas em padrões, métodos de mercado e serviços externos usados pelo RASAi além do núcleo `SARI-001` / `SCORE-GEO-004`.

O RASAi está em fase pré-publicação. Este documento descreve somente o comportamento atual que deve ser validado e publicado. Não existem versões comerciais anteriores a preservar e coexistência de controles internos não representa compatibilidade com uma versão pública anterior.

Contrato desta família: `STANDARDS-METRICS-001`.

Princípios obrigatórios:

- nenhuma métrica desta família altera `SARI-001` ou `SCORE-GEO-004` sem mudança metodológica explícita e versionada;
- métricas derivadas pelo RASAi são identificadas como derivadas e nunca atribuídas a Google, W3C, MDN, WebDX ou outra entidade;
- scores ou grades emitidos por fonte externa permanecem identificados como valores da própria fonte;
- ausência, desabilitação ou indisponibilidade de integração opcional não é finding do website;
- cada serviço possui controle independente de habilitação;
- serviço sem cobrança de provider e sem credencial obrigatória fica habilitado por default;
- serviço que requer credencial permanece inativo até credencial e contexto mínimo obrigatório existirem;
- credenciais nunca são gravadas em `rasai-console.ini`, `AuditJob`, `audit.db`, HTML ou logs sanitizados;
- configurações não secretas podem ser persistidas no `rasai-console.ini` e transportadas em `AuditJob`;
- chamadas externas são bounded por quantidade de URLs, timeout, throttling e limites específicos quando aplicáveis;
- `ORIGIN`, `URL`, `URL_SET`, `DEVICE_SNAPSHOT`, `PROFILE_MEASUREMENT` e `SEARCH_QUERY` não são agregados silenciosamente como se tivessem a mesma semântica;
- resultados externos observacionais permanecem separados das evidências determinísticas do scoring.

## Arquitetura de escopo

| Escopo | Significado | Exemplos |
|---|---|---|
| `ORIGIN` | propriedade/origem como unidade | MDN Observatory, propriedade Search Console |
| `URL` | recurso/endereço específico | W3C Nu, W3C CSS, canonical, indexability por URL |
| `URL_SET` | consolidação explícita do universo de URLs auditado | HTTP 2xx/4xx/5xx, timeout, redirects, duração da aquisição HTTP |
| `DEVICE_SNAPSHOT` | captura renderizada por dispositivo | Open Web Metrics, structured data renderizado, contexto de browser |
| `PROFILE_MEASUREMENT` | execução sintética com perfil de rede/device | Apdex e medições sintéticas dedicadas |
| `SEARCH_QUERY` | observação ou avaliação orientada a consulta | SERP visibility, MRR, Precision, Recall, nDCG |

Uma consolidação de várias URLs deve declarar universo e fórmula. Média implícita entre páginas não é permitida.

## Catálogo vigente

| Serviço ou método | Relação com RASAi | Escopo | Default operacional | Credencial/contexto | Finalidade |
|---|---:|---|---|---|---|
| RASAi Derived Search & AI Readiness Metrics | 5/5 | URL, URL_SET, DEVICE_SNAPSHOT | ligado | não | crawlability, indexability, sitemap, canonical, structured data e operação HTTP derivada |
| Information Retrieval Metrics | 5/5 | SEARCH_QUERY | ligado | não | MRR, visibilidade e métricas com relevance judgments explícitos |
| Open Web Performance APIs | 3/5 | DEVICE_SNAPSHOT | ligado | não | Navigation Timing, Resource Timing, Paint, LCP, CLS, Event Timing e sinais relacionados |
| W3C Nu HTML Checker | 3/5 | URL | ligado | não | conformidade HTML sem inventar score W3C |
| W3C CSS Validation Service | 3/5 | URL | ligado | não | conformidade CSS com SOAP 1.2 e throttling mínimo do serviço público |
| MDN HTTP Observatory | 2/5 | ORIGIN | ligado | não | postura de headers HTTP e grade/score emitidos pela fonte |
| Web Platform Baseline / WebDX | 3/5 | URL, DEVICE_SNAPSHOT | solicitado por default | dataset e detector reproduzível | compatibilidade quando há mapeamento confiável de features |
| Google PageSpeed Insights / Lighthouse | 3/5 | URL, DEVICE_SNAPSHOT | auto por credencial | API key | laboratório Lighthouse e categorias Web Quality |
| Chrome UX Report API | 4/5 | URL, ORIGIN, DEVICE_SNAPSHOT | auto por credencial | API key | Core Web Vitals de campo agregados |
| Google Search Console | 5/5 | ORIGIN, URL, SEARCH_QUERY | auto por credencial + property | OAuth 2.0 + `siteUrl` | Sitemaps, URL Inspection e Search Analytics observacional |

## Estados de integração

- `DISABLED`: serviço não solicitado ou desligado explicitamente;
- `NOT_CONFIGURED`: solicitado, mas falta requisito obrigatório como dataset, credencial ou contexto;
- `READY`: requisitos mínimos estão presentes e a execução é elegível.

Após tentativa podem existir `SUCCESS`, `PARTIAL`, `NO_DATA` ou `ERROR`. Falha de provider não é convertida em falha do website.

## Controles gerais

| Variável | Default | Efeito |
|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | consolida métricas derivadas de Search & AI Readiness e HTTP operacional |
| `RASAI_RETRIEVAL_METRICS` | `true` | calcula métricas de Information Retrieval quando há dados suficientes |
| `RASAI_OPEN_WEB_METRICS` | `true` | coleta métricas browser-native no snapshot já aberto |
| `RASAI_W3C_VALIDATOR` | `true` | habilita W3C Nu bounded |
| `RASAI_W3C_CSS_VALIDATOR` | `true` | habilita W3C CSS bounded e throttled |
| `RASAI_MDN_OBSERVATORY` | `true` | habilita scan MDN HTTP Observatory por origem |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | solicita análise Baseline; sem dataset/detector fica `NOT_CONFIGURED` ou `NO_DATA` |
| `RASAI_WEB_FEATURES_DATASET` | sem default | dataset WebDX/web-features versionado |
| `RASAI_STANDARDS_MAX_URLS` | `10` | teto de URLs para checks externos; `0` significa todas as URLs auditadas |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | timeout por request desta família |

A referência completa de valores, faixas e precedência está em [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

## Google PageSpeed Insights / Lighthouse

Referência oficial: https://developers.google.com/speed/docs/insights/v5/get-started

O RASAi exige `RASAI_PAGESPEED_API_KEY` para automação. Com a chave presente e sem override de `RASAI_PAGESPEED_ENABLED`, o serviço fica elegível automaticamente. `RASAI_PAGESPEED_ENABLED=false` sempre desliga PageSpeed.

Criação/gerenciamento da key: https://console.cloud.google.com/apis/credentials

A integração preserva a origem Lighthouse/PageSpeed das métricas e não trata dados correlacionados de Lighthouse, PageSpeed e CrUX como evidências independentes de scoring.

## Chrome UX Report API

Referência oficial: https://developer.chrome.com/docs/crux/api/

Requisitos:

```text
RASAI_CRUX_API_KEY=<segredo>
RASAI_CRUX_ENABLED=true|false
```

Com a chave presente e sem override, o serviço fica elegível automaticamente. `RASAI_CRUX_ENABLED=false` é hard-off do CrUX dedicado.

CrUX é fonte de campo agregada. Não é substituído por observação sintética local.

## Controle agregado de Web Performance

`RASAI_WEB_PERFORMANCE` é o controle agregado do runtime externo de Web Performance. `RASAI_PAGESPEED_ENABLED` e `RASAI_CRUX_ENABLED` refinam a seleção por serviço.

`RASAI_WEB_PERFORMANCE=false` explícito interrompe a família externa para aquela execução. Quando não existe hard-off, serviços individuais podem ser ativados conforme seus próprios requisitos.

## Google Search Console

Referências oficiais:

- visão geral: https://developers.google.com/webmaster-tools
- referência: https://developers.google.com/webmaster-tools/v1/api_reference_index
- OAuth 2.0: https://developers.google.com/webmaster-tools/v1/how-tos/authorizing
- Search Analytics: https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- URL Inspection: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
- limites: https://developers.google.com/webmaster-tools/limits

Requisitos mínimos:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=<segredo OAuth temporário>
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL=<property>
```

A property aceita `sc-domain:example.com` ou propriedade URL-prefix absoluta.

O token nunca é persistido em INI, AuditJob ou `audit.db`. A property é não secreta e pode ser persistida no INI ou transportada no `AuditJob`.

### Coleta bounded

Quando `READY`, a finalização da auditoria reutiliza os coletores Search Console já existentes e grava outcomes em `observability.db` e artifacts de observabilidade.

A coleta pode incluir:

- Sitemaps da property;
- URL Inspection limitada por `RASAI_STANDARDS_MAX_URLS`;
- Search Analytics com período finalizado curto.

Defaults operacionais:

| Variável | Default | Faixa |
|---|---:|---:|
| `RASAI_GSC_SEARCH_ANALYTICS_DAYS` | `1` | `0..31` |
| `RASAI_GSC_SEARCH_MAX_ROWS` | `10000` | `1..50000` |
| `RASAI_GSC_FINAL_DATA_LAG_DAYS` | `3` | `0..30` |

`RASAI_GSC_SEARCH_ANALYTICS_DAYS=0` desliga somente a subcoleta Search Analytics.

### Isolamento SaaS

A property deve pertencer ao próprio `AuditJob`. Um worker não pode herdar silenciosamente uma property global para um job sem `gsc_site_url`. A execução temporária mascara qualquer property global quando o job não fornece seu próprio contexto.

O token pode existir no secret store do worker e nunca trafega no payload durável.

## W3C Nu HTML Checker

Referências oficiais:

- https://validator.w3.org/docs/api
- https://validator.w3.org/nu/

O RASAi registra outcome e contagens por URL sem criar score W3C. O serviço é bounded por `RASAI_STANDARDS_MAX_URLS` e `RASAI_STANDARDS_TIMEOUT_SECONDS`.

Estados por URL podem ser `PASS`, `FAIL`, `INDETERMINATE` ou `ERROR`.

Para SaaS em alto volume, self-host do Nu Checker é preferível ao uso intensivo da infraestrutura pública.

## W3C CSS Validation Service

Referências oficiais:

- https://jigsaw.w3.org/css-validator/
- https://jigsaw.w3.org/css-validator/api.html
- https://jigsaw.w3.org/css-validator/manual.html

O RASAi solicita SOAP 1.2 por URI e preserva `validity`, `errorcount`, `warningcount`, `csslevel`, `checkedby` e data quando disponíveis. Não cria score próprio.

A documentação do serviço público pede pelo menos 1 segundo entre requests de automações que validam conjuntos de documentos. O runtime aplica esse throttling entre URLs, além do limite e timeout gerais.

Desligamento explícito:

```text
RASAI_W3C_CSS_VALIDATOR=false
```

Detalhes: [W3C_CSS_VALIDATION.md](W3C_CSS_VALIDATION.md).

## MDN HTTP Observatory

Referência oficial: https://developer.mozilla.org/en-US/observatory/docs/faq

O serviço mede postura de segurança HTTP por origem. Grade e score são preservados como valores emitidos pela própria fonte; não alteram SARI.

O scan externo revela o hostname ao serviço público. Essa fronteira de privacidade deve permanecer visível. Para SaaS em escala ou ambientes restritos, considerar execução controlada/self-host quando disponível.

## Web Platform Baseline / WebDX

Referências:

- https://github.com/web-platform-dx/web-features
- https://web-platform-dx.github.io/web-features-project/

Configuração:

```text
RASAI_WEB_PLATFORM_BASELINE=true|false
RASAI_WEB_FEATURES_DATASET=<caminho versionado>
```

O RASAi não produz cobertura Baseline apenas porque o dataset existe. É necessário mapear features realmente usadas pela página para IDs `web-features` de forma reproduzível.

Estados esperados:

- sem dataset: `NOT_CONFIGURED`;
- dataset disponível, mas sem detector/mapeamento suficiente: `NO_DATA`;
- nenhum score de compatibilidade é inventado por aproximação silenciosa.

## Open Web Performance APIs

Contrato: `OPEN-WEB-METRICS-001`.

Referências:

- https://www.w3.org/TR/performance-timeline/
- https://www.w3.org/TR/navigation-timing-2/
- https://www.w3.org/TR/resource-timing/
- https://www.w3.org/TR/event-timing/

O collector lê métricas do browser já aberto, sem criar nova navegação. O desligamento é `RASAI_OPEN_WEB_METRICS=false`.

## Métricas derivadas RASAi

Estas métricas são calculadas sobre evidência persistida. Não são scores oficiais dos fornecedores citados.

### Crawlability Coverage

```text
URLs com BR-GEO-005 = PASS
---------------------------------- x 100
URLs com recuperabilidade determinável
```

Estados desconhecidos não são convertidos em falha.

### Indexability Coverage

A consolidação por URL usa checks determinísticos de recuperabilidade, conteúdo analisável, soft-404 e diretivas observadas por snapshot. A URL só é positiva quando o conjunto aplicável é determinável e aprovado em todos os snapshots observados.

O contrato atual considera `BR-GEO-005`, `BR-GEO-006`, `BR-GEO-009`, `BR-GEO-011`, `BR-GEO-012` e `BR-GEO-016`.

O resultado é RASAi-derived; não é um “Google Indexability Score”.

### Sitemap Coverage of Audited URLs

```text
URLs auditadas cuja proveniência inclui SITEMAP
----------------------------------------------- x 100
URLs do universo efetivamente auditado
```

A métrica mede o universo auditado e não afirma cobertura de todas as URLs existentes no site.

### Canonical

- `Canonical Declaration Coverage`: snapshots com canonical explícito / snapshots observados;
- `Canonical Consistency Rate`: `BR-GEO-013 = PASS` / snapshots com canonical declarado.

Ausência de canonical e canonical inválido permanecem conceitos separados.

### Structured Data

- `Structured Data Coverage`;
- `Structured Data Validity Rate`, baseada em `BR-GEO-034`;
- `Structured Data to Visible Content Consistency`, baseada em `BR-GEO-036`;
- `Structured Entity Consistency`, baseada em `BR-GEO-037`.

Essas métricas não afirmam elegibilidade para rich result específico quando essa condição não foi medida.

### HTTP operacional por aquisição física

Relação: 4/5.

A aquisição HTTP direta ocorre uma vez por URL. O mesmo `raw_http` pode ser preservado em múltiplos snapshots de device; por isso a consolidação deduplica por `page_id`. Mobile/Desktop não multiplicam a mesma request física.

Métricas:

- `Physical HTTP Observation Coverage`;
- `HTTP 2xx Success Rate`;
- `HTTP 4xx Rate`;
- `HTTP 5xx Rate`;
- `Transport Error Rate`;
- `Transport Timeout Rate`;
- `Redirect Rate`;
- `Redirect Completion Rate`;
- `Cross-host Redirect Rate`;
- `HTTP Acquisition Duration p50`;
- `HTTP Acquisition Duration p75`;
- `HTTP Acquisition Duration p95`;
- `HTTP Acquisition Duration p99`.

Para 2xx/4xx/5xx, o denominador é o conjunto de aquisições físicas observadas. Timeout e erro de transporte permanecem no denominador, evitando inflar a taxa de sucesso.

Os percentis de duração usam `raw_http.duration_ms`. Eles medem duração da aquisição HTTP física e não representam TTFB de browser, CrUX/RUM, Core Web Vital ou Apdex.

Todas essas métricas usam `scope=URL_SET` e criam zero requests adicionais ao alvo.

Detalhes: [OPERATIONAL_HTTP_METRICS.md](OPERATIONAL_HTTP_METRICS.md).

### TTFB p50/p75/p95/p99

TTFB vem de `OPEN-WEB-METRICS-001` no `DEVICE_SNAPSHOT`. Representa o universo browser observado na auditoria; não é RUM e não equivale a percentil CrUX.

Aquisição HTTP física e TTFB browser-native permanecem metodologias separadas.

## Information Retrieval

O cálculo é local e não exige serviço externo.

### Domain MRR

```text
RR(query) = 1 / primeira posição observada do domínio
RR(query) = 0 quando o domínio não foi observado
MRR = média dos RR
```

### Domain SERP Visibility Rate

```text
queries onde o domínio apareceu
------------------------------- x 100
queries com observação persistida
```

### Métricas com relevance judgments

O RASAi não transforma resultado não julgado em irrelevante.

- `Precision@10` e `Judged MRR@10` só são publicados quando o top 10 observado está totalmente julgado;
- `nDCG@10` exige julgamentos explícitos e `ideal_relevance_grades` reproduzível;
- `Recall@10` exige `total_relevant_documents` explícito;
- `Relevance Judgment Coverage@10` informa quanto do top 10 elegível possui julgamento explícito.

Posição alta não é sinônimo de relevância e IA não cria qrels silenciosamente.

## Console e rasai-console.ini

A categoria **Métricas e padrões** expõe os controles desta família.

Podem ser persistidos no INI:

- toggles de serviço;
- property Search Console;
- período/limites GSC;
- limites e timeout de standards;
- caminho de dataset WebDX;
- demais configurações não secretas.

Nunca são persistidos:

- API keys;
- access tokens;
- refresh tokens;
- passwords;
- client secrets;
- DSNs contendo credencial.

Em serviços dirigidos por credencial, ausência de override significa “auto quando os requisitos estiverem presentes”. O console não deve apresentar `false` como default efetivo desses serviços.

## SaaS e workers

O `AuditJob` carrega somente escolhas não secretas. A superfície inclui:

- `open_web_metrics`;
- `derived_readiness_metrics`;
- `retrieval_metrics`;
- `w3c_validator`;
- `w3c_css_validator`;
- `mdn_observatory`;
- `web_platform_baseline`;
- `pagespeed_enabled`;
- `crux_enabled`;
- `gsc_enabled`;
- `gsc_site_url`;
- `gsc_search_analytics_days`;
- `gsc_search_max_rows`;
- `gsc_final_data_lag_days`;
- `standards_max_urls`;
- `standards_timeout_seconds`.

Regras:

- campo booleano omitido/null dos serviços dirigidos por credencial significa auto por requisitos;
- `false` desliga explicitamente;
- `true` solicita execução, mas requisitos ausentes mantêm a integração não configurada;
- Search Console exige property do próprio job;
- API key/token permanecem no secret store do worker;
- W3C CSS respeita o throttling do serviço público.

O SaaS Pilot usa AUTO por padrão para Web Performance. Abrir o formulário não deve materializar `web_performance=false`. OFF é decisão explícita do usuário.

A API expõe:

```text
GET /api/v1/audit-job-options
GET /api/v1/standards/services
```

O catálogo informa finalidade, grau de relação, escopos, variáveis requeridas, links oficiais, estado e configuração ausente. Valores de credenciais não são retornados.

## Organização dos relatórios

`report/standards.html` concentra serviços, estado operacional, relação, escopo, controles, métricas, fonte e metodologia.

As métricas também são projetadas nas superfícies temáticas:

- `index.html`: resumo executivo com escopo explícito;
- `crawling-discovery.html`: crawlability, indexability, sitemap, canonical, structured data e HTTP operacional;
- `search-intelligence.html`: MRR, visibilidade e métricas IR;
- `web-performance.html`: Open Web Metrics, PageSpeed/Lighthouse e CrUX;
- `observability.html`: Search Console e outcomes externos;
- `context.html`: topologia de ORIGIN, URL, DEVICE_SNAPSHOT e PROFILE_MEASUREMENT.

HTML/CSS conformance permanece detalhada em `standards.html` por URL, sem ser confundida com score de Search & AI Readiness.

Em múltiplas URLs, qualquer consolidação deve indicar denominador/universo. O relatório não usa a primeira URL como representação silenciosa do domínio inteiro e não publica média sem explicar a agregação.

## Impacto SaaS

“Sem custo de provider” não significa “sem custo operacional”. Serviços externos gratuitos podem adicionar:

- egress;
- latência;
- dependência de disponibilidade pública;
- rate limit/quota;
- armazenamento de artifacts;
- exposição de hostname ou URL a terceiros.

O W3C CSS Validator adiciona o throttling mínimo documentado quando o endpoint público é usado. As métricas HTTP operacionais derivadas têm custo de provider zero e zero aquisições adicionais porque reutilizam evidência já persistida.

Para escala SaaS, a ordem preferencial é:

1. coleta local/browser já existente;
2. cálculo derivado sobre evidência persistida;
3. dataset versionado local;
4. API oficial autenticada do cliente;
5. serviço público externo bounded/throttled;
6. self-host de ferramenta gratuita quando volume ou privacidade justificarem.

## Capacidades ainda não materializadas como resultado conclusivo

### Web Platform Baseline completo

O estado e dataset estão modelados, mas falta detector de uso de features com mapeamento reproduzível para `web-features`. Até isso existir, o RASAi retorna `NO_DATA` em vez de inventar cobertura.

### Browsertime / sitespeed.io

É aderente para journeys e múltiplos browsers, mas adiciona runtime, dependências e aquisições próprias. Deve entrar como provider sintético somente quando o ganho superar a sobreposição com Playwright.

Referência: https://www.sitespeed.io/documentation/browsertime/

### WebPageTest

Pode ser provider sintético opcional, mas sobrepõe Lighthouse/Browsertime e adiciona dependência externa.

### SSL Labs

Pode complementar postura TLS, mas uso SaaS exige validação de termos, limites e política comercial antes de ativação automática.

### axe-core direto

Lighthouse já fornece cobertura automatizada baseada no ecossistema axe. Execução adicional só deve entrar quando houver cobertura/proveniência incremental sem dupla contagem.

## Proveniência mínima

Cada nova fonte deve preservar, quando aplicável:

```text
source
methodology
methodology_version
collector
collector_version
scope
observed_at
raw_metrics
source_score
normalized_or_derived_value
```

Os campos podem estar em metadata estruturada desde que permaneçam reabríveis, versionáveis e auditáveis.
