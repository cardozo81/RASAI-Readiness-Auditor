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

### Resolução automática do escopo - #317

O RASAi, **não o Playground**, constrói o payload de `POST /search` no instante de execução da AUD. A solicitação Perplexity continua opt-in **por queries na AUD**, independente de `RASAI_PERPLEXITY_ENABLED=true`. Seleção WEB/FAST permanece escopo da auditoria. Não existe pesquisa implícita, OCR nem alteração do SERP, de scoring ou da orquestração IA.

Configurações adicionais **não secretas**, disponíveis no catálogo canônico (menus 5 e 6), editáveis e persistíveis no mesmo `rasai-console.ini`:

| Variável | Campo enviado à Search API | Padrão |
| --- | --- | --- |
| `RASAI_PERPLEXITY_MAX_RESULTS` | `max_results` (1..20 WEB/FAST) | 10 |
| `RASAI_PERPLEXITY_COUNTRY` | `country` ISO 3166-1 alpha-2 | omitido |
| `RASAI_PERPLEXITY_SEARCH_LANGUAGE_FILTER` | `search_language_filter` (ISO 639-1 separados por vírgula, até 20) | omitido |
| `RASAI_PERPLEXITY_SEARCH_DOMAIN_FILTER` | `search_domain_filter` (domínios sem URL, até 20) | omitido |
| `RASAI_PERPLEXITY_SEARCH_RECENCY_FILTER` | `search_recency_filter` (hour/day/week/month/year) | omitido |
| `RASAI_PERPLEXITY_SEARCH_AFTER_DATE` | `search_after_date_filter` (MM/DD/YYYY) | omitido |
| `RASAI_PERPLEXITY_SEARCH_BEFORE_DATE` | `search_before_date_filter` (MM/DD/YYYY) | omitido |
| `RASAI_PERPLEXITY_LAST_UPDATED_AFTER` | `last_updated_after_filter` (MM/DD/YYYY) | omitido |
| `RASAI_PERPLEXITY_LAST_UPDATED_BEFORE` | `last_updated_before_filter` (MM/DD/YYYY) | omitido |
| `RASAI_PERPLEXITY_MAX_CONTENT_UNITS` | `max_tokens` (1..1.000.000) | omitido |
| `RASAI_PERPLEXITY_MAX_CONTENT_UNITS_PER_PAGE` | `max_tokens_per_page` (1..1.000.000) | omitido |

**Precedência:** quando a região SERP da AUD identifica explicitamente Brasil, a chamada recebe `country=BR` independentemente de país de override; usa `search_language_filter=["pt"]` somente se não houver filtro de idiomas explícito. Sem região brasileira explícita, `RASAI_PERPLEXITY_COUNTRY` pode definir um país ISO de duas letras. **Nenhum país é inferido pelo ccTLD**; não se restringem domínios `.br` nem datas por padrão. O resultado pode incluir fontes estrangeiras, tratadas como evidências externas, não prova de localização.

O editor valida valores e o adapter revalida *antes da rede*: entrada inválida aborta apenas a pesquisa opcional (sem custo), preservando estado e evidências da AUD. O hash SHA-256 de `request_payload_hash` é calculado sobre o **JSON efetivamente enviado**; não contém credencial. O hash prova identidade dos bytes da solicitação, não reconstitui sozinho os parâmetros de uma execução antiga após mudança de INI. Versões históricas permanecem legíveis; não há alteração de esquema nem atualização retroativa de snapshots.

Documentação de campos e limites: https://docs.perplexity.ai/api-reference/search-post.

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

`PERPLEXITY_API_KEY` é a única **credencial secreta** consumida pelo runtime Perplexity. Flag de ativação e filtros opcionais são configurações não secretas. O editor é o mesmo usado pelo catálogo global: entrada mascarada, sessão e persistência/remoção explícita em Windows/User; o valor nunca entra no INI.

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

`RASAI_PERPLEXITY_ENABLED = true` é o **padrão do produto** que permite consultas explícitas à Perplexity Search API. `true` não dispara consultas automaticamente: a AUD ainda precisa de queries solicitadas e credencial `PERPLEXITY_API_KEY` configurada. `false` (`0`/`off`/`no`) impede chamadas externas e preserva a credencial e as queries existentes. A flag ausente preserva a compatibilidade anterior; valor inválido impede requisições por segurança. O `EnvironmentSpec` canônico registra o valor não secreto em `rasai-console.ini`; preferências `false` explícitas não são sobrescritas pelo baseline `true` no reinício. Restaurar padrões globais redefine `true`, mas não remove a chave quando escolhida a preservação de credenciais. CAT-05, Integrações e serviços e Todas as configurações expõem o controle. Diagnósticos locais permanecem sem consumo comercial.

A nova superfície transversal `geo.html` é advisory e parte do `report-catalog` da AUD individual. Lê apenas evidências persistidas; não substitui CAT-05, não altera índice e não comprova answer inclusion ou citation inclusion em respostas generativas. Comparações de URLs entre SERP e Perplexity somente têm semântica direta quando a Search API recebeu **uma única consulta** e existe observação SERP live válida equivalente. Requests multi-query não oferecem, no contrato atual, vínculo individual fonte→query: apresentar indisponibilidade da comparação em vez de inventar pareamento.

Apenas evidências rastreáveis podem fundamentar recomendações; snippets de concorrentes não comprovam conteúdo integral. A interpretação deve separar explicitamente observação, hipótese e ação de boas práticas. Evolução longitudinal para CONS-* fica no gap #311 e fora da presente implementação.

**Estado:** documento descreve projeto incremental; a implementação não deve ser considerada homologada até CI, testes de persistência/RPR, integridade e fechamento das issues-filhas #302-#310.


### Snapshot GEO derivado e reuso

A camada adicional `geo_observation_runs` mantém projeções imutáveis e versionadas (`RASAI-GEO-OBSERVATION-1` a `RASAI-GEO-OBSERVATION-4`) vinculadas a `audit_id`, `perplexity_run_id`, observação SERP comparável (quando disponível), fingerprint SHA-256 da entrada, contrato e timestamp de materialização. O ID é determinístico e a gravação é idempotente: nova evidência produz novo snapshot; a mesma evidência não é duplicada. Essa projeção não participa de scoring nem muda tabelas de origem.

Depois de uma pesquisa Perplexity explicitamente executada pelo console e persistida com sucesso, o adapter GEO cria o snapshot e utiliza a materialização canônica do relatório existente para refletir os dados. Falhas nessa projeção opcional permanecem advisory. RPR e complementos continuam sujeitos às regras existentes de snapshot e aquisição: rematerialização HTML lê o estado persistido e não chama a API. Se não existir snapshot compatível, a seção deve apresentar indisponibilidade em vez de refazer a observação ou reinterpretar o histórico.

No contrato v4, taxas de interseção por URL são exibidas somente para consulta única,
SERP observada via API e horários **com timezone explícito** cuja distância
não exceda 24 horas. Data sem fuso, clock inválido, diferença maior que 24 horas,
multi-query ou denominador vazio tornam as taxas N/D, com razão registrada;
contagens brutas não são apresentadas como taxas comparáveis. Os snapshots v1 a v3
não são regravados e mantêm suas limitações metodológicas originais.
O limite de 24 horas é apenas uma janela de elegibilidade descritiva, não um
ajuste estatístico ou prova de identidade de intenção, país, idioma e dispositivo.

A comparação é estritamente observacional: mesmo quando a consulta coincide, SERP e Perplexity podem diferir em momento, mercado, provider, profundidade e normalização. URLs recuperadas não são citações em respostas. As hipóteses de negócio/semântica são ações para avaliação humana, não causalidade comprovada.


### Interpretação GEO por IA canônica (#306)

O menu da Perplexity no CAT-05 oferece a opção explícita **"Síntese GEO por IA canônica nesta AUD"**, desabilitada por padrão e separada da pesquisa externa. A pesquisa Perplexity somente solicita requisições quando o operador informou consultas, ativação e credencial aplicáveis. A síntese por IA somente considera fontes persistidas e uma consulta única com provenance rastreável. A análise não lê automaticamente o conteúdo integral dos concorrentes.

O consumidor `rasai.geo_ai` reutiliza o contrato `CompetitiveAiInput`/`CompetitiveAiEvidence` e o builder já instalado da orquestração competitiva canônica. Não existe cliente HTTP privado, fallback de provider ou motor próprio de preços/retries. Caso a orquestração canônica não esteja instalada, configurada ou elegível, a síntese é indicada como indisponível; a AUD e CAT-05 não são rebaixados.

As interpretações bem-sucedidas e tentativas derivadas são persistidas em `geo_ai_interpretations`, vinculadas a `audit_id` e `perplexity_run_id`, com hash de entrada, provider, modelo, versões de prompt, status e oportunidades com IDs de evidência. Antes de nova tentativa, o consumidor verifica o mesmo fingerprint e seleção: uma análise já persistida é reutilizada sem nova chamada faturável. RPR, complemento e geração HTML não executam esse consumidor, apenas projetam os dados persistidos. O report `geo.html` diferencia a interpretação GEO específica de sínteses competitivas pré-existentes em SERP.

A exposição a texto de fonte externa é limitada a metadados e snippets, tratados como evidência observacional não confiável. A saída não modifica score, CAT, SARI, SCORE-GEO, indexação nem mecanismo de IA. Recomendações precisam ser validadas pelo analista humano e não são prova de inclusão em respostas generativas.


### Qualidade de extração e benchmark competitivo (#313)

A projeção de relatório inspeciona os `main_content.txt` já persistidos pela extração determinística, sem executá-lo novamente. Textos extremamente curtos dominados por rótulos usuais de navegação podem receber o diagnóstico aditivo `NAVIGATION_DOMINATED_SUSPECTED` em `artifacts/geo-extraction-quality.json`. Essa evidência é **heurística**, não representa erro confirmado do crawler, e não modifica nenhum snapshot, pontuação ou classificação de catálogo. A seção GEO apresenta o alerta e a referência ao arquivo para inspeção humana do DOM.

No comparador competitivo determinístico, um concorrente observado com HTTP 200 mas **sem qualquer texto de corpo, título, descrição, heading ou JSON-LD** continua com o status de coleta observado, mas não integra as medianas/gaps. Se nenhum concorrente possuir atributos analisáveis, a comparação não é consolidada. A opção elimina referências competitivas vazias sem alterar o motor de coleta nem apagar a resposta original.

Para consultas Perplexity com região SERP explicitamente brasileira, são encaminhados `country=BR` e `search_language_filter=pt`; esses filtros não certificam geolocalização de cada fonte. Fontes com TLD de outros países são preservadas e sinalizadas apenas para revisão de pertinência.


### Correlação temporal entre DOM e screenshot (#315)

O motor de captura existente obtém o DOM serializado e, posteriormente, o screenshot do mesmo contexto de navegação. Quando o estado materializado de `capture_quality` já for `INCOMPLETE` e houver screenshot, uma única leitura adicional de `page.content()` após a imagem gera a metainformação `screenshot_dom_correlation`: versão do contrato, SHA-256 do HTML congelado e do DOM observado após screenshot, comprimento textual de `<main>` nos dois instantes e delta. A observação é local, não navega, não consulta providers e não substitui arquivos, hashes originais, pontuações nem as regras da captura renderizada. Para capturas `READY`, screenshots não capturados ou falhas no probe, não há impacto operacional: o estado será `NOT_APPLICABLE` ou `UNAVAILABLE`.

Uma divergência temporal positiva é sinal observacional de conteúdo que apareceu após o primeiro DOM, **não** comprovação de que uma captura visual seja legível/indexável por crawler. O diagnóstico GEO de confiabilidade apresenta os artefatos de extração e de HTML/screenshot associados por SNP, sem OCR, e precisa de análise contextual antes de recomendar qualquer correção técnica.


## Complemento externo GEO de auditoria concluida (#318 / #323)

No menu de parametros CAT-05 > Perplexity, a opcao **6** permite propor a copia de termos SERP para Perplexity, mas somente apos confirmacao afirmativa. SERP e Perplexity nunca compartilham intencao automaticamente.

A opcao **7** aceita o caminho de uma **AUD COMPLETE existente** e solicita queries, tipo WEB/FAST, pais, `intent_id` exclusivo e autorizacao expressa para **uma** consulta Search API potencialmente faturavel. A consulta e o custo nao sao disparados pelo toggle da integracao nem pela existencia de chave. A extensao nao executa novamente captura, extracao, SERP, PSI, IA canonica nem Apdex.

O suplemento fica fora da pasta original da AUD, em `<audits-root>/.rasai-geo-supplements/<audit_id>/<intent-hash>/`. Contem `intent.json`, `result.json`, `supplement.html`, `evidence/audit.db` e `manifest.json` proprios. Um mesmo `intent_id` e escopo retorna o pacote existente sem novo HTTP. Intencao iniciada e nao finalizada **nao deve ser reenviada automaticamente**, pois timeout de rede pode ter faturamento desconhecido. Novo `intent_id` configura uma nova requisicao que exige novo aceite.

Antes da extensao, sao verificadas a situacao `COMPLETE`, a integridade SQLite/FK e o pacote `report-catalog` original. O pacote e manifestos **originais nao sao atualizados**; o suplemento externo apresenta proveniencia e hash de vinculo. Resultados posteriores nao sao promovidos ao score ou reclassificados como observacoes historicas da AUD. O contrato da fronteira e o estudo de reuso estao em [ADR_PERPLEXITY_SEARCH_REUSE_323.md](ADR_PERPLEXITY_SEARCH_REUSE_323.md).

**Limite:** executar a consulta real ainda depende de autorizacao humana explicita no console; a suite automatizada usa transporte fake sem consumo de API paga.


### Hardening de complemento e replay #318 - 09/10/2026

No replay de um suplemento existente, a identidade da AUD original deve
continuar igual à registrada na reserva inicial (SHA-256 do `audit.db`,
fingerprint do estado e SHA-256 do manifesto do `report-catalog`).
O `intent_id` somente pode reutilizar arquivos com manifesto íntegro,
mesmo escopo e lista completa de quatro arquivos exigidos. Manifesto
corrompido, diretório/arquivo linkado ou trilha insegura não autorizam nova
requisição Search API nem são interpretados como sucesso. Resultados
inconclusivos demandam revisão humana; nunca reutilizar um suplemento
ligado a outra versão física da AUD. Esta checagem é local, automática,
sem chamadas externas e **não** homologa faturamento comercial real.


### GEO observation v5 - exact URL versus domain-family evidence (09/10/2026)

A versão `RASAI-GEO-OBSERVATION-5` conserva `www.` no host ao
normalizar URL para comparação exata. Sem redirecionamento canônico
realmente observado, `https://www.example.org/a` e
`https://example.org/a` **não** são a mesma URL exata;
a relação por família de domínio continua elegível como alternativa
sob interpretação advisory. O mesmo rigor vale para o conjunto de URLs
SERP x Perplexity: esse par não conta como URL comum, embora haja
similaridade de domínio. O snapshot v4 anterior permanece imutável;
novas análises derivadas recebem identificador e contrato v5 próprios.
Continuam obrigatórios query única, clocks verificáveis <=24h,
denominadores de URLs válidos e avisos de não equivalência
mercado/idioma/dispositivo/intenção. O `geo.html` respeita abstenção N/D
tanto em v4 quanto v5; nenhuma inferência de canonical SEO ou citação
generativa decorre desta normalização.


### Pré-condição de frescor do pacote original em complemento pós-AUD (#318)

A rotina externa de complemento exige simultaneamente integridade do pacote
`report-catalog` pelo manifesto e **frescor em relação ao estado corrente da
AUD original**, utilizando o entrypoint canônico
`catalog_report_is_fresh(audit_id, workspace)`. Um pacote antigo pode
continuar internamente íntegro, mas não corresponder ao `audit.db` atual;
essa condição bloqueia a reserva de intenção e qualquer tentativa
Perplexity **antes de consumo tarifável**. Este guard não modifica o pacote,
não reinterpreta uma AUD e não autoriza reenvio em casos ambíguos.


## Consulta dos complementos GEO pós-AUD (CAT-05, #318/#309)

No submenu **P. Perplexity** do CAT-05, a opção **8. Consultar
complementos GEO existentes** é somente leitura e independe de ativação
de Perplexity, chave, parâmetros SERP ou nova autorização comercial.
O operador informa a pasta da AUD COMPLETE e recebe as intenções
pré-existentes, o estado de verificação e, quando confirmado, o caminho
do relatório independente `supplement.html`.

A verificação exige: pacote original íntegro/fresco, origem da AUD
estável, requisição autorizada com hash/escopo consistente, manifesto
independente com SHA-256 dos arquivos, `result.json` coerente e
`perplexity_search_runs` da base derivada vinculado ao run_id,
query, search_type, estado da execução, integridade SQLite e FKs.
Um manifesto isolado não basta para afirmar sucesso. Saídas possíveis:

- `VERIFIED`: dados locais da intenção, resultado e ledger
  verificados; não implica citação em resposta de IA.
- `PENDING_UNCERTAIN`: reserva incompleta ou resposta sem
  evidência conclusiva. Não refazer automaticamente, pois cobrança
  pode ter ocorrido.
- `INVALID`: identidade ou integridade não verificáveis.
  Não considerar evidência GEO e não reenviar automaticamente.

O inventário não cria sidecars, não materializa novos catálogos, não
muda o banco original e não dispara Search API ou IA. Não tenta
transformar automaticamente o suplemento externo em snapshot GEO v5
da AUD selada. Essa projeção futura permanece pendente no #311/#309.


### Pré-checagem comercial de configuração (CAT-05 #318)

A opção de **novo complemento externo** rejeita habilitação ausente
(`DISABLED`) e credencial Perplexity ausente (`NOT_CONFIGURED`)
**antes** de reservar o `intent_id` e, na interface, **antes** de pedir
o caminho da AUD ou confirmar cobrança. Configurar a flag não valida
automaticamente o token: validade remota, crédito e eventuais falhas
só podem ser conhecidos pela resposta real do serviço, após autorização.
A autorização explícita continua obrigatória mesmo quando a credencial
está ausente. A consulta read-only pela opção **8** funciona sem token
e não dispara integrações nem recálculo de relatórios.


### GEO observation v6 - eleição de amostra SERP pela proximidade temporal (#304)

A versão `RASAI-GEO-OBSERVATION-6` corrige um viés de seleção da
amostra SERP por consulta única: antes, a observação SERP mais
recente podia estar fora da janela de 24h de uma Search API
enquanto uma observação anterior da mesma consulta estava
temporalmente próxima e era mais comparável.

Agora só amostras `OBSERVED_API/OBSERVED`, correspondentes à
**mesma consulta textual** e com instantes offset-aware
dentro de 24h concorrem ao cálculo. Seleciona-se o menor
intervalo de tempo; empates favorecem o SERP mais recente
e depois o ID de observação estável. Se não houver nenhuma
amostra elegível, preserva-se o diagnóstico de abstenção
(`TIME_SCOPE_UNPROVEN` ou `TIME_SCOPE_OUTSIDE_WINDOW`),
sem inventar sobreposição numérica.

Essa regra melhora apenas a seleção de evidência já
persistida, não afirma intenção equivalente, posição em
resposta gerativa ou relevância de negócio. Não executa
coletas, serviços externos, IA ou pontuação. Snapshots v1-v5
pré-existentes conservam seus métodos e identificadores.


### GEO IA opcional: abstenção antes de escrita (#306, 09/10/2026)

A seleção explícita de síntese GEO por IA não significa que exista
evidência apta para síntese. O consumidor canônico da AUD verifica
primeiro, **sem criar tabelas derivadas**, a presença de uma execução
Perplexity persistida, bem-sucedida, atribuível a exatamente uma
consulta e com fontes reais. Sem esses pré-requisitos retorna
`NOT_ELIGIBLE`: não cria `geo_ai_interpretations`, não invoca a IA,
não consome quota nem altera o banco da AUD. Se houver evidências
e a execução for explicitamente solicitada, continuam válidos o
contrato de consumidor canônico, a persistência de estado terminal
e os IDs de evidência exigidos. Reprocessamentos e visualização HTML
não ganham capacidade de disparar chamadas.


### CAT-08: última tentativa de síntese GEO, não último sucesso (#308)

A projeção GEO do CAT-08 consulta o estado mais recente da
interpretação persistida para a **mesma AUD**, ordenando pelo
timestamp gravado e, em empate, pelo identificador. Quando o
último estado não é `AVAILABLE`, exibe indisponibilidade,
sem promover uma interpretação antiga que poderia parecer
a avaliação vigente. Exibir indisponibilidade não causa
nova inferência, cobrança, reprocessamento nem alteração de
scores/achados. O estado registrado é renderizado com escape
HTML e a ausência de interpretação continua explicitamente
identificada.


## Inventário do ciclo de suplementos independentes (#309)

Para uma AUD COMPLETE selada, o comando read-only

```powershell
.\.venv\Scripts\python.exe -m rasai geo-supplements ".\audits\AUD-EXEMPLO"
```

consulta os dados já existentes em `.rasai-geo-supplements` sem flags,
chaves, nova autorização, requests externos ou materialização. Reutiliza
a mesma validação de origem, manifesto e ledger da consulta no console
CAT-05 Perplexity > opção 8. Saída JSON por intenção: `VERIFIED`,
`PENDING_UNCERTAIN` ou `INVALID`, com disponibilidade do HTML
**somente** para evidências integralmente verificadas e contadores
`provider_requests=0` e `audit_writes=0`. Falha/timeout
de faturamento desconhecido permanece incerto, sem repetição automática.
Esse inventário não prova citação em IA, não altera o snapshot GEO v5/v6
da AUD original e não aciona RPR.

O estado `VERIFIED` certifica **integridade e vínculo do pacote**, não uma
resposta HTTP bem-sucedida. O inventário expõe separadamente
`search_status`, `verified_source_count`, `search_started_at` e
`search_finished_at` apenas após conferir os registros de resultado,
fontes, timestamps e faturabilidade contra o SQLite derivado. Totais
`verified_successful_searches` e `verified_unsuccessful_searches`
distinguem sucesso de erro de autenticação, rate limit e outras falhas.
Um `result.json` adulterado, mesmo acompanhado de manifesto com novos
hashes, não pode declarar fontes não persistidas ou converter cobrança
registrada como possível/verdadeira em gratuita. Para pacote `INVALID`
ou `PENDING_UNCERTAIN`, o resultado e a quantidade de fontes não são
inferidos. Custos e tempos dos suplementos não entram nas somas da AUD
original (#319). Nenhuma chamada comercial é realizada pela inspeção.


### Reuso de intenção pós-AUD: integridade semântica (#309)

Quando uma intenção comercial já está reservada, a nova entrada de
solicitação não aceita `ALREADY_RECORDED` com base apenas nos hashes do
manifesto. A mesma verificação semântica read-only do inventário confere
consulta, escopo autorizado, `result.json`, execução e fontes SQLite,
status, timestamps e `billable`; rejeita adulteração mesmo após rehash.
Nenhuma rejeição causa reenvio de `POST /search`: erro ou dúvida exige
inspeção humana, porque a cobrança anterior pode ter ocorrido.
A AUD original permanece selada e não é rematerializada.


### GEO observation v7 - requisição externa corrente comprovável (#304/#309)

`RASAI-GEO-OBSERVATION-7` mantém a eleição de SERP válida mais próxima
introduzida em v6. Corrige o **outro lado** do pareamento: a seleção do
run Perplexity corrente deixa de usar ordenação lexical de `started_at`
ou `run_id`. Se existirem várias pesquisas, a escolha exige instantes
com fuso explícito comparados em UTC; dois runs com relógio empatado,
inválido ou sem timezone tornam impossível provar qual é o último.
Nesse caso, a projeção devolve ausência de novo snapshot, sem criar
tabelas, chamar APIs, acionar IA ou promover um sucesso antigo. Um run
único preserva a compatibilidade com históricos que não precisavam
escolher entre múltiplos instantes.

O status real do run mais recente (inclusive AUTH_ERROR, TIMEOUT etc.)
é preservado como evidência de serviço; **não** vira falha do website,
pontuação GEO, zero cobertura inventada ou autorização para retry pago.
Snapshots v1-v6 continuam com versões, IDs e bytes anteriores. A nova
versão possui fingerprint e ID derivados de suas fontes efetivamente
selecionadas e é reproduzível sem nova consulta. `geo.html`, o
read-only longitudinal e o seletor de IA reconhecem o método v7 e
continuam a tratar evidência de busca como observação, não citação de IA.


### GEO observation v8 - equivalencia exata de URL sem redirecionamento presumido (#304)

`RASAI-GEO-OBSERVATION-8` conserva o criterio de consulta unica, janela
temporal e escolha do ultimo run Search API verificado por UTC (v7).
O ajuste desta versao e estritamente semantico e afeta apenas NOVOS
snapshots derivados: `/produto` e `/produto/` **nao** sao URLs identicas
sem evidencia observada de redirecionamento ou canonical. Um resultado
com a rota alternativa pode continuar sendo descrito como observacao
de outra URL do dominio, mas nunca soma a cobertura exata da pagina.
A identidade exata preserva protocolo, host, porta nao-default,
caminho e query; ignora somente fragmentos de pagina, ausentes no
request HTTP, e normaliza portas default. URLs com userinfo, controles
ASCII, backslash, whitespace interno ou porta zero nao contribuem
para denominadores de URLs validas.

O metodo foi versionado em v8 para impedir mistura com as metricas
das versoes anteriores. Snapshots v1-v7 permanecem imutaveis;
a leitura longitudinal do metodo antigo reusa a normalizacao daquela
versao, enquanto grupos v8 recebem a semantica mais estrita. Em
nenhuma situacao o v8 atribui redirecionamento/canonical, marca,
intencao, regiao, idioma, citacao gerativa ou ranking nao observados.
As rates continuam DESCRIPTIVE_ONLY para query simples efetivamente
coincidente; multi-query ou clocks nao demonstraveis continuam N/D.
Sem chamada extra a Perplexity ou SERP, mudanca nos coletores,
indices homologados, score GEO, Apdex ou storage de capturas.


### Segurança do lifecycle GEO: reserva, isolamento e reuso (#306/#309/#318)

A rotina `materialize_geo_observation` abre somente um `audit.db` regular,
preexistente e nao simbolico, em modo SQLite `rw` sem criacao implicita.
Um caminho inexistente retorna N/D e nao cria um banco vazio, artefato,
snapshot ou solicitacao de provider.

O complemento externo vincula `audit_id` e identidade da AUD ao workspace
derivado. Antes da reserva comercial, o executor e o inventario rejeitam
`.rasai-geo-supplements` ou seu subdiretorio da AUD caso estejam ligados por
symlink. A validacao de arquivos e do ledger continua obrigatoria. Um diretorio
de destino fora do escopo nao pode receber evidencias ou autorizacao de custo
por um caminho simbolico.

Na interpretacao GEO por IA canonica, a mesma combinacao de AUD, Search run,
modelo selecionado, versao do contrato e fingerprint da entrada tem uma
reserva persistida `PENDING_UNCERTAIN` confirmada em transacao **antes**
de `provider.analyze`. Sucesso ou indisponibilidade substituem esse estado
apos a resposta. Se o processo parar no meio de uma chamada possivelmente
faturavel, um novo clique com o mesmo fingerprint encontra a reserva e nao
envia outro pedido automaticamente. Este contrato e de **at-most-once** do
RASAi, nao prova de idempotencia comercial no fornecedor. Auditoria/replay/HTML
apenas exibem a incerteza e orientam consulta do ledger antes de nova
autorizacao. Nenhuma reserva pendente significa que um custo foi comprovado.

Os testes sao locais e isolados, com interrupcao simulada e symlinks
adversariais; nao contratam IA ou Perplexity, nao alteram RPR ou os motores
homologados e nao migram auditorias anteriores.

### Hardening observacional, financeiro e da interpretacao GEO IA (09/10/2026)

A inspecao read-only de complemento externo compara adicionalmente
`native_usage_unit`, `native_usage_quantity`,
`posthoc_estimated_cost`, `cost_currency` e `pricing_version`
de `result.json` com a linha `perplexity_search_runs` persistida
no SQLite derivado. Alterar o JSON e recomputar os SHA-256 do manifesto
nao comprova uso ou preco diferente. Quantidades nao finitas, valores
negativos e tipos ambiguos sao invalidados sem reenvio.
Estimativa pos-uso nao e fatura do fornecedor.

O contexto de IA GEO opcional inclui somente URLs HTTP/HTTPS
sintaticamente validas segundo o canonizador v8, sem credenciais
userinfo, whitespace ou esquemas executaveis. Titulos/snippets sao
limitados antes de alimentar o consumidor canonico; se nenhuma fonte
valida permanece, nenhuma chamada de IA, reserva ou DDL e executada.
O resultado persistido passa a conservar `causality_note` de cada
oportunidade da IA e o HTML apresenta justificativa e limite causal
com escape, sem promover hipotese a fato. Nenhum coletor, provider,
score, reprocesso ou historico antigo e recalculado.

### Seleção independente e autorização de queries Perplexity (#318)

No console, `T` configura os termos SERP e `U` configura
independentemente a consulta externa Perplexity. O menu exibe
separadamente **integração HABILITADA/DESABILITADA**,
**credencial CONFIGURADA/NÃO CONFIGURADA** e
**pesquisa SOLICITADA/NÃO SOLICITADA**. Uma chave definida nunca
implica autorização ou envio de pesquisa externa.

No menu `U`, quando existem termos SERP, o operador pode
escolher explicitamente **copiar** esses termos para a solicitação
Perplexity. A escolha padrão é **não**; não há herança automática.
Um conjunto SERP com mais de cinco termos é recusado integralmente,
sem cópia parcial. A interface permite revisar os termos, selecionar
WEB/FAST e exibe que o custo de uma consulta não tem cotação
comprovada (**N/D**), podendo haver cobrança externa. Uma segunda
confirmação, com padrão **não**, autoriza agendar essa pesquisa
apenas **após a auditoria**; recusar limpa solicitações anteriores,
evitando executar drafts persistidos na sessão. A configuração
não faz HTTP nem dispara provedor; a aquisição continua separada
e sujeita à disponibilidade e à governança do serviço.

No relatório HTML separado de suplemento, URLs vindas da Search API
permanecem preservadas no ledger, porém só são exibidas como links
clicáveis se passam pela regra estrita de identidade GEO v8 (HTTP(S)
sem userinfo, controles, backslashes ou URL ambígua). Fontes
inválidas não são legitimadas por um prefixo textual `https://`.
Isso não reescreve fontes externas, custos, hashes, AUDs anteriores
nem implementa navegação/fetch da página concorrente.

#### Evidências GEO IA: limite após validação (#306)

A interpretação GEO lê no máximo 256 candidatos persistidos da última
pesquisa válida e só depois de eliminar URLs inválidas seleciona as
primeiras 12 fontes aptas. Antes, as 12 primeiras linhas eram
selecionadas no SQLite **antes** da validação; resultados suspeitos
nas primeiras posições podiam ocupar todo o orçamento de evidências e
ocultar fontes válidas subsequentes. A mudança é estritamente local
ao adaptador opcional, não amplia o limite de contexto de IA e não
faz chamada adicional de provider ou crawler.
