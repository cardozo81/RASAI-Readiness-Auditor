# Perplexity Search Intelligence

**Estado:** implementação da issue #5  
**Data de revalidação oficial:** 04/10/2026  
**Surface implementada:** Perplexity Search API  
**Boundary RASAi:** pesquisa externa / Search Intelligence, não provider evidence-bound canônico

## Objetivo

A integração Perplexity amplia o RASAi com pesquisa web externa rastreável sem alterar a auditoria determinística.

~~~text
RASAi Search Intelligence
        ↓
Perplexity Search API
        ↓
fontes/resultados externos
        ↓
provenance explícita
        ↓
persistência + native usage/pricing
~~~

Esta superfície **não**:

- substitui SERP observada;
- entra no provider_registry canônico de IA;
- participa do AI=auto;
- altera crawling;
- altera SARI;
- altera CATs;
- altera SCORE-GEO;
- altera Apdex;
- cria finding determinístico;
- promove fonte Perplexity para evidence canônica.

A regra geral do RASAi continua sendo: qualquer provider que for integrado ao **registry canônico de IA** deve entrar no AI=auto no mesmo merge quando configurado e apto. Perplexity Search API fica fora dessa regra apenas porque nesta entrega ela não é um provider desse registry; é uma integração domain-specific de Search Intelligence.

## API escolhida

A primeira integração usa exclusivamente:

~~~text
POST https://api.perplexity.ai/search
~~~

Autenticação:

~~~text
Authorization: Bearer $PERPLEXITY_API_KEY
Content-Type: application/json
~~~

Variável canônica:

~~~text
PERPLEXITY_API_KEY
~~~

A Agent API não faz parte desta entrega e não deve ser documentada como implementada.

Fontes oficiais revalidadas em 04/10/2026:

- Search API: https://docs.perplexity.ai/docs/search/quickstart
- Fast Search: https://docs.perplexity.ai/docs/search/fast-search
- pricing: https://docs.perplexity.ai/docs/getting-started/pricing
- rate limits: https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers
- API keys: https://docs.perplexity.ai/docs/admin/api-key-management

## Request

A integração suporta:

- uma query;
- até cinco queries relacionadas no mesmo request;
- search_type=web;
- search_type=fast;
- max_results;
- country ISO 3166-1 alpha-2;
- search_language_filter com códigos ISO 639-1.

A query ou lista de queries faz parte da provenance da execução.

O secret não entra no payload persistido, hash de payload, relatório, banco, logs ou console.

## Response e provenance

A resposta esperada contém um id e results[].

Para cada resultado o RASAi preserva, quando retornado:

- posição na resposta;
- URL;
- título;
- snippet;
- date;
- last_updated;
- metadata adicional;
- vínculo com o run_id;
- vínculo com o audit_id.

As URLs das fontes são também materializadas como conjunto de citações da execução.

Persistência dedicada:

~~~text
perplexity_search_runs
perplexity_search_sources
~~~

Essas tabelas são separadas de:

~~~text
serp_observations
serp_results
serp_evidence_provenance
~~~

Portanto uma fonte Perplexity não pode ser confundida com uma SERP observada.

## Native usage e pricing

A integração consome diretamente o contrato entregue pela issue #8:

~~~text
provider = PERPLEXITY
surface = SEARCH_API
unit = PERPLEXITY_SEARCH_REQUEST
pricing_model = PER_REQUEST
~~~

Não são criados campos token-based fictícios.

Para a Search API:

~~~text
WEB  = USD 5 / 1000 requests = USD 0.005 / request
FAST = USD 1 / 1000 requests = USD 0.001 / request
~~~

A documentação oficial vigente distingue **billing** de **rate limit**:

- uma resposta bem-sucedida de POST /search = uma unidade faturável;
- um request com até cinco queries continua sendo **uma** unidade faturável;
- rate limit conta uma query unit por query;
- request inválido, rate-limited ou upstream failure não é faturado;
- resposta bem-sucedida sem resultados continua faturável;
- não há cobrança token-based adicional na Search API.

Consequências no RASAi:

- multi-query não multiplica PERPLEXITY_SEARCH_REQUEST;
- HTTP não faturável conhecido recebe billable=false;
- timeout/network sem certeza de faturabilidade preserva billable=NULL;
- ausência de pricing reproduzível permanece UNPRICED;
- ausência de preço nunca vira zero;
- tokens permanecem NULL;
- custo não é recalculado retroativamente com catálogo corrente.

## Telemetria e ledger

A chamada reutiliza:

~~~text
ai_provider_attempts
ai_provider_native_usage
usage_events
pricing snapshots
~~~

O ai_provider_attempts é usado apenas como envelope genérico de tentativa/telemetria. O contrato da tentativa é:

~~~text
semantic_contract_version = RASAI-PERPLEXITY-SEARCH-1
operation = SEARCH_INTELLIGENCE
surface = SEARCH_API
~~~

O conteúdo externo e suas fontes permanecem nas tabelas de provenance Perplexity.

A ingestão SaaS já existente trata a tentativa como contagem de call e a unidade nativa como consumo monetário separado, evitando dupla contagem de custo.

## Erros

A integração contém os erros no boundary externo.

| Condição | Classificação |
|---|---|
| HTTP 401 | AUTH_ERROR |
| HTTP 403 | PERMISSION_ERROR |
| HTTP 429 | RATE_LIMIT_ERROR |
| HTTP 5xx | SERVER_ERROR |
| timeout | TIMEOUT_ERROR |
| falha de rede | NETWORK_ERROR |
| JSON/schema inválido em resposta 2xx | INVALID_RESPONSE |
| credencial ausente | NOT_CONFIGURED |

Erro Perplexity não vira finding do site auditado.

Falha externa não invalida a auditoria determinística e é apresentada como limitação da integração.

## Secrets

PERPLEXITY_API_KEY:

- é lida de environment/secret store;
- não é persistida em rasai-console.ini;
- não é gravada em TOML;
- não é passada por command line;
- não aparece em URL;
- não é persistida em audit.db;
- não é incluída em snapshots;
- não aparece em relatório;
- não entra em scheduler arguments.

O console apresenta apenas estado configurada / não configurada.

## Console

A Perplexity permanece separada da seleção principal de IA e é operada por três superfícies que compartilham a mesma configuração canônica:

~~~text
INÍCIO > PREPARAR AUDITORIA > CAT-05 · Search & AI Intelligence
INÍCIO > 5. Integrações e serviços > Perplexity Search Intelligence
INÍCIO > 6. Todas as configurações > Perplexity Search Intelligence / Credencial
~~~

No CAT-05, a ação **P. Perplexity externa** abre o pedido da próxima execução. O usuário pode:

- não solicitar ou limpar a solicitação;
- informar de uma a cinco queries;
- escolher `WEB` ou `FAST`;
- visualizar readiness e estado da credencial;
- abrir o editor canônico de `PERPLEXITY_API_KEY`.

Queries e `WEB/FAST` são inputs da próxima execução. Eles não são convertidos em variáveis de ambiente e não são gravados como secrets/configuração reutilizável no `rasai-console.ini`.

`PERPLEXITY_API_KEY` é a única variável de ambiente consumida pelo runtime Perplexity atual. O editor é o mesmo usado pelo catálogo global: entrada mascarada, sessão e persistência/remoção explícita em Windows/User; o valor nunca entra no INI.

Em **Integrações e serviços**, o diagnóstico Perplexity é `CONFIGURATION_ONLY`: confirma apenas a presença/configuração local e **não executa `POST /search`**. Isso evita consumir request comercial/quota apenas para testar a integração. A validade funcional final da credencial é observada somente quando uma pesquisa Perplexity é realmente solicitada.

A opção Perplexity é opt-in e independente dos termos SERP e do Google Search Console.

A execução ocorre após o core determinístico da auditoria.

## Relatórios

O contrato RASAI-PERPLEXITY-SEARCH-1 é rotulado como:

~~~text
Pesquisa externa Perplexity
CAT-05 · Pesquisa externa / Search Intelligence
~~~

A finalidade apresentada ao usuário deixa explícito que:

- as fontes são externas;
- a execução é advisory;
- não substitui SERP;
- não altera scoring;
- não constitui evidence determinística.

## AUTO

Perplexity Search API não está no provider_registry.

Logo ela não participa de:

~~~text
AI=auto
RASAI_AI_AUTO_EXCLUDE
fallback do provider registry
ranking econômico do AUTO
~~~

Isso não cria exceção à regra geral de AUTO para providers canônicos.

Se uma futura integração Perplexity entrar no registry canônico de IA, ela deverá ser AUTO-eligible no mesmo merge quando configurada/apta, salvo nova decisão arquitetural explícita e documentada.

## Homologação com ressalvas externas

Crédito, quota, saldo, rate limit, plano ou indisponibilidade comercial isolados não invalidam a implementação quando estiver comprovado que:

1. request/auth/surface estão corretos;
2. erro externo é classificado;
3. erro fica contido;
4. persistência permanece íntegra;
5. secrets não vazam;
6. native usage/pricing são coerentes;
7. testes isolados estão verdes;
8. CI relevante está verde;
9. core determinístico permanece invariável.

Qualquer defeito funcional posterior em main deve virar bug específico.


## Evolução GEO (#301, implementação em andamento)

A configuração opcional `RASAI_PERPLEXITY_ENABLED` controla **ativação**, separadamente de `PERPLEXITY_API_KEY`. A ausência da flag é compatível com o comportamento previamente homologado (queries explícitas + credencial); `false`, `0`, `off` ou `no` impedem requisição externa sem apagar a credencial. O inventário de variáveis utiliza `EnvironmentSpec`, e somente configurações não secretas são elegíveis ao INI; restauração segue o registry e a precedência padrão do produto.

A nova superfície transversal `geo.html` é advisory e parte do `report-catalog` da AUD individual. Lê apenas evidências persistidas; não substitui CAT-05, não altera índice e não comprova answer inclusion ou citation inclusion em respostas generativas. Comparações de URLs entre SERP e Perplexity somente têm semântica direta quando a Search API recebeu **uma única consulta** e existe observação SERP live válida equivalente. Requests multi-query não oferecem, no contrato atual, vínculo individual fonte→query: apresentar indisponibilidade da comparação em vez de inventar pareamento.

Apenas evidências rastreáveis podem fundamentar recomendações; snippets de concorrentes não comprovam conteúdo integral. A interpretação deve separar explicitamente observação, hipótese e ação de boas práticas. Evolução longitudinal para CONS-* fica no gap #311 e fora da presente implementação.

**Estado:** documento descreve projeto incremental; a implementação não deve ser considerada homologada até CI, testes de persistência/RPR, integridade e fechamento das issues-filhas #302-#310.


### Snapshot GEO derivado e reuso

A camada adicional `geo_observation_runs` mantém uma projeção `RASAI-GEO-OBSERVATION-1` vinculada a `audit_id`, `perplexity_run_id`, observação SERP comparável (quando disponível), fingerprint SHA-256 da entrada, contrato e timestamp de materialização. O ID é determinístico e a gravação é idempotente: nova evidência produz novo snapshot; a mesma evidência não é duplicada. Essa projeção não participa de scoring nem muda tabelas de origem.

Depois de uma pesquisa Perplexity explicitamente executada pelo console e persistida com sucesso, o adapter GEO cria o snapshot e utiliza a materialização canônica do relatório existente para refletir os dados. Falhas nessa projeção opcional permanecem advisory. RPR e complementos continuam sujeitos às regras existentes de snapshot e aquisição: rematerialização HTML lê o estado persistido e não chama a API. Se não existir snapshot compatível, a seção deve apresentar indisponibilidade em vez de refazer a observação ou reinterpretar o histórico.

A comparação é estritamente observacional: mesmo quando a consulta coincide, SERP e Perplexity podem diferir em momento, mercado, provider, profundidade e normalização. URLs recuperadas não são citações em respostas. As hipóteses de negócio/semântica são ações para avaliação humana, não causalidade comprovada.


### Interpretação GEO por IA canônica (#306)

O menu da Perplexity no CAT-05 oferece a opção explícita **"Síntese GEO por IA canônica nesta AUD"**, desabilitada por padrão e separada da pesquisa externa. A pesquisa Perplexity somente solicita requisições quando o operador informou consultas, ativação e credencial aplicáveis. A síntese por IA somente considera fontes persistidas e uma consulta única com provenance rastreável. A análise não lê automaticamente o conteúdo integral dos concorrentes.

O consumidor `rasai.geo_ai` reutiliza o contrato `CompetitiveAiInput`/`CompetitiveAiEvidence` e o builder já instalado da orquestração competitiva canônica. Não existe cliente HTTP privado, fallback de provider ou motor próprio de preços/retries. Caso a orquestração canônica não esteja instalada, configurada ou elegível, a síntese é indicada como indisponível; a AUD e CAT-05 não são rebaixados.

As interpretações bem-sucedidas e tentativas derivadas são persistidas em `geo_ai_interpretations`, vinculadas a `audit_id` e `perplexity_run_id`, com hash de entrada, provider, modelo, versões de prompt, status e oportunidades com IDs de evidência. Antes de nova tentativa, o consumidor verifica o mesmo fingerprint e seleção: uma análise já persistida é reutilizada sem nova chamada faturável. RPR, complemento e geração HTML não executam esse consumidor, apenas projetam os dados persistidos. O report `geo.html` diferencia a interpretação GEO específica de sínteses competitivas pré-existentes em SERP.

A exposição a texto de fonte externa é limitada a metadados e snippets, tratados como evidência observacional não confiável. A saída não modifica score, CAT, SARI, SCORE-GEO, indexação nem mecanismo de IA. Recomendações precisam ser validadas pelo analista humano e não são prova de inclusão em respostas generativas.


### Qualidade de extração e benchmark competitivo (#313)

A projeção de relatório inspeciona os `main_content.txt` já persistidos pelo M4, sem executá-lo novamente. Textos extremamente curtos dominados por rótulos usuais de navegação podem receber o diagnóstico aditivo `NAVIGATION_DOMINATED_SUSPECTED` em `artifacts/geo-extraction-quality.json`. Essa evidência é **heurística**, não representa erro confirmado do crawler, e não modifica nenhum snapshot, pontuação ou classificação de catálogo. A seção GEO apresenta o alerta e a referência ao arquivo para inspeção humana do DOM.

No comparador competitivo determinístico, um concorrente observado com HTTP 200 mas **sem qualquer texto de corpo, título, descrição, heading ou JSON-LD** continua com o status de coleta observado, mas não integra as medianas/gaps. Se nenhum concorrente possuir atributos analisáveis, a comparação não é consolidada. A opção elimina referências competitivas vazias sem alterar o motor de coleta nem apagar a resposta original.

Para consultas Perplexity com região SERP explicitamente brasileira, são encaminhados `country=BR` e `search_language_filter=pt`; esses filtros não certificam geolocalização de cada fonte. Fontes com TLD de outros países são preservadas e sinalizadas apenas para revisão de pertinência.
