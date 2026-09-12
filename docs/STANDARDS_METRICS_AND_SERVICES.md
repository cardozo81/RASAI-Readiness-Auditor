# Métricas, padrões e serviços de referência

## Objetivo

Este documento define o contrato vigente das métricas fundamentadas em padrões, métodos de mercado e serviços externos usados pelo RASAi além do núcleo `SARI-001` / `SCORE-GEO-004`.

O RASAi está em fase pré-publicação. Este documento descreve somente o comportamento atual que deve ser validado e publicado. Não existem versões comerciais anteriores a preservar e não se deve interpretar coexistência de controles internos como compatibilidade com uma versão pública anterior.

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
| `ORIGIN` | propriedade/origem como unidade | MDN Observatory, propriedade Search Console, sitemap externo |
| `URL` | recurso/endereço específico | W3C Nu, W3C CSS, canonical, indexability por URL |
| `URL_SET` | consolidação explícita do universo de URLs auditado | HTTP 2xx/4xx/5xx, timeout, redirects e cobertura física M2 |
| `DEVICE_SNAPSHOT` | captura renderizada por dispositivo | Open Web Metrics, structured data renderizado, contexto de browser |
| `PROFILE_MEASUREMENT` | execução sintética com perfil de rede/device | Apdex e medições sintéticas dedicadas |
| `SEARCH_QUERY` | observação ou avaliação orientada a consulta | SERP visibility, MRR, Precision, Recall, nDCG |

Uma consolidação de várias URLs deve declarar o universo e a fórmula. Média implícita entre páginas não é permitida.

## Catálogo vigente

| Serviço ou método | Relação com RASAi | Escopo | Default operacional | Credencial/contexto | Finalidade |
|---|---:|---|---|---|---|
| RASAi Derived Search & AI Readiness Metrics | 5/5 | URL, URL_SET, DEVICE_SNAPSHOT | ligado | não | crawlability, indexability, sitemap, canonical, structured data e operação HTTP derivada |
| Information Retrieval Metrics | 5/5 | SEARCH_QUERY | ligado | não | MRR, visibilidade e métricas com relevance judgments explícitos |
| Open Web Performance APIs | 3/5 | DEVICE_SNAPSHOT | ligado | não | Navigation Timing, Resource Timing, Paint, LCP, CLS, Event Timing e sinais relacionados |
| W3C Nu HTML Checker | 3/5 | URL | ligado | não | conformidade HTML sem inventar score W3C |
| W3C CSS Validation Service | 3/5 | URL | ligado | não | conformidade CSS com SOAP 1.2 oficial e throttling mínimo de 1 segundo |
| MDN HTTP Observatory | 2/5 | ORIGIN | ligado | não | postura de headers HTTP e grade/score emitidos pela fonte |
| Web Platform Baseline / WebDX | 3/5 | URL, DEVICE_SNAPSHOT | solicitado por default | dataset e detector reproduzível | compatibilidade de recursos Web quando há mapeamento confiável |
| Google PageSpeed Insights / Lighthouse | 3/5 | URL, DEVICE_SNAPSHOT | auto por credencial | API key | laboratório Lighthouse e categorias Web Quality |
| Chrome UX Report API | 4/5 | URL, ORIGIN, DEVICE_SNAPSHOT | auto por credencial | API key | Core Web Vitals de campo agregados |
| Google Search Console | 5/5 | ORIGIN, URL, SEARCH_QUERY | auto por credencial + property | OAuth 2.0 + `siteUrl` | Sitemaps, URL Inspection e Search Analytics observacional |

## Estados de integração

O estado operacional usa três conceitos principais:

- `DISABLED`: serviço não solicitado ou desligado explicitamente;
- `NOT_CONFIGURED`: solicitado, mas falta requisito obrigatório como dataset, credencial ou contexto;
- `READY`: requisitos mínimos estão presentes e a execução é elegível.

Após uma tentativa podem existir estados de execução como `SUCCESS`, `PARTIAL`, `NO_DATA` ou `ERROR`. Falha de provider não é convertida em falha do website.

## Variáveis gerais

| Variável | Default | Valores | Efeito |
|---|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | booleano | consolida métricas derivadas de Search & AI Readiness e HTTP operacional |
| `RASAI_RETRIEVAL_METRICS` | `true` | booleano | calcula métricas de Information Retrieval quando há dados suficientes |
| `RASAI_OPEN_WEB_METRICS` | `true` | booleano | coleta métricas browser-native no snapshot já aberto |
| `RASAI_W3C_VALIDATOR` | `true` | booleano | habilita W3C Nu bounded |
| `RASAI_W3C_CSS_VALIDATOR` | `true` | booleano | habilita W3C CSS bounded e throttled |
| `RASAI_MDN_OBSERVATORY` | `true` | booleano | habilita scan MDN HTTP Observatory por origem |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | booleano | solicita análise Baseline; sem dataset/detector fica `NOT_CONFIGURED` ou `NO_DATA` |
| `RASAI_WEB_FEATURES_DATASET` | sem default | caminho de arquivo | dataset WebDX/web-features versionado |
| `RASAI_STANDARDS_MAX_URLS` | `10` | inteiro `>= 0` | teto para checks externos por URL; `0` significa todas as URLs auditadas |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | número `> 0` e `< 3600` | timeout por request desta família |

Todos os controles acima podem ser desligados explicitamente pelo usuário.

## Google PageSpeed Insights / Lighthouse

### Para que serve

Coleta medição de laboratório Lighthouse e categorias suportadas pela PageSpeed Insights API.

Referência oficial:

- https://developers.google.com/speed/docs/insights/v5/get-started

### Política RASAi

A API pode aceitar determinados usos sem chave, mas o RASAi exige API key para automação. Isso evita depender de quota anônima ou comportamento operacional incerto.

Variáveis:

```text
RASAI_PAGESPEED_API_KEY=<segredo>
RASAI_PAGESPEED_ENABLED=true|false
```

Sem `RASAI_PAGESPEED_API_KEY`, o serviço não executa. Com a chave presente e sem override de `RASAI_PAGESPEED_ENABLED`, o serviço fica elegível automaticamente. `RASAI_PAGESPEED_ENABLED=false` sempre desliga PageSpeed.

### Criar a chave

1. Acesse https://console.cloud.google.com/.
2. Crie ou selecione um projeto.
3. Habilite a PageSpeed Insights API.
4. Abra `APIs & Services > Credentials`.
5. Crie uma API key.
6. Restrinja a chave de acordo com o ambiente de execução.
7. Injete a chave somente por secret store ou variável protegida.

## Chrome UX Report API

### Para que serve

Fornece dados agregados de experiência real para URL/origin quando o target possui cobertura no CrUX.

Referência oficial:

- https://developer.chrome.com/docs/crux/api/

Variáveis:

```text
RASAI_CRUX_API_KEY=<segredo>
RASAI_CRUX_ENABLED=true|false
```

Sem a chave, o serviço não executa. Com a chave e sem override, o serviço fica elegível automaticamente. `RASAI_CRUX_ENABLED=false` é hard-off do CrUX dedicado.

### Criar a chave

1. Acesse https://console.cloud.google.com/.
2. Crie ou selecione um projeto.
3. Habilite `Chrome UX Report API`.
4. Abra `APIs & Services > Credentials`.
5. Crie e restrinja uma API key.
6. Injete-a como `RASAI_CRUX_API_KEY` somente em ambiente seguro.

PageSpeed pode retornar dados de campo em determinadas respostas, mas o RASAi mantém CrUX dedicado como fonte identificável e não trata duas observações correlacionadas como evidências independentes para score.

## Controle agregado de Web Performance

`RASAI_WEB_PERFORMANCE` é o controle agregado vigente do runtime externo de Web Performance. Os toggles `RASAI_PAGESPEED_ENABLED` e `RASAI_CRUX_ENABLED` refinam a seleção por serviço.

Um `RASAI_WEB_PERFORMANCE=false` explícito interrompe a família externa para aquela execução. Quando o controle agregado não é explicitamente desligado, os serviços individuais podem ser ativados conforme seus próprios requisitos.

Isso é um contrato atual de composição, não referência a uma versão pública anterior.

## Google Search Console

### Para que serve

A Search Console API fornece dados autenticados da propriedade verificada, incluindo:

- Search Analytics;
- Sitemaps;
- properties/sites;
- URL Inspection.

Referências oficiais:

- visão geral: https://developers.google.com/webmaster-tools
- referência: https://developers.google.com/webmaster-tools/v1/api_reference_index
- pré-requisitos: https://developers.google.com/webmaster-tools/v1/prereqs
- OAuth 2.0: https://developers.google.com/webmaster-tools/v1/how-tos/authorizing
- Search Analytics: https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- URL Inspection: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
- limites de uso: https://developers.google.com/webmaster-tools/limits
- orientação para obtenção de dados de performance: https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data

### Requisitos mínimos

O serviço só fica elegível quando existem simultaneamente:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=<segredo OAuth temporário>
RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL=<property>
```

A property aceita:

```text
sc-domain:example.com
```

ou propriedade URL-prefix absoluta, por exemplo:

```text
https://www.example.com/
```

`RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL` não é segredo e pode ser persistida no INI ou transportada no `AuditJob`. O access token nunca pode ser persistido nessas superfícies.

### OAuth e criação da credencial

Search Console não usa uma API key simples para dados privados da conta. O fluxo recomendado é OAuth 2.0.

1. Acesse https://console.cloud.google.com/.
2. Crie ou selecione um projeto Google Cloud.
3. Habilite a Search Console API.
4. Configure a tela/consentimento OAuth conforme o tipo da aplicação.
5. Crie um OAuth Client compatível com o cenário local ou SaaS.
6. Solicite somente os scopes necessários, preferencialmente `https://www.googleapis.com/auth/webmasters.readonly` quando leitura for suficiente.
7. Faça o fluxo de autorização com o usuário que possui acesso à property.
8. No runtime local, forneça o access token temporário por `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`.
9. No SaaS, refresh token/client secret devem permanecer em secret store e nunca entrar em `AuditJob` ou `audit.db`.

O token sozinho não torna o serviço `READY`: a property também é obrigatória.

### Coleta automática bounded

Quando o serviço está `READY`, a finalização da auditoria reutiliza os coletores oficiais já existentes no RASAi e grava os resultados em `observability.db` + `artifacts/observability`.

A coleta automática inclui:

- Sitemaps da property;
- URL Inspection para no máximo `RASAI_STANDARDS_MAX_URLS` URLs;
- Search Analytics para um período finalizado curto.

Política de Search Analytics:

| Variável | Default | Faixa | Finalidade |
|---|---:|---:|---|
| `RASAI_GSC_SEARCH_ANALYTICS_DAYS` | `1` | `0..31` | dias consultados; `0` desliga apenas Search Analytics automático |
| `RASAI_GSC_SEARCH_MAX_ROWS` | `10000` | `1..50000` | teto de linhas normalizadas por auditoria |
| `RASAI_GSC_FINAL_DATA_LAG_DAYS` | `3` | `0..30` | defasagem para preferir dados finalizados |

O default de 3 dias segue a orientação pública do Google de que dados de Search Analytics normalmente ficam disponíveis após cerca de 2 a 3 dias. O RASAi consulta `dataState=final` nessa automação.

A documentação pública do Google informa que URL Inspection possui quota por property e que Search Analytics possui limites de carga. Por isso o default do RASAi é bounded e não consulta todas as URLs automaticamente.

Desligamento total:

```text
RASAI_GSC_ENABLED=false
```

URL Inspection descreve o estado conhecido pelo índice do Google. Não é teste live universal de indexabilidade e não substitui as métricas determinísticas locais.

### Isolamento SaaS

No SaaS, a property deve pertencer ao próprio `AuditJob`. Um worker não pode usar silenciosamente uma property global para um job que não informou `gsc_site_url`. Essa regra evita vazamento de contexto entre tenants/properties.

O worker pode receber o token por secret store. O token não trafega no payload durável.

## W3C Nu HTML Checker

### Para que serve

Valida conformidade HTML e retorna mensagens estruturadas. O RASAi registra outcome e contagens, sem criar um suposto score oficial do W3C.

Referências oficiais:

- https://validator.w3.org/docs/api
- https://validator.w3.org/nu/

Comportamento:

- default: ligado;
- credencial: não necessária;
- escopo: `URL`;
- URLs limitadas por `RASAI_STANDARDS_MAX_URLS`;
- timeout limitado por `RASAI_STANDARDS_TIMEOUT_SECONDS`;
- resultados: `PASS`, `FAIL`, `INDETERMINATE` ou `ERROR` e contagens de mensagens.

Desligamento:

```text
RASAI_W3C_VALIDATOR=false
```

O endpoint público deve ser usado de forma bounded. Para SaaS em volume alto, self-host do Nu Checker é preferível a depender de infraestrutura pública de terceiros.

## W3C CSS Validation Service

### Para que serve

Valida CSS associado à URL e retorna, pela interface SOAP 1.2 oficial, validade e contagens de erros/warnings. O RASAi não cria score próprio.

Referências oficiais:

- serviço: https://jigsaw.w3.org/css-validator/
- API SOAP 1.2: https://jigsaw.w3.org/css-validator/api.html
- parâmetros/manual: https://jigsaw.w3.org/css-validator/manual.html

Comportamento:

- default: ligado;
- credencial: não necessária;
- escopo: `URL`;
- toggle: `RASAI_W3C_CSS_VALIDATOR`;
- URLs limitadas por `RASAI_STANDARDS_MAX_URLS`;
- timeout limitado por `RASAI_STANDARDS_TIMEOUT_SECONDS`;
- perfil solicitado: `css3`;
- resposta: `PASS`, `FAIL` ou `ERROR`, preservando `validity`, `errorcount`, `warningcount`, `csslevel`, `checkedby` e data quando disponíveis.

A documentação oficial pede que automações sobre conjuntos de documentos aguardem pelo menos 1 segundo entre requests ao serviço público. O runtime do RASAi aplica `PUBLIC_MIN_INTERVAL_SECONDS=1.0` entre URLs.

Desligamento:

```text
RASAI_W3C_CSS_VALIDATOR=false
```

Para SaaS em volume alto, uma implantação controlada/self-host deve ser preferida ao uso intensivo do serviço público.

Detalhes: [W3C_CSS_VALIDATION.md](W3C_CSS_VALIDATION.md).

## MDN HTTP Observatory

### Para que serve

Avalia postura de segurança HTTP e retorna grade/score calculados pela própria fonte.

Referência oficial:

- https://developer.mozilla.org/en-US/observatory/docs/faq

Comportamento:

- default: ligado;
- credencial: não necessária;
- escopo: `ORIGIN`;
- uma origem é consultada uma vez, não uma vez por URL/device;
- grade, score, testes e versão de algoritmo da fonte são preservados quando retornados;
- não altera SARI.

Desligamento:

```text
RASAI_MDN_OBSERVATORY=false
```

O scan externo revela o hostname ao serviço público. Esse efeito de privacidade é diferente de uma análise local. Para SaaS em escala ou ambientes restritos, avaliar execução controlada/self-host quando disponível.

## Web Platform Baseline / WebDX

### Para que serve

Baseline classifica disponibilidade de recursos Web entre browsers. O projeto `web-features`, coordenado pelo W3C WebDX Community Group, fornece dados versionáveis para esses status.

Referências:

- https://github.com/web-platform-dx/web-features
- https://web-platform-dx.github.io/web-features-project/

Configuração:

```text
RASAI_WEB_PLATFORM_BASELINE=true|false
RASAI_WEB_FEATURES_DATASET=<caminho versionado>
```

O RASAi não produz cobertura Baseline apenas porque um dataset existe. É necessário também mapear recursos efetivamente usados pela página para IDs `web-features` de forma reproduzível.

Estados esperados:

- sem dataset: `NOT_CONFIGURED`;
- dataset disponível, mas sem detector/mapeamento suficiente: `NO_DATA`;
- nenhuma nota de compatibilidade é inventada por aproximação silenciosa.

## Open Web Performance APIs

O collector `OPEN-WEB-METRICS-001` lê métricas do browser já aberto e não cria nova navegação contra o target.

Referências:

- Performance Timeline: https://www.w3.org/TR/performance-timeline/
- Navigation Timing: https://www.w3.org/TR/navigation-timing-2/
- Resource Timing: https://www.w3.org/TR/resource-timing/
- Event Timing: https://www.w3.org/TR/event-timing/

Default:

```text
RASAI_OPEN_WEB_METRICS=true
```

Desligamento:

```text
RASAI_OPEN_WEB_METRICS=false
```

## Métricas derivadas RASAi

As métricas abaixo são calculadas sobre evidência persistida. Elas não são scores oficiais dos fornecedores citados nas referências.

### Crawlability Coverage

Relação: 5/5.

```text
URLs com BR-GEO-005 = PASS
---------------------------------- x 100
URLs com recuperabilidade determinável
```

Estados desconhecidos não são convertidos em falha.

### Indexability Coverage

Relação: 5/5.

A consolidação por URL usa checks determinísticos de recuperabilidade, conteúdo analisável, soft-404 e diretivas observadas por snapshot. A URL só é positiva quando o conjunto aplicável é determinável e aprovado em todos os snapshots observados.

Contrato atual usa:

- `BR-GEO-005`;
- `BR-GEO-006`;
- `BR-GEO-009`;
- `BR-GEO-011`;
- `BR-GEO-012`;
- `BR-GEO-016`.

O resultado é RASAi-derived. Não é "Google Indexability Score".

### Sitemap Coverage of Audited URLs

```text
URLs auditadas cuja proveniência inclui SITEMAP
----------------------------------------------- x 100
URLs do universo efetivamente auditado
```

A métrica não afirma cobertura de todas as URLs existentes no site. Mede o universo efetivamente auditado.

### Canonical

Métricas:

- `Canonical Declaration Coverage`: snapshots com canonical explícito / snapshots observados;
- `Canonical Consistency Rate`: `BR-GEO-013 = PASS` / snapshots com canonical declarado.

Ausência de canonical e canonical inválido permanecem conceitos separados.

### Structured Data

Métricas:

- `Structured Data Coverage`;
- `Structured Data Validity Rate`, baseada em `BR-GEO-034`;
- `Structured Data to Visible Content Consistency`, baseada em `BR-GEO-036`;
- `Structured Entity Consistency`, baseada em `BR-GEO-037`.

Elas não afirmam elegibilidade para rich result específico quando essa condição não foi medida.

### HTTP operacional por aquisição física

Relação: 4/5.

A aquisição M2 ocorre uma vez por URL. O mesmo `raw_http` pode ser preservado em múltiplos snapshots de device; por isso o contrato deduplica por `page_id` antes de calcular taxas. Mobile/Desktop não multiplicam a mesma request física.

Métricas:

- `Physical HTTP Observation Coverage`;
- `HTTP 2xx Success Rate`;
- `HTTP 4xx Rate`;
- `HTTP 5xx Rate`;
- `Transport Error Rate`;
- `Transport Timeout Rate`;
- `Redirect Rate`;
- `Redirect Completion Rate`;
- `Cross-host Redirect Rate`.

Para 2xx/4xx/5xx, o denominador é o conjunto de aquisições físicas observadas. Timeout e erro de transporte permanecem no denominador, evitando inflar artificialmente a taxa de sucesso.

Essas métricas usam `scope=URL_SET` e não criam request adicional ao alvo.

Detalhes de fórmulas e fronteiras: [OPERATIONAL_HTTP_METRICS.md](OPERATIONAL_HTTP_METRICS.md).

### TTFB p50/p75/p95/p99

TTFB vem do `OPEN-WEB-METRICS-001` no `DEVICE_SNAPSHOT` e representa o universo browser observado na auditoria. Não é RUM e não equivale a percentil CrUX.

HTTP físico M2 e TTFB de browser permanecem metodologias separadas.

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

- `Precision@10` e `Judged-result MRR@10` só são publicados quando o top 10 observado está totalmente julgado;
- `nDCG@10` exige julgamentos explícitos e um ideal reproduzível (`ideal_relevance_grades`);
- `Recall@10` exige `total_relevant_documents` explícito para a query;
- `Judgment Coverage@10` informa quanto do top 10 possui julgamento explícito.

Posição alta não é usada como sinônimo de relevância e IA não cria qrels silenciosamente.

## Console e rasai-console.ini

A categoria **Métricas e padrões** expõe os controles desta família.

Podem ser persistidos no INI:

- toggles de serviço, incluindo HTML/CSS validators;
- property Search Console;
- período/limites GSC;
- limites e timeout de standards;
- caminho de dataset WebDX;
- demais configurações não secretas.

Nunca são persistidos no INI:

- API keys;
- access tokens;
- refresh tokens;
- passwords;
- client secrets;
- DSNs contendo credencial.

Nos serviços dirigidos por credencial, ausência de override significa "auto quando os requisitos estiverem presentes". O console não deve apresentar `false` como se fosse o default efetivo desses serviços.

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
- `true` solicita execução, mas credencial/contexto ausente mantém a integração não configurada;
- Search Console exige property do próprio job para ativação automática no SaaS;
- API key/token permanecem no secret store do worker;
- W3C CSS não exige segredo, mas respeita throttling mínimo de 1 segundo quando usa o serviço público.

O SaaS Pilot usa AUTO por padrão para a família externa de Web Performance. Ele não deve materializar `web_performance=false` apenas por abrir o formulário. OFF é uma decisão explícita do usuário.

A API SaaS expõe:

```text
GET /api/v1/audit-job-options
GET /api/v1/standards/services
```

O catálogo de serviços fornece finalidade, relação com RASAi, escopos, variáveis requeridas, links oficiais, estado de configuração e itens ausentes. Valores de credencial nunca são retornados.

A visão geral do SaaS Pilot mostra o catálogo de serviços, grau de relação, escopo, estado e configuração faltante. O estado reflete o processo API como capability hint; a aptidão final pode depender do secret store do worker.

## Organização dos relatórios

`report/standards.html` concentra:

- serviços e estado operacional;
- relação com o RASAi;
- escopo;
- toggle;
- necessidade de credencial;
- métricas materializadas;
- fonte e metodologia.

As métricas também são projetadas nas superfícies onde fazem sentido:

- `index.html`: resumo executivo com escopo explícito;
- `crawling-discovery.html`: crawlability, indexability, sitemap, canonical, structured data e HTTP operacional por aquisição física;
- `search-intelligence.html`: MRR, visibilidade e métricas IR;
- `web-performance.html`: Open Web Metrics, PageSpeed/Lighthouse e CrUX;
- `observability.html`: Search Console e demais outcomes externos;
- `context.html`: topologia de ORIGIN, URL, DEVICE_SNAPSHOT e PROFILE_MEASUREMENT.

HTML/CSS conformance permanece detalhada em `standards.html` por URL, sem ser confundida com score de Search & AI Readiness.

Em múltiplas URLs, qualquer consolidação deve indicar denominador/universo. O relatório não usa a primeira URL como se representasse o domínio inteiro e não publica média sem explicar a agregação.

## Impacto SaaS

"Sem custo de provider" não significa "sem custo operacional". Serviços externos gratuitos podem adicionar:

- egress;
- latência;
- dependência de disponibilidade pública;
- rate limit/quota;
- armazenamento de artifacts;
- exposição de hostname ou URL a terceiros.

O W3C CSS Validator adiciona no mínimo o throttling documentado de 1 segundo entre URLs quando o endpoint público é usado. `RASAI_STANDARDS_MAX_URLS` limita o universo por auditoria.

As métricas HTTP operacionais derivadas, por outro lado, têm custo de provider zero e criam zero aquisições adicionais, pois reutilizam o `raw_http` M2 persistido.

Para escala SaaS, a ordem preferencial é:

1. coleta local/browser já existente;
2. cálculo derivado sobre evidência persistida;
3. dataset versionado local;
4. API oficial autenticada do cliente;
5. serviço público externo bounded/throttled;
6. self-host de ferramentas gratuitas quando volume/privacidade justificarem.

## Capacidades ainda não materializadas como default conclusivo

### Web Platform Baseline completo

O estado e dataset estão modelados, mas falta um detector de uso de features Web com mapeamento reproduzível para `web-features`. Até isso existir, o RASAi retorna `NO_DATA` em vez de inventar cobertura.

### Browsertime / sitespeed.io

É tecnicamente aderente para journeys e múltiplos browsers. Deve entrar como `SyntheticMeasurementProvider` quando o ganho superar a sobreposição com Playwright.

Referência: https://www.sitespeed.io/documentation/browsertime/

### WebPageTest

Pode ser provider sintético opcional, mas sobrepõe Lighthouse/Browsertime e adiciona dependência externa.

### SSL Labs

Pode complementar postura TLS, mas uso SaaS exige validação de termos, limites e política comercial antes de ativação automática.

### axe-core direto

Lighthouse já fornece uma camada automatizada de acessibilidade baseada no ecossistema axe. Uma execução adicional só deve ser incluída se trouxer cobertura/proveniência adicional sem dupla contagem.

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
