# SERP Observation - fundação de Search Intelligence

**Estado:** fundação provider-neutral implementada / POC operacional.

SERP Observation é a camada factual de evidência de Search tradicional usada por RASAi Competitive Search & Content Intelligence. Semânticas de request/response específicas de fornecedores permanecem isoladas em adapters concretos; o código downstream consome objetos canônicos `SerpObservation` e `SerpResult`.

Contratos relacionados:

- análise competitiva determinística: `COMPETITIVE_SEARCH_INTELLIGENCE.md`;
- recomendações semânticas opcionais vinculadas a evidências: `COMPETITIVE_AI_INTELLIGENCE.md`;
- comparação temporal determinística: `SEARCH_INTELLIGENCE_HISTORY.md`;
- monitoramento longitudinal recorrente: `SEARCH_INTELLIGENCE_MONITORING.md`;
- Web/API e execução desacoplada: `WEB_API_FOUNDATION.md`.

## 1. Escopo

SERP significa **Search Engine Results Page**. Observação de Search tradicional e observação de respostas de IA são conceitos separados:

- **Search Observation:** Google, Bing e outros mecanismos de busca tradicionais;
- **AI Observation:** ChatGPT, Gemini, Claude, Perplexity, Copilot e mecanismos de resposta semelhantes.

A camada SERP nunca executa IA e nunca infere causalidade de ranking. Ela registra fatos limitados, como a ordem dos resultados, a posição observada de um domínio do cliente configurado e quais resultados observados aparecem antes dele.

O request canônico contém `engine`; portanto, os contratos downstream não ficam vinculados ao Google.

## 2. Arquitetura

```text
CMD / Web API / worker
        |
        v
serviço de aplicação Search Intelligence
        |
        v
contrato SerpProvider
        |
        +-- FixtureSerpProvider
        +-- SerpApiProvider      -> Google live
        +-- SerpApiBingProvider  -> Bing live
        +-- adapters futuros
        |
        v
SerpObservation / SerpResult canônicos
        |
        +-- posição do cliente / resultados à frente
        +-- persistência pontual em auditoria, quando solicitada
        +-- sink operacional de evidência para monitoramento recorrente
        |
        +--> Competitive Search Intelligence
        +--> Competitive AI (opt-in explícito)
        +--> SEARCH-HISTORY-001
        +--> SEARCH-MONITOR-001
```

`SearchIntelligenceService` depende apenas de `SerpProvider`. A construção do provider permanece na camada de runtime/composição.

A API HTTP não executa coleta Search dentro do processo da requisição. Execução no estilo hospedado é representada por jobs duráveis `SEARCH_MONITOR` consumidos por workers.

## 3. Modos

### `disabled`

Default. Nenhum provider de Search é construído e nenhuma requisição externa de Search é feita.

### `fixture`

Lê JSON de fixture canônico, realiza zero chamadas de rede e emite `Data mode: FIXTURE`. Destina-se a testes, CI, desenvolvimento e demonstrações.

### `live`

Constrói o adapter live configurado.

IDs de adapters live atuais:

| ID do adapter | Mecanismo | Fornecedor | Paginação |
|---|---|---|---|
| `serpapi` | Google | SerpApi | `start` do Google, páginas limitadas a 10 posições |
| `serpapi-bing` | Bing | SerpApi | cursor `first` informado pelo provider para Bing |

Os dois adapters usam a mesma variável BYOK `RASAI_SERPAPI_API_KEY`. IDs distintos tornam explícitas as regras específicas de request, paginação e normalização de cada mecanismo.

## 4. Adapter Google

`serpapi` suporta `engine=google` com contexto desktop/mobile.

A paginação Google usa `start` em incrementos de 10 posições. Para profundidade solicitada acima de 10, o RASAi solicita páginas adicionais respeitando o orçamento de requests configurado e a disponibilidade de paginação do provider.

O adapter rejeita mecanismos não suportados antes do acesso à rede.

## 5. Adapter Bing

`serpapi-bing` suporta `engine=bing` com contexto desktop/mobile.

Search no Bing via SerpApi **não** usa o mesmo contrato fixo de paginação do Google. Por isso, o adapter:

- monta `mkt` a partir de idioma + país configurados;
- encaminha região opcional por `location`;
- usa `serpapi_pagination.next` / `next_link` informado pelo provider;
- extrai somente o cursor `first` dessa URL do provider;
- reconstrói localmente o próximo request, em vez de seguir URL arbitrária devolvida pelo provider;
- converte posições locais da página Bing em posições absolutas observadas;
- encerra quando a profundidade solicitada foi coberta, a paginação termina ou o orçamento rígido de requests impede nova coleta.

O cursor deve ser positivo e avançar estritamente. Cursores inválidos ou repetidos são tratados como resposta malformada do provider.

## 6. Completude da profundidade solicitada

`NOT_FOUND_WITHIN_DEPTH` só é válido quando o RASAi possui evidência suficiente para tratar a janela Search solicitada como completa.

Em paginação variável dirigida pelo provider, uma execução pode terminar porque o orçamento configurado foi esgotado antes de a profundidade solicitada ser totalmente observada. Nesse estado:

```text
requested_depth_complete = false
```

Se o domínio do cliente **não** foi observado, o RASAi retorna:

```text
DomainMatchStatus.UNAVAILABLE
SERP_REQUESTED_DEPTH_INCOMPLETE
```

Ele **não** retorna `NOT_FOUND_WITHIN_DEPTH`, pois isso declararia mais evidência Search do que foi efetivamente coletado.

Se o domínio do cliente já tiver sido observado em uma coleta parcial, a posição observada continua sendo um fato válido e ainda pode ser retornada como `FOUND`.

Metadados de qualidade do Bing incluem, quando aplicável:

- `pagination_strategy=serpapi_next_first`;
- `observed_position_ceiling`;
- `requested_depth_complete`;
- `request_budget_ended_before_requested_depth`;
- `pagination_ended_before_requested_depth`;
- request IDs do provider e timestamps da janela de coleta.

## 7. Contratos canônicos de request e observação

### `SerpQueryRequest`

Transporta:

- query;
- engine;
- país/mercado;
- região opcional;
- idioma;
- dispositivo;
- profundidade solicitada;
- timestamp solicitado;
- domínio de interesse;
- run ID;
- origem da query;
- metadados independentes do provider.

`query_origin` suporta `MANUAL`, `SEARCH_CONSOLE`, `BING_WEBMASTER`, `PAGE_CONTENT`, `AI_HYPOTHESIS`, `SERP_RELATED`, `COMPETITOR_DISCOVERY` e `EXTERNAL`.

### `SerpObservation`

Transporta:

- ID da observação;
- proveniência de execução/query;
- engine/mercado/idioma/dispositivo;
- timestamp de coleta;
- provider e request IDs do provider;
- profundidade solicitada;
- resultados normalizados;
- modo de dados e status da observação;
- referência da evidência bruta + SHA-256, quando persistida;
- metadados de configuração/qualidade.

### `SerpResult`

Transporta:

- posição absoluta observada;
- domínio normalizado;
- URL;
- título;
- snippet;
- tipo do resultado;
- features SERP normalizadas;
- metadados independentes do provider.

JSON específico do fornecedor não entra nos objetos canônicos downstream.

## 8. Semântica de domínio

A correspondência de domínio normaliza caixa, hostnames IDN e `www.` usado apenas para apresentação. Um domínio raiz configurado corresponde aos seus subdomínios; configurar um subdomínio não implica o domínio pai.

Status atuais do domínio:

- `FOUND`;
- `NOT_FOUND_WITHIN_DEPTH`;
- `NOT_REQUESTED`;
- `UNAVAILABLE`;
- `ERROR`;
- `DISABLED`.

`NOT_FOUND_WITHIN_DEPTH` significa somente que o domínio estava ausente de uma janela Search que o RASAi considera totalmente observada dentro da profundidade solicitada. Não significa que o domínio nunca ranqueia.

## 9. Proveniência e persistência

Modos de dados canônicos incluem:

- `OBSERVED_API`;
- `OBSERVED_SYNTHETIC`;
- `IMPORTED`;
- `FIXTURE`;
- `MODELED`;
- `AI_INFERRED`.

Adapters SERP live atuais emitem `OBSERVED_API`; fixtures emitem `FIXTURE`.

A evidência bruta do provider possui dois caminhos de persistência:

- Search Intelligence pontual pode persistir dentro de um workspace `AUD-*` existente;
- Search Monitoring recorrente usa uma raiz dedicada `.rasai/search-monitoring/`, sem modificar arquivos `AUD-*/audit.db`.

Campos com aparência de segredo são redigidos antes da persistência da evidência.

Tabelas aditivas pontuais:

- `serp_observations`;
- `serp_results`;
- `serp_competitive_analyses`;
- `serp_competitive_results`;
- `serp_competitive_pages`;
- `serp_competitive_ai_analyses`, quando Competitive AI é usada.

Tabelas recorrentes do control plane:

- `search_monitor_queries`;
- `search_monitor_runs`.

Nenhuma tabela de Search Intelligence altera `SARI-001`, `SCORE-GEO-004` ou tabelas de scoring.

## 10. Salvaguardas e controle de custo

| Variável | Default efetivo | Valores permitidos | Recomendado | Finalidade |
|---|---|---|---|---|
| `RASAI_SERP_MODE` | `disabled` | `disabled`, `live`, `fixture` | `disabled` por padrão; `fixture` em testes; `live` somente com intenção explícita de consumo | opt-in global de SERP |
| `RASAI_SERP_PROVIDER` | `serpapi` | `serpapi`, `serpapi-bing` | `serpapi`, salvo uso explícito de Bing | ID do adapter live |
| `RASAI_SERPAPI_API_KEY` | sem default | chave SerpApi válida | secret/env | credencial BYOK |
| `RASAI_SERP_FIXTURE_PATH` | sem default | caminho de arquivo existente | definir apenas em `fixture` | fixture canônica |
| `RASAI_SERP_MAX_QUERIES` | `10` | inteiro `> 0` | `10` ou menor em smoke/custo controlado | teto de queries |
| `RASAI_SERP_MAX_REQUESTS` | `10` | inteiro `> 0` | `10` | orçamento global de tentativas HTTP ao provider |
| `RASAI_SERP_MAX_DEPTH` | `20` | inteiro `> 0` | `20` | teto de profundidade solicitada |
| `RASAI_SERP_MAX_COMPETITORS` | `10` | inteiro `>= 0` | `10` | teto de candidatos derivados |
| `RASAI_SERP_TIMEOUT_SECONDS` | `20` | número `> 0` | `20` | timeout por tentativa do provider |
| `RASAI_SERP_RETRIES` | `1` | inteiro `>= 0` | `1` | retries limitados |
| `RASAI_SERP_MIN_INTERVAL_SECONDS` | `1` | número `>= 0` | `1` ou maior conforme política/carga | intervalo mínimo entre inícios de requests |

Para o adapter Google, o teto determinístico de preflight é:

```text
ceil(depth / 10) * (retries + 1)
```

Para `serpapi-bing`, a quantidade de linhas orgânicas por página varia conforme o provider; por isso, `--dry-run` reporta o `RASAI_SERP_MAX_REQUESTS` global configurado como teto conservador de requests ao provider de Search. As tentativas reais continuam rigidamente limitadas pelo `RequestBudget` compartilhado.

O RASAi não inventa preço de provider. O custo real segue o plano e a quota do cliente junto ao fornecedor.

## 11. Limites de segurança

- BYOK; nenhuma chave de provider de Search é hardcoded;
- a chave do provider nunca é impressa;
- payloads externos são não confiáveis e passam por normalização;
- URLs, esquemas e credenciais inválidas nos resultados são rejeitados;
- a paginação Bing nunca segue URL arbitrária devolvida pelo provider; apenas o cursor numérico validado é reutilizado;
- evidência bruta do provider é sanitizada de segredos antes da persistência;
- CI usa fixtures/mocks e não deve consumir quota live de Search.

Aquisição opcional de páginas concorrentes possui limite separado para SSRF/web pública, documentado em `COMPETITIVE_SEARCH_INTELLIGENCE.md`.

Competitive AI opcional recebe evidência estruturada, não credenciais brutas do provider nem HTML bruto.

Em execução hospedada multi-tenant, validação de URL na aplicação não substitui controles de egress na camada de rede.

## 12. Exemplos de CLI

Google:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine google `
  --country BR `
  --language pt-BR `
  --device mobile `
  --depth 20
```

Bing:

```powershell
$env:RASAI_SERP_MODE="live"
$env:RASAI_SERP_PROVIDER="serpapi-bing"
$env:RASAI_SERPAPI_API_KEY="<BYOK>"
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine bing `
  --country BR `
  --language pt-BR `
  --region "Porto Alegre, RS, Brazil" `
  --device desktop `
  --depth 20
```

`dry-run`:

```powershell
rasai search "seguro residencial" `
  --domain loja.exemplo.com.br `
  --engine bing `
  --provider serpapi-bing `
  --mode live `
  --depth 20 `
  --dry-run
```

Fixture, Competitive Search, comparação de conteúdo e Competitive AI usam os contratos downstream independentes de provider.

Observação recorrente é exposta por `rasai search-monitor` e armazena adapter/engine selecionados no contexto registrado da query, de modo que mudanças incompatíveis de provider nunca sejam comparadas silenciosamente.

## 13. Search Console e Bing Webmaster são fontes de evidência diferentes

Search Console e Bing Webmaster representam dados agregados first-party de desempenho/observabilidade. SERP Observation representa uma observação controlada e pontual de uma query Search.

Não se espera que a posição média de Search Console/Bing Webmaster seja igual a uma única observação SERP controlada.

Essas superfícies de ingestão permanecem separadas do contrato de adapter SERP live.

## 14. Relatórios e histórico

Relatório pontual da auditoria:

```text
AUD-*/report/search-intelligence.html
```

Histórico determinístico do par:

```text
search-history/SH-*/report.html
search-history/SH-*/manifest.json
```

Relatório longitudinal recorrente:

```text
platform-report/search-intelligence.html
```

Todos são projeções de evidência persistida. A renderização não chama providers de Search ou IA.

## 15. Limitações atuais

- adapters live de Search tradicional usam atualmente um único fornecedor, SerpApi, para Google e Bing;
- linhas normalizadas de Search permanecem focadas em resultados orgânicos;
- não há integração com endpoint de billing/quota do provider;
- a classificação de resultados competitivos é heurística, não um grafo comercial de entidades;
- comparação de conteúdo concorrente usa HTML estático por HTTP, não DOM renderizado por browser;
- ainda não há contrato competitivo canônico para canonical/`hreflang`/link graph;
- suporte live de Competitive AI começa atualmente por OpenAI;
- comparação longitudinal semântica da saída de Competitive AI ainda não é contrato estável;
- monitoramento recorrente detecta mudanças, mas ainda não expõe uma superfície completa de notificações externas;
- não há probes Search regionais distribuídos;
- execução portátil de agendamento recorrente permanece em uma única máquina; execução horizontal hospedada depende do modelo de worker/fila durável.

## 16. Próxima evolução

Observação periódica de queries já está implementada em `SEARCH-MONITOR-001`. As próximas extensões de Search Intelligence devem se concentrar em:

1. adicionar um segundo fornecedor/provider de dados Search independente por trás de `SerpProvider`, reduzindo concentração de fornecedor;
2. ampliar a cobertura de SERP features normalizadas quando a evidência do provider sustentar isso;
3. adicionar aquisição competitiva por DOM renderizado para páginas client-rendered, preservando a aquisição estática limitada;
4. adicionar comparações determinísticas de canonical, `hreflang` e link graph limitado;
5. expor eventos materiais de mudança do Search Monitor para destinos de notificação controlados;
6. adicionar observação distribuída/regional somente quando a demanda SaaS justificar o custo operacional;
7. definir comparação longitudinal semântica somente após existir metodologia reproduzível e vinculada a evidências.

Volatilidade de Search permanece observacional. Nem movimento de ranking, nem momento de alerta, nem proximidade temporal com deploy podem ser apresentados como prova de causalidade de ranking.
