# Métricas, padrões e serviços de referência

## Objetivo

Este documento define o contrato de métricas fundamentadas em padrões, métodos de mercado e serviços externos usados pelo RASAi além do núcleo `SARI-001` / `SCORE-GEO-004`.

A finalidade é ampliar diagnóstico e observabilidade sem transformar sinais heterogêneos em um único score arbitrário.

Princípios obrigatórios:

- nenhuma métrica desta superfície altera `SARI-001` ou `SCORE-GEO-004` sem nova versão metodológica explícita;
- métricas derivadas pelo RASAi são identificadas como derivadas e nunca atribuídas a Google, W3C, MDN, WebDX ou outra entidade;
- scores ou grades emitidos por fonte externa são preservados como valores da fonte;
- ausência de integração opcional não é finding do website;
- todo serviço possui toggle próprio;
- serviço sem cobrança de provider e sem credencial obrigatória fica habilitado por default;
- serviço que requer credencial permanece inativo até a credencial existir;
- segredos nunca são persistidos em `rasai-console.ini` nem em payload de `AuditJob`;
- escolhas não secretas do console podem ser persistidas em `rasai-console.ini`;
- chamadas externas são bounded por quantidade de URLs e timeout;
- dados são separados por `ORIGIN`, `URL`, `DEVICE_SNAPSHOT`, `PROFILE_MEASUREMENT` ou `SEARCH_QUERY`, conforme a natureza da evidência.

Contrato de implementação: `STANDARDS-METRICS-001`.

## Catálogo

| Serviço ou método | Relação com RASAi | Escopo | Default | Credencial | Finalidade |
|---|---:|---|---|---|---|
| RASAi Derived Search & AI Readiness Metrics | 5/5 | ORIGIN, URL, DEVICE_SNAPSHOT | ligado | não | consolidar crawlability, indexability, canonical, sitemap, structured data e disponibilidade a partir de evidência persistida |
| Information Retrieval Metrics | 5/5 | SEARCH_QUERY, ORIGIN | ligado | não | MRR e, quando existem julgamentos explícitos, Precision@k, Recall@k e nDCG@k |
| Open Web Performance APIs | 3/5 | DEVICE_SNAPSHOT | ligado | não | Navigation Timing, Resource Timing, Paint, LCP, CLS, Event Timing e sinais relacionados no browser já aberto |
| W3C Nu HTML Checker | 3/5 | URL | ligado | não | validar conformidade HTML e preservar erros/warnings sem inventar score oficial |
| MDN HTTP Observatory | 2/5 | ORIGIN | ligado | não | avaliar postura de headers HTTP e preservar grade/score da própria fonte |
| Web Platform Baseline / WebDX | 3/5 | URL, DEVICE_SNAPSHOT | ligado | dataset versionado | classificar recursos Web por disponibilidade entre browsers quando o detector/dataset estiver materializado |
| Google PageSpeed Insights / Lighthouse | 3/5 | URL, DEVICE_SNAPSHOT | auto após credencial | API key | laboratório Lighthouse e categorias de Web Quality |
| Chrome UX Report API | 4/5 | URL, ORIGIN, DEVICE_SNAPSHOT | auto após credencial | API key | Core Web Vitals de campo agregados |
| Google Search Console | 5/5 | ORIGIN, URL, SEARCH_QUERY | auto após credencial e contexto | OAuth 2.0 | Search Analytics, sitemaps, properties e URL Inspection |

## Variáveis de controle

### Serviços sem credencial obrigatória

| Variável | Default efetivo | Valores | Efeito |
|---|---|---|---|
| `RASAI_DERIVED_READINESS_METRICS` | `true` | `true` / `false` | liga/desliga consolidações derivadas de readiness |
| `RASAI_RETRIEVAL_METRICS` | `true` | `true` / `false` | liga/desliga métricas de Information Retrieval |
| `RASAI_OPEN_WEB_METRICS` | `true` | `true` / `false` | liga/desliga métricas browser-native sem nova navegação |
| `RASAI_W3C_VALIDATOR` | `true` | `true` / `false` | liga/desliga W3C Nu Checker |
| `RASAI_MDN_OBSERVATORY` | `true` | `true` / `false` | liga/desliga MDN HTTP Observatory |
| `RASAI_WEB_PLATFORM_BASELINE` | `true` | `true` / `false` | habilita a capacidade Baseline; sem dataset/detector suficiente fica `NOT_CONFIGURED` ou `NO_DATA` |
| `RASAI_WEB_FEATURES_DATASET` | sem default | caminho | aponta para dataset versionado WebDX/web-features quando disponível |
| `RASAI_STANDARDS_MAX_URLS` | `10` | inteiro `>= 0` | limita URLs enviadas a validadores externos; `0` significa todo o universo auditado |
| `RASAI_STANDARDS_TIMEOUT_SECONDS` | `20` | número `> 0` | timeout por request externo desta família |

### Serviços com credencial

| Variável de serviço | Credencial | Default sem credencial | Default com credencial | Desligamento explícito |
|---|---|---|---|---|
| `RASAI_PAGESPEED_ENABLED` | `RASAI_PAGESPEED_API_KEY` | desligado | ligado quando não há override | `RASAI_PAGESPEED_ENABLED=false` |
| `RASAI_CRUX_ENABLED` | `RASAI_CRUX_API_KEY` | desligado | ligado quando não há override | `RASAI_CRUX_ENABLED=false` |
| `RASAI_GSC_ENABLED` | `RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN` | desligado | elegível quando não há override e o contexto mínimo existe | `RASAI_GSC_ENABLED=false` |

`RASAI_WEB_PERFORMANCE` permanece como macro legado de compatibilidade para PageSpeed/CrUX. Um `false` explícito nesse macro continua sendo hard-off. Os novos toggles permitem controle individual por serviço.

## Persistência do console

O menu de variáveis do `rasai-console` expõe os toggles desta família na categoria **Métricas e padrões**.

Regras de persistência:

- toggles, limites, timeout e caminho de dataset são não secretos e podem ser salvos na seção `[environment]` de `rasai-console.ini`;
- API keys, tokens OAuth, passwords, client secrets e DSNs com credencial não são gravados no INI;
- segredos podem existir apenas no ambiente/processo ou em mecanismo seguro equivalente;
- ao reabrir o console, overrides não secretos persistidos voltam a ser aplicados pelo fluxo normal de configuração.

## Métricas derivadas RASAi

### Crawlability Coverage

Relação: **5/5**.

Fórmula atual:

```text
URLs com BR-GEO-005 = PASS
---------------------------------- x 100
URLs com recuperabilidade determinável
```

A métrica mede recuperabilidade técnica do universo auditado. `UNKNOWN` e estados não determináveis não são transformados em falha por conveniência.

### Indexability Coverage

Relação: **5/5**.

É uma consolidação conservadora por URL. Para a URL ser considerada positiva, os checks determinísticos de acesso/análise da página e os checks de diretivas/soft-404 dos snapshots observados precisam ser determináveis e aprovados.

Contrato atual usa:

- `BR-GEO-005`;
- `BR-GEO-006`;
- `BR-GEO-009`;
- `BR-GEO-011`;
- `BR-GEO-012`;
- `BR-GEO-016`.

O resultado é **RASAi-derived**. Não é “Google Indexability Score”.

### Sitemap Coverage of Audited URLs

Relação: **5/5**.

Fórmula:

```text
URLs auditadas cuja proveniência inclui SITEMAP
----------------------------------------------- x 100
URLs do universo efetivamente auditado
```

Limite metodológico: não afirma cobertura integral de todas as URLs que existem no site. Mede apenas o universo incluído na auditoria.

### Canonical Declaration Coverage

Percentual de snapshots que possuem canonical explícito.

Ausência de canonical e canonical inválido são conceitos diferentes. Por isso esta métrica é separada de `Canonical Consistency Rate`.

### Canonical Consistency Rate

Relação: **5/5**.

Usa `BR-GEO-013` como fonte determinística e calcula PASS sobre snapshots com canonical declarado. Não reimplementa a interpretação de canonical em um segundo motor.

### Structured Data

Métricas atuais:

- `Structured Data Coverage`;
- `Structured Data Validity Rate`, baseada em `BR-GEO-034`;
- `Structured Data to Visible Content Consistency`, baseada em `BR-GEO-036`;
- `Structured Entity Consistency`, baseada em `BR-GEO-037`.

Estas consolidações são derivadas do rule engine já persistido. Não substituem Rich Results Test e não afirmam elegibilidade para um rich result específico quando essa condição não foi medida.

### HTTP Success e Error Rate

Métricas atuais:

- `HTTP 2xx Success Rate`;
- `HTTP 5xx Rate`.

Fonte: status HTTP dos `DEVICE_SNAPSHOT` persistidos.

### TTFB p50, p75, p95 e p99

Fonte: `OPEN-WEB-METRICS-001`, `Navigation Timing` no mesmo browser snapshot.

São percentis do universo observado nesta auditoria, não dados RUM e não equivalem ao percentil CrUX.

## Métricas de Information Retrieval

Relação: **5/5**.

O RASAi calcula localmente as fórmulas. Não é necessário contratar um serviço externo para a matemática.

### Domain MRR

Quando Search Intelligence possui várias observações de query para um domínio de interesse:

```text
RR(query) = 1 / primeira posição do domínio
RR(query) = 0 quando o domínio não foi observado
MRR = média dos RR
```

Isso mede quão cedo o domínio aparece no conjunto de queries observadas.

### Domain SERP Visibility Rate

```text
queries onde o domínio apareceu
------------------------------- x 100
queries com observação persistida
```

### Precision@10, nDCG@10 e Judged-result MRR

Só são calculados quando existem **relevance judgments** explícitos e persistidos em metadata do resultado (`relevance_grade` ou `relevant`).

O RASAi não presume que posição alta significa relevância e não pede a uma IA para fabricar qrels silenciosamente.

`Recall@k` exige conhecer ou estimar de forma contratada o conjunto total de documentos relevantes. Enquanto esse denominador não existir de forma reproduzível, o RASAi não publica Recall apenas para preencher uma tabela.

## W3C Nu HTML Checker

### Para que serve

Valida conformidade de documentos HTML e retorna mensagens estruturadas. O RASAi usa a interface moderna do W3C HTML Checker, não a API SOAP histórica.

Referências oficiais:

- API e orientação para usar `/nu/`: https://validator.w3.org/docs/api
- serviço moderno: https://validator.w3.org/nu/

### Comportamento RASAi

- default: ligado;
- credencial: não necessária;
- escopo: `URL`;
- limite default: 10 URLs por auditoria por meio de `RASAI_STANDARDS_MAX_URLS`;
- timeout default: 20 segundos;
- saída: PASS, FAIL, INDETERMINATE ou ERROR, além de contagem de erros/warnings;
- não existe “W3C Score” inventado pelo RASAi.

O serviço público deve ser usado de forma bounded e razoável. Para SaaS com volume significativo, recomenda-se self-host do Nu Checker ou outra implantação controlada compatível.

Para desligar:

```text
RASAI_W3C_VALIDATOR=false
```

## MDN HTTP Observatory

### Para que serve

Avalia postura de segurança HTTP, principalmente políticas e headers de resposta, e retorna grade/score calculados pela própria fonte.

Referências oficiais:

- FAQ e API v2: https://developer.mozilla.org/en-US/observatory/docs/faq
- endpoint: `https://observatory-api.mdn.mozilla.net/api/v2/scan`

### Comportamento RASAi

- default: ligado;
- credencial: não necessária;
- escopo: `ORIGIN`;
- uma origem não é repetida por URL/device;
- o RASAi preserva `grade`, `score`, testes e `algorithm_version` quando retornados;
- o score continua identificado como score da fonte MDN Observatory;
- não altera SARI.

Importante: o uso do endpoint público inicia/consulta um scan externo do host. Isso é um efeito de privacidade e operação diferente de uma análise puramente local.

Para desligar:

```text
RASAI_MDN_OBSERVATORY=false
```

Para SaaS em escala ou ambientes restritos, avaliar a execução local/self-host da ferramenta em vez de depender do serviço público.

## Web Platform Baseline / WebDX

### Para que serve

Baseline fornece status de disponibilidade de recursos da Web entre browsers. O projeto `web-features`, coordenado pelo W3C WebDX Community Group, é fonte de dados para esses status e publica o pacote `web-features`.

Referências:

- projeto WebDX/web-features: https://github.com/web-platform-dx/web-features
- visão do projeto: https://web-platform-dx.github.io/web-features-project/

### Estado atual no RASAi

A capacidade e seu estado já estão modelados, mas o RASAi **não inventa cobertura Baseline** apenas porque o dataset existe. É necessário também mapear features efetivamente usadas pela página para IDs `web-features` de forma reproduzível.

Por isso:

- `RASAI_WEB_PLATFORM_BASELINE=true` é o default;
- sem dataset versionado, estado `NOT_CONFIGURED`;
- com dataset mas sem observação mapeável suficiente, estado `NO_DATA`;
- nenhuma nota de compatibilidade é produzida por aproximação heurística silenciosa.

Dataset:

```text
RASAI_WEB_FEATURES_DATASET=<caminho versionado>
```

## Google PageSpeed Insights / Lighthouse

### Para que serve

Coleta medição de laboratório Lighthouse e recomendações/categorias suportadas pela PageSpeed Insights API.

Referência oficial:

https://developers.google.com/speed/docs/insights/v5/get-started

A documentação oficial permite uso com ou sem API key e recomenda key para consultas frequentes/automatizadas. A política do RASAi é mais restritiva: **automação PageSpeed fica desabilitada até uma API key estar configurada**.

### Criar a chave

1. Acesse Google Cloud Console: https://console.cloud.google.com/
2. Crie ou selecione um projeto.
3. Habilite a API PageSpeed Insights para o projeto.
4. Abra `APIs & Services > Credentials`.
5. Crie uma API key e aplique restrições adequadas ao seu ambiente.
6. Configure somente no ambiente/secret store:

```text
RASAI_PAGESPEED_API_KEY=<segredo>
```

Com a chave presente e sem override, o serviço fica elegível automaticamente.

Desligamento explícito:

```text
RASAI_PAGESPEED_ENABLED=false
```

## Chrome UX Report API

### Para que serve

Fornece dados agregados de experiência real na granularidade disponível para URL/origin, incluindo Core Web Vitals.

Referência oficial:

https://developer.chrome.com/docs/crux/api

A documentação oficial exige Google Cloud API key com `Chrome UX Report API` provisionada.

### Criar a chave

1. Acesse https://console.cloud.google.com/
2. Crie ou selecione um projeto.
3. Habilite `Chrome UX Report API`.
4. Abra `APIs & Services > Credentials`.
5. Crie/restrinja uma API key.
6. Configure:

```text
RASAI_CRUX_API_KEY=<segredo>
```

Desligamento explícito:

```text
RASAI_CRUX_ENABLED=false
```

O PageSpeed pode devolver dados CrUX em sua resposta, mas o Google informa intenção de descontinuar esse acoplamento. Para dados de campo, a integração CrUX dedicada é tratada como fonte explícita e mais estável.

## Google Search Console

### Para que serve

A Search Console API fornece, conforme permissão da propriedade:

- Search Analytics;
- Sitemaps;
- Sites/properties;
- URL Inspection.

Referências oficiais:

- visão da API: https://developers.google.com/webmaster-tools
- referência: https://developers.google.com/webmaster-tools/v1/api_reference_index
- pré-requisitos: https://developers.google.com/webmaster-tools/v1/prereqs
- autorização OAuth 2.0: https://developers.google.com/webmaster-tools/v1/how-tos/authorizing
- URL Inspection: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect

### Credencial

Search Console usa OAuth 2.0 para dados privados da conta. O fluxo recomendado para SaaS é Authorization Code/OIDC-compatible account connection com refresh token protegido em secret store, não um token bearer persistido em `audit.db` ou INI.

O runtime local existente aceita token temporário via:

```text
RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=<segredo>
```

Também é necessário que o usuário autenticado tenha acesso à propriedade Search Console compatível com o target. URL Inspection requer `inspectionUrl`, `siteUrl` e escopo OAuth apropriado (`webmasters.readonly` ou `webmasters`).

Desligamento explícito:

```text
RASAI_GSC_ENABLED=false
```

Limite importante: URL Inspection descreve o estado conhecido no índice do Google. Não deve ser apresentada como teste live de indexabilidade universal.

## Open Web Performance APIs

Referências centrais:

- Performance Timeline: https://www.w3.org/TR/performance-timeline/
- Navigation Timing: https://www.w3.org/TR/navigation-timing-2/
- Resource Timing: https://www.w3.org/TR/resource-timing/
- Event Timing: https://www.w3.org/TR/event-timing/

O collector `OPEN-WEB-METRICS-001` lê estado do browser já aberto. Não cria request adicional ao target e não chama API externa.

Default:

```text
RASAI_OPEN_WEB_METRICS=true
```

Para desligar:

```text
RASAI_OPEN_WEB_METRICS=false
```

## Organização dos relatórios

A página canônica `report/standards.html` concentra:

- catálogo dos serviços;
- estado por integração;
- toggle correspondente;
- escopo da evidência;
- relação com o RASAi;
- métricas materializadas e sua fonte.

A mesma informação é projetada sem duplicação semântica nas superfícies onde faz sentido:

- `index.html`: resumo executivo das métricas mais relacionadas ao RASAi;
- `crawling-discovery.html`: crawlability, indexability, sitemap, canonical e structured data;
- `search-intelligence.html`: MRR, visibilidade e métricas de IR quando há judgments;
- `web-performance.html`: Open Web Metrics, PageSpeed/Lighthouse e CrUX;
- `context.html`: topologia de ORIGIN, URL, DEVICE_SNAPSHOT e PROFILE_MEASUREMENT.

Quando houver múltiplas URLs, o relatório deve identificar se o valor é por URL, por snapshot, por origem ou uma consolidação do universo auditado. Média implícita entre páginas não é permitida.

## Impacto e paridade SaaS

### Payload de AuditJob

O SaaS transporta somente escolhas não secretas. Foram adicionadas opções estruturadas para:

- `open_web_metrics`;
- `derived_readiness_metrics`;
- `retrieval_metrics`;
- `w3c_validator`;
- `mdn_observatory`;
- `web_platform_baseline`;
- `pagespeed_enabled`;
- `crux_enabled`;
- `gsc_enabled`;
- `standards_max_urls`;
- `standards_timeout_seconds`.

Omissão e customização são preservadas no payload durável.

Para serviços com credencial:

- campo omitido: o worker pode aplicar default dirigido pela credencial disponível no ambiente dele;
- `false`: desliga explicitamente;
- `true`: solicita execução, mas a ausência de credencial mantém o serviço não configurado.

### Secret store

O payload nunca leva API key/token. Workers recebem segredos por deployment secret store/variáveis protegidas. Isso mantém o control plane independente do segredo bruto e evita replicação para `AUD-*/audit.db`.

### API do SaaS

O SaaS Pilot expõe:

```text
GET /api/v1/audit-job-options
GET /api/v1/standards/services
```

O segundo endpoint retorna metadados, docs, nomes das variáveis e estado de capability do processo API, mas **nunca valores de credencial**. Em topologias onde API e worker têm secret stores diferentes, esse estado é apenas hint do processo API; a aptidão efetiva final é resolvida pelo worker.

### Custo operacional mesmo sem fee de provider

“Sem custo de provider” não significa “sem impacto de infraestrutura”. Defaults externos adicionam:

- egress;
- latência de auditoria;
- dependência de disponibilidade pública;
- possibilidade de rate limit;
- uso de CPU/armazenamento para persistir resultados;
- no MDN Observatory, exposição do hostname ao serviço público de scan.

Para SaaS em escala, priorizar self-host/cache/datasets versionados antes de aumentar frequência ou universo de URLs.

## O que permanece fora do default automático

### Browsertime / sitespeed.io

É tecnicamente aderente para synthetic journeys e múltiplos browsers, mas adiciona runtime/dependências próprias e pode duplicar parte da coleta Playwright atual. Deve entrar como `SyntheticMeasurementProvider`, não como chamada silenciosa no core.

Referência: https://www.sitespeed.io/documentation/browsertime/

### WebPageTest

Permanece provider opcional futuro. Há forte sobreposição com Lighthouse/Browsertime e dependência de serviço externo.

### SSL Labs

Permanece provider opcional futuro. Antes de uso SaaS deve haver validação explícita de termos de uso, limites e política comercial da API.

### axe-core direto

O RASAi já recebe uma camada automatizada de acessibilidade via Lighthouse. Executar axe separadamente só deve entrar se houver ganho comprovado de cobertura/proveniência sem dupla contagem do mesmo finding.

## Proveniência

Sempre que uma nova fonte for incorporada, o contrato deve preservar no mínimo:

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

Nem todos os campos precisam existir como colunas físicas independentes; podem ser materializados em metadata estruturada, desde que sejam reabríveis e auditáveis.
