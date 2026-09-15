# Métricas, padrões e serviços de referência

## Objetivo

Este documento define o contrato vigente das métricas fundamentadas em padrões, métodos reconhecidos e serviços externos usados pelo RASAi além do núcleo `SARI-001` / `SCORE-GEO-004`.

Contrato: `STANDARDS-METRICS-001`.

Princípios:

- nenhuma métrica desta família altera o SARI sem regra e mudança metodológica explicitamente versionadas;
- a exceção atual é `BR-GEO-060`, corroboração externa positive-only baseada em Common Crawl, definida por contrato próprio;
- métricas derivadas pelo RASAi são rotuladas como derivadas;
- score ou grade emitido por fonte externa permanece atribuído à própria fonte;
- ausência, desabilitação ou indisponibilidade de integração não é finding do website;
- credenciais nunca são persistidas em INI, `AuditJob`, `audit.db`, HTML ou logs sanitizados;
- chamadas externas são bounded por URLs, timeout, throttling e quota quando aplicável;
- escopos diferentes não são agregados silenciosamente.

Para defaults, faixas e variáveis, consulte [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). Para geração de keys/tokens e links oficiais, consulte [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

## Escopos

| Escopo | Significado | Exemplos |
|---|---|---|
| `ORIGIN` | propriedade/origem | MDN Observatory, Search Console, CrUX History |
| `URL` | recurso específico | W3C Nu, CSS Validator, Common Crawl por URL |
| `URL_SET` | universo explicitamente consolidado | taxas HTTP do conjunto auditado |
| `DEVICE_SNAPSHOT` | captura renderizada por dispositivo | Open Web Metrics, PageSpeed/Lighthouse |
| `PROFILE_MEASUREMENT` | execução sintética com perfil | Apdex |
| `SEARCH_QUERY` | observação orientada a consulta | SERP, MRR, Precision, Recall, nDCG |

Toda consolidação de múltiplas URLs deve declarar universo e fórmula.

## Catálogo vigente

| Serviço ou método | Relação com RASAi | Escopo | Default | Credencial/contexto | Finalidade |
|---|---:|---|---|---|---|
| RASAi Derived Search & AI Readiness Metrics | 5/5 | URL, URL_SET, DEVICE_SNAPSHOT | ligado | não | métricas derivadas de evidência do auditor |
| Information Retrieval Metrics | 5/5 | SEARCH_QUERY | ligado | não | MRR e métricas com relevance judgments explícitos |
| Open Web Performance APIs | 3/5 | DEVICE_SNAPSHOT | ligado | não | Timing, Paint, LCP, CLS, Event Timing |
| W3C Nu HTML Checker | 3/5 | URL | ligado | não | conformidade HTML sem score RASAi artificial |
| W3C CSS Validation Service | 3/5 | URL | ligado | não | conformidade CSS com throttling |
| MDN HTTP Observatory | 2/5 | ORIGIN | ligado | não | headers HTTP e grade da própria fonte |
| Web Platform Baseline / WebDX | 3/5 | URL, DEVICE_SNAPSHOT | ligado; fonte `auto` | sem credencial; fonte WebDX global | compatibilidade de features quando mapeável |
| Google PageSpeed Insights / Lighthouse | 3/5 | URL, DEVICE_SNAPSHOT | auto por credencial | API key | laboratório Lighthouse e categorias Web Quality |
| Chrome UX Report API | 4/5 | URL, ORIGIN, DEVICE_SNAPSHOT | auto por credencial | API key | Core Web Vitals de campo |
| Chrome UX Report History API | 5/5 | ORIGIN, DEVICE_SNAPSHOT | auto por credencial | mesma API key CrUX | série histórica semanal de métricas de campo |
| Google Search Console | 5/5 | ORIGIN, URL, SEARCH_QUERY | auto por OAuth + property | OAuth 2.0 + `siteUrl` | Sitemaps, URL Inspection e Search Analytics |
| Microsoft Clarity Data Export | 5/5 | ORIGIN, URL, DEVICE_SNAPSHOT | desligado | bearer token + opt-in | métricas comportamentais agregadas |
| Common Crawl CDX History | 4/5 | URL | ligado e bounded | sem credencial | presença histórica pública e possível `BR-GEO-060` positiva |

## Estados de integração

```text
DISABLED        serviço não solicitado ou desligado
NOT_CONFIGURED  falta credencial, contexto ou fonte obrigatória sem default aplicável
READY           requisitos mínimos presentes
SUCCESS         coleta concluída
PARTIAL         resultado parcial
NO_DATA         fonte não forneceu dado elegível
ERROR           falha da integração
```

`NO_DATA` e `ERROR` externos não são convertidos em falha do website.

## Controles gerais

| Variável | Default | Finalidade |
|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | métricas derivadas do auditor |
| `RASAI_RETRIEVAL_METRICS` | `true` | Information Retrieval |
| `RASAI_OPEN_WEB_METRICS` | `true` | métricas browser-native |
| `RASAI_W3C_VALIDATOR` | `true` | W3C Nu bounded |
| `RASAI_W3C_CSS_VALIDATOR` | `true` | W3C CSS bounded/throttled |
| `RASAI_MDN_OBSERVATORY` | `true` | scan por origem |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | solicita análise Baseline |
| `RASAI_WEB_FEATURES_DATASET` | `auto` | fonte canônica global WebDX; caminho local é override avançado |
| `RASAI_STANDARDS_MAX_URLS` | `10` | teto de URLs; `0=todas` |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | timeout por request |

## Google PageSpeed Insights / Lighthouse

Referência oficial: <https://developers.google.com/speed/docs/insights/v5/get-started>

O RASAi exige `RASAI_PAGESPEED_API_KEY` para tornar PageSpeed elegível automaticamente. Com key presente e sem override, o serviço pode ficar `READY`. `RASAI_PAGESPEED_ENABLED=false` desliga o serviço.

Criação e restrição da key: [EXTERNAL_CREDENTIALS.md](EXTERNAL_CREDENTIALS.md).

Métricas Lighthouse permanecem atribuídas ao Lighthouse/PageSpeed e não são evidências independentes adicionais quando derivam da mesma chamada.

## Chrome UX Report API e History API

Referências oficiais:

- CrUX API: <https://developer.chrome.com/docs/crux/api/>
- CrUX History API: <https://developer.chrome.com/docs/crux/history-api/>

Ambas usam `RASAI_CRUX_API_KEY`. A History API é controlada por `RASAI_CRUX_HISTORY_ENABLED` e preserva origem e form factor. Ausência de amostra CrUX não é falha do website.

Os dados de campo não são fundidos silenciosamente com Lighthouse lab, Apdex ou Open Web Metrics.

## Google Search Console

Referências oficiais:

- pré-requisitos: <https://developers.google.com/webmaster-tools/v1/prereqs>
- OAuth 2.0: <https://developers.google.com/webmaster-tools/v1/how-tos/authorizing>
- API: <https://developers.google.com/webmaster-tools/v1/api_reference_index>
- Search Analytics: <https://developers.google.com/webmaster-tools/v1/searchanalytics/query>
- URL Inspection: <https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect>
- limites: <https://developers.google.com/webmaster-tools/limits>

Requisitos mínimos: uma property e uma das formas OAuth suportadas.

Modo recomendado para uso repetido:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID=<OAuth Client ID>
RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET=<OAuth Client Secret>
RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN=<OAuth Refresh Token>
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL=<property>
```

Alternativa temporária/manual:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=<OAuth access token>
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL=<property>
```

A property aceita `sc-domain:example.com` ou URL-prefix HTTP(S). No fluxo recomendado, o RASAi obtém um access token imediatamente antes da chamada e o mantém somente em memória. `CLIENT_SECRET`, `REFRESH_TOKEN` e `ACCESS_TOKEN` são secretos e nunca entram no INI. `CLIENT_ID` e a property são configurações não secretas.

Uma Google API Key, normalmente iniciada por `AIza`, não substitui OAuth para dados privados do Search Console. Consulte [GSC_OAUTH.md](GSC_OAUTH.md).

Coleta automática bounded:

| Variável | Default | Faixa |
|---|---:|---:|
| `RASAI_GSC_SEARCH_ANALYTICS_DAYS` | `1` | `0..31` |
| `RASAI_GSC_SEARCH_MAX_ROWS` | `10000` | `1..50000` |
| `RASAI_GSC_FINAL_DATA_LAG_DAYS` | `3` | `0..30` |

`RASAI_GSC_SEARCH_ANALYTICS_DAYS=0` desliga apenas Search Analytics automático.

A property deve pertencer ao próprio contexto do job. Segredos OAuth podem existir no secret store do worker e não trafegam no payload durável.

## Microsoft Clarity Data Export

Referência oficial: <https://learn.microsoft.com/clarity/setup-and-installation/clarity-data-export-api>

Configuração:

```text
RASAI_CLARITY_ENABLED=false
RASAI_CLARITY_API_TOKEN=<segredo>
RASAI_CLARITY_DAYS=1
RASAI_CLARITY_DIMENSIONS=URL,Device
```

A integração exige opt-in explícito. O token sozinho não habilita a coleta. O contrato aceita `1`, `2` ou `3` dias e até três dimensões; `URL` deve estar presente para manter vínculo com o domínio auditado.

O RASAi persiste apenas agregados comportamentais. Não persiste session replay, IDs de visitante/sessão, teclas ou conteúdo de formulário.

## Common Crawl CDX History

Referências oficiais:

- <https://commoncrawl.org/get-started>
- <https://commoncrawl.org/cdxj-index>

Defaults:

```text
RASAI_COMMON_CRAWL_ENABLED=true
RASAI_COMMON_CRAWL_MAX_URLS=3
RASAI_COMMON_CRAWL_INDEX_COUNT=2
```

A integração consulta índices públicos, não baixa WARC e não exige credencial.

Presença histórica pode materializar `BR-GEO-060` somente quando o contrato positivo é atendido. Ausência, erro ou amostra insuficiente não cria `FAIL`, zero ou perda de Coverage/Confidence.

Detalhes: [SARI_EXTERNAL_CRAWL_CORROBORATION.md](SARI_EXTERNAL_CRAWL_CORROBORATION.md).

## Controle agregado de Web Performance

`RASAI_WEB_PERFORMANCE` controla a família externa. `RASAI_PAGESPEED_ENABLED` e `RASAI_CRUX_ENABLED` refinam os serviços individuais.

`RASAI_WEB_PERFORMANCE=false` explícito funciona como hard-off da família. Sem hard-off, serviços credential-driven podem ficar elegíveis quando seus requisitos existem.

## W3C Nu HTML Checker

Referências:

- <https://validator.w3.org/docs/api>
- <https://validator.w3.org/nu/>

O RASAi registra outcome e contagens por URL sem criar score W3C. A execução é limitada por `RASAI_STANDARDS_MAX_URLS` e `RASAI_STANDARDS_TIMEOUT_SECONDS`.

Para volume elevado, self-host do Nu Checker é preferível ao uso intensivo do serviço público.

## W3C CSS Validation Service

Referências:

- <https://jigsaw.w3.org/css-validator/>
- <https://jigsaw.w3.org/css-validator/api.html>
- <https://jigsaw.w3.org/css-validator/manual.html>

O RASAi solicita SOAP 1.2 por URI e preserva os campos emitidos pela fonte quando disponíveis. O serviço público exige throttling; o runtime aplica intervalo e limites locais.

## MDN HTTP Observatory

Referência: <https://developer.mozilla.org/en-US/observatory/docs/faq>

O scan mede postura de segurança HTTP por origem. Grade e score pertencem à fonte. A chamada revela o hostname ao serviço externo e pode ser desligada quando política de privacidade/egress exigir.

## Web Platform Baseline / WebDX

Referências:

- <https://github.com/web-platform-dx/web-features>
- <https://web-platform-dx.github.io/web-features-project/>

Configuração normal:

```text
RASAI_WEB_PLATFORM_BASELINE=true
RASAI_WEB_FEATURES_DATASET=auto
```

`auto` é a política canônica de fonte do dataset global `web-platform-dx/web-features`. O dataset-base não varia por domínio auditado; o domínio determina quais features são observadas na página. Um caminho para arquivo local existente continua aceito como override avançado para pin/versionamento e reprodutibilidade.

O default `auto` atende a configuração mínima da fonte e evita exigir ao usuário um caminho local sem necessidade. Isso não significa que a análise de compatibilidade já foi materializada: sem detector/mapeamento reproduzível suficiente, o estado de resultado permanece `NO_DATA` e nenhuma compatibilidade é inventada.

Contrato detalhado: [WEB_PLATFORM_BASELINE.md](WEB_PLATFORM_BASELINE.md).

## Open Web Performance APIs

Contrato: `OPEN-WEB-METRICS-001`.

Referências:

- <https://www.w3.org/TR/performance-timeline/>
- <https://www.w3.org/TR/navigation-timing-2/>
- <https://www.w3.org/TR/resource-timing/>
- <https://www.w3.org/TR/event-timing/>

O collector lê o browser já aberto e não cria nova navegação.

## Métricas derivadas RASAi

Essas métricas usam evidências já persistidas e não são scores oficiais dos fornecedores referenciados.

### Crawlability Coverage

```text
URLs com BR-GEO-005 = PASS
---------------------------------- x 100
URLs com recuperabilidade determinável
```

### Indexability Coverage

A consolidação por URL considera recuperabilidade, documento analisável, soft-404 e diretivas observadas. O contrato usa `BR-GEO-005`, `006`, `009`, `011`, `012` e `016`.

### Sitemap Coverage of Audited URLs

Mede apenas o universo efetivamente auditado e não afirma cobertura integral de todas as URLs do site.

### Canonical

- `Canonical Declaration Coverage`;
- `Canonical Consistency Rate`, baseada em `BR-GEO-013`.

### Structured Data

- `Structured Data Coverage`;
- `Structured Data Validity Rate`, baseada em `BR-GEO-034`;
- `Structured Data to Visible Content Consistency`, baseada em `BR-GEO-036`;
- `Structured Entity Consistency`, baseada em `BR-GEO-037`.

Essas métricas não afirmam elegibilidade para rich result não medido.

### HTTP operacional por aquisição física

A aquisição HTTP direta ocorre uma vez por URL e é deduplicada por `page_id`. Mobile/Desktop não multiplicam a mesma request física.

Métricas incluem taxas 2xx/4xx/5xx, transport errors/timeouts, redirects e percentis p50/p75/p95/p99 de `raw_http.duration_ms`. Esses percentis não representam TTFB de browser, CrUX/RUM, Core Web Vital ou Apdex.

Detalhes: [OPERATIONAL_HTTP_METRICS.md](OPERATIONAL_HTTP_METRICS.md).

### TTFB p50/p75/p95/p99

TTFB vem de Open Web Metrics no `DEVICE_SNAPSHOT`. Não é RUM e não equivale a percentil CrUX.

## Information Retrieval

Cálculo local, sem serviço externo obrigatório.

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

O RASAi não transforma resultado não julgado em irrelevante. Precision, Recall e nDCG só são publicados quando os julgamentos necessários existem de forma reproduzível.

## Console e `rasai-console.ini`

Podem ser persistidos:

- toggles de serviço;
- property Search Console;
- OAuth Client ID do Search Console;
- limites GSC;
- limites e timeout de standards;
- fonte `auto` ou caminho local versionado do dataset WebDX;
- configurações Clarity não secretas;
- limites Common Crawl;
- demais configurações não secretas previstas pelo console.

Nunca são persistidos API keys, access tokens, refresh tokens, passwords, client secrets ou DSNs com credencial.

## SaaS e workers

`AuditJob` carrega escolhas não secretas. Secrets permanecem na fronteira do worker/integration.

Regras:

- campo booleano omitido de serviço credential-driven significa auto por requisitos;
- `false` desliga explicitamente;
- `true` solicita execução, mas requisito ausente mantém `NOT_CONFIGURED`;
- Search Console exige property do próprio job e uma forma OAuth completa;
- Clarity exige opt-in explícito;
- Common Crawl não exige secret;
- serviços públicos respeitam throttling e limites.

A API expõe:

```text
GET /api/v1/audit-job-options
GET /api/v1/standards/services
```

O catálogo retorna metadados, nomes de variáveis e estado, nunca valores de credenciais. Consulte [WEB_API_FOUNDATION.md](WEB_API_FOUNDATION.md).

## Organização dos relatórios

`report/standards.html` é a superfície canônica da família e permanece presente mesmo quando uma capacidade não é executada.

As métricas também são projetadas nas superfícies temáticas quando há dados:

- `index.html`: resumo executivo;
- `crawling-discovery.html`: discovery, sitemap, canonical, structured data e HTTP operacional;
- `search-intelligence.html`: MRR e métricas IR;
- `web-performance.html`: Open Web Metrics, PageSpeed/Lighthouse, CrUX e CrUX History;
- `observability.html`: Search Console, Clarity, Common Crawl e outros outcomes externos;
- `context.html`: topologia de escopos.

Em múltiplas URLs, toda consolidação deve indicar denominador/universo.

## Impacto operacional SaaS

Ausência de cobrança do provider não significa custo operacional zero. Serviço externo pode adicionar egress, latência, rate limit, armazenamento e exposição de hostname/URL a terceiros.

Para escala, priorize coleta local já existente, cálculo sobre evidência persistida, dataset local versionado e API oficial autenticada antes de depender de serviço público compartilhado.

## Capacidades sem resultado conclusivo no contrato atual

### Web Platform Baseline completo

A fonte do dataset e o estado são modelados, com `auto` como default canônico. Sem detector/mapeamento suficiente o RASAi retorna `NO_DATA`.

### Browsertime / sitespeed.io

Não integra o runtime atual. Referência: <https://www.sitespeed.io/documentation/browsertime/>.

### WebPageTest

Não integra o runtime atual como provider sintético.

### SSL Labs

Não integra o runtime atual automaticamente.

### axe-core direto

Não existe execução adicional separada apenas para duplicar a cobertura já recebida via Lighthouse.

## Proveniência mínima

Cada fonte deve preservar, quando aplicável:

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

Os campos podem residir em metadata estruturada desde que permaneçam reabríveis, versionáveis e auditáveis.