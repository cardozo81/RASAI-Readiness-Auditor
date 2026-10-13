# #355 - Dynatrace RUM Apdex versus arquitetura descoberta

## Conclusão da pesquisa de documentação oficial

Uma aplicação classificada como SPA **não** deve ter seu Apdex de
carregamento automaticamente substituído por um Apdex de XHR.
O primeiro carregamento do documento continua sendo uma Load action.
Transições de rota/client-side e interações com XHR/Fetch podem produzir
XHR actions; interações que não forem identificadas automaticamente
podem precisar de ações customizadas. A presença ou ausência depende
da instrumentação real e do uso observado, não apenas da arquitetura.

Fontes oficiais Dynatrace, consultadas em 09/10/2026:

- [User actions in RUM Classic](https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions)
- [Capture XHR actions and SPA navigation](https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/initial-setup/configure-dynatrace-real-user-monitoring-to-capture-xhr-actions)
- [Configure Apdex settings for web applications](https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/additional-configuration/configure-apdex-web)
- [Load action KPM schema](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions)
- [XHR action KPM schema](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-xhr-actions)
- [Custom action KPM schema](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-custom-actions)

## Configurações distintas

| Tipo de ação RUM | Indicadores oficiais possíveis para Apdex | Escopo típico |
| --- | --- | --- |
| Load | USER_ACTION_DURATION, VISUALLY_COMPLETE, SPEED_INDEX, DOM_INTERACTIVE, LOAD_EVENT_END/START, RESPONSE_END/START, FIRST_INPUT_DELAY, LARGEST_CONTENTFUL_PAINT, CUMULATIVE_LAYOUT_SHIFT | Navegação que carrega o documento |
| XHR | USER_ACTION_DURATION, VISUALLY_COMPLETE, RESPONSE_END/START | Interação XHR/Fetch, inclusive soft navigation SPA quando realmente observada |
| Custom | USER_ACTION_DURATION | Ação explicitamente instrumentada quando a detecção padrão não a representa |

As configurações de Load e XHR possuem limiares independentes
`thresholds` (tolerated/frustrating) e `fallbackThresholds`
(toleratedFallbackThresholdSeconds e
frustratingFallbackThresholdSeconds). A documentação não prescreve
um threshold numérico universal para SPA, SSR ou HYDRATED.
Limiares devem ser calibrados por objetivo de experiência e
distribuições reais de ações. A existência de `VISUALLY_COMPLETE`
não comprova automaticamente prontidão de conteúdo principal
nem capacidade de interação do usuário.

## Matriz de avaliação proposta

| Arquitetura RASAi | Evidência observada | Avaliação |
| --- | --- | --- |
| CSR_SPA | Navegação inicial de documento | Load actions podem ser adequadas para esse recorte |
| CSR_SPA | Soft navigation com XHR/Fetch, mas nenhuma XHR action declarada no RUM | Revisar captura de XHR/Fetch e população de ações; não mudar Apdex automaticamente |
| HYDRATED / MIXED | Carregamento inicial e rotas client-side | Avaliar Load e XHR por universo de ações observado |
| STATIC_OR_SSR | Navegações completas sem soft route comprovada | Load action pode ser adequada; não exigir XHR artificialmente |
| UNKNOWN | Evidência de arquitetura ausente | N/D, sem recomendação categórica |

## Implementação aditiva

`rasai.dynatrace_apdex_arch_advisory_355.assess_dynatrace_apdex_architecture`
é uma função puramente determinística que recebe explicitamente:
arquitetura, ID de evidência da classificação, presença de soft
navigation e gatilho XHR/Fetch, e um snapshot **fornecido pelo chamador**
contendo configurações de Load/XHR/Custom, limiares/fallbacks, flags
de captura e contagens de ações. A rotina valida enums e intervalos,
confere cobertura por tipo de ação, identifica ausências ou contradições,
e devolve classificação e próximos passos sem inventar números.

A função não tem cliente Dynatrace nem privilégios do tenant.
`settings_provenance=NOT_VERIFIED_BY_RASAI` é obrigatório: fornecer
um JSON não comprova que o tenant foi consultado, que o snapshot
foi produzido na mesma janela de observação ou que o RUM capturou
as mesmas interações do Apdex sintético. Ausência de configuração
ou de contagens confiáveis é `NOT_EVALUABLE` ou
`INSUFFICIENT_ACTION_SCOPE`, nunca diagnóstico de bug do site.

Os outputs não recalculam os Apdex homologados M23/M25, não
mudam SCORE-GEO/SARI, não criam findings, não produzem custos
de provider e não são conectados a um relatório real sem evidência.
Os testes são fixtures sintéticas isoladas.

## Gate ainda pendente

Para a frase do relatório "Detectada arquitetura X; observada
configuração Apdex Y; recomenda-se revisar Z" ser auditável,
será necessário obter configurações reais do Dynatrace mediante
integração **read-only com permissão settings.read**, vincular
application ID e período de observação da mesma URL/rota,
registrar contagens de Load/XHR/Custom, instrumentação Fetch/XHR
e key user action overrides. Somente depois integrar a síntese
na camada advisory do relatório e oferecer nova auditoria.
Não há autorização para consultar tenant, nem medição RUM
disponível nesta fase. Nenhum threshold poderá ser sugerido
como valor oficial para arquitetura isoladamente.


## Revisao offline operavel de configuracoes RUM (sem acesso ao tenant)

A funcao pura do #355 tambem pode ser chamada com um JSON local, por exemplo
um snapshot exportado/manual de configuracoes compatíveis com seu esquema:

```powershell
.\.venv\Scripts\python.exe -m rasai dynatrace-apdex-review `
  --architecture CSR_SPA `
  --architecture-evidence-id M6-REFERENCIA-LOCAL `
  --soft-navigation observed `
  --async-requests observed `
  --settings-json .\dynatrace-rum-settings.json
```

O retorno JSON separa tipo de acao Load/XHR/Custom, KPM e diagnostico de
cobertura. Os tres parametros de observacao e o documento sao fornecidos
pelo operador; nao sao provas de capturas fisicas, tampouco resultado de
`settings.read`. A ferramenta informa `settings_provenance:
NOT_VERIFIED_BY_RASAI`, `actual_dynatrace_tenant_consulted: false` e zero
requests. Arquivo ausente ou nao JSON e recusado. O CLI nao instala
runtime de auditoria, nao expoe um campo de token fornecido no JSON e nao
executa M23/M25. Ainda e obrigatorio confirmar application ID, escopo,
janela temporal, captura de rotas e thresholds em Dynatrace real para
uma recomendacao homologada, conforme o gate desta issue.


## Adaptador offline Settings API effectiveValues - entrega adicional #355

O comando passa a aceitar JSON exportado da rota documentada
`GET /api/v2/settings/effectiveValues` (Dynatrace Settings API 2.0).
As consultas reais exigem `settings.read` ou `settings:objects:read`;
**este fluxo NÃO as executa**. O operador exporta fora do RASAi.
Fontes oficiais:
- https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/objects/get-effective-values
- https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions
- https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-xhr-actions
- https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-custom-actions

Exemplo: exporte o JSON completo de effectiveValues com as três
`schemaIds` específicas de Apdex RUM Web e escopo `APPLICATION-...`.
Depois use, sem credenciais:

```powershell
.\.venv\Scripts\python.exe -m rasai dynatrace-apdex-review `
  --architecture CSR_SPA `
  --architecture-evidence-id M6-REFERENCIA-LOCAL `
  --soft-navigation observed `
  --async-requests observed `
  --effective-values-json .\effective-values-apdex.json `
  --application-scope APPLICATION-ID-DECLARADO
```

O `--application-scope` é **declaração do operador** e NÃO demonstra que
o arquivo foi realmente solicitado naquele escopo. O endpoint
effectiveValues fornece `schemaId`, `value`, `schemaVersion`,
`origin` e paginação; não fornece sozinho contagens de ações nem
prova que o período/URL coincidam com M6. O adaptador rejeita
paginação incompleta, totalCount divergente, itens duplicados,
schemas desconhecidos, objeto inválido, tamanho >1 MiB e symlinks.
`capture` e `action_counts` continuam ausentes, em vez de
serem simulados como desligados/zero.

Somente campos documentados são mapeados:
`load_actions`, `xhr_actions`, `custom_actions` com
`thresholds`, `fallbackThresholds` (Load/XHR) e KPMs suportadas.
`settings_provenance=NOT_VERIFIED_BY_RASAI` e
`actual_dynatrace_tenant_consulted=false` permanecem.
O output adicional apresenta origem e versões declaradas sem
converter o JSON em configuração executada do M25.

Esta etapa conclui **leitura compatível com exportação do fornecedor
sem rede**. Não conclui a integração live com token, avaliação de
políticas por URL nem correlação física de amostras RUM; #355
permanece aberta até esses gates e aprovação humana.

## Explicação para o analista humano no CLI (complemento #355)

Além dos códigos estruturados determinísticos, o comando
`dynatrace-apdex-review` apresenta `analyst_guidance_pt_br` com
conclusão, arquitetura **informada**, KPMs **declaradas no arquivo** por
Load/XHR/Custom, motivos em português, próximos passos e ressalva explícita
de que o export não comprova tenant, captura, população de ações, período,
URL nem identidade física de amostra com M6. Essa explicação não converte
configuração offline em medição efetiva, não sugere limiares universais e
não altera o status do contrato, as fórmulas M23/M25, a AUD ou o relatório.
A integração de settings.read e a projeção no relatório de auditoria
continuam condicionadas aos gates de autenticação/proveniência e aceite.


## Leitura efetiva opt-in via Settings API (fase aditiva #355)

O comando `rasai dynatrace-apdex-review` suporta opcionalmente
`--live-base-url https://<ambiente>.live.dynatrace.com`,
`--application-scope APPLICATION-...` e
`--allow-live-settings-read`. A chamada GET única e somente leitura usa
o token já reconhecido pelo RASAi em `DYNATRACE_API_TOKEN`, exclusivamente
em cabeçalho, e requer escopo `settings.read`.
O CLI nunca imprime o token nem o corpo de erro HTTP.

O adaptador permite somente HTTPS em ambiente SaaS Dynatrace com
domínio `.live.dynatrace.com`, bloqueia URLs com usuário, query,
path e porta, rejeita redirecionamento, limita a resposta a 1 MiB
e um único request de até 10 segundos; exportações paginadas não são
apresentadas como completas. Não há retry, coleta RUM nem escrita
em AUD. A resposta declara o número de solicitações e distingue
`LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES` de exports offline.

Exemplo de ativação somente quando autorizado pelo operador:

```powershell
$env:DYNATRACE_API_TOKEN = "<token settings.read>"
.\.venv\Scripts\python.exe -m rasai dynatrace-apdex-review `
  --architecture CSR_SPA `
  --architecture-evidence-id SNP-REFERENCIA `
  --soft-navigation observed --async-requests observed `
  --application-scope APPLICATION-REFERENCIA `
  --live-base-url https://ambiente.live.dynatrace.com `
  --allow-live-settings-read
```

**Fronteira de confiança:** a resposta autenticada prova apenas valores
efetivos de configuração devolvidos pela Settings API para o scope
consultado; não comprova população de Load/XHR/Custom Actions,
correlação com `snapshot_id/page_id/device`, rota visitada ou período
da auditoria. Os índices sintéticos RASAi M23/M25 permanecem separados.
Ausência de token, request não autorizada ou resposta incompleta => erro
explícito, sem troca silenciosa de metodologia ou provider.

Referência oficial:
https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/objects/get-effective-values

## Consulta de população de Load/Xhr/Custom na RUM Classic (#355)

O adaptador `python -m rasai.dynatrace_rum_population_355` é
**independente e opcional**, separado do Settings API 2.0 e de M25.
Um único GET ao endpoint oficial `/api/v1/userSessionQueryLanguage/table`
consulta **somente** `COUNT(*)` agrupado por `type` em `useraction`,
com filtros explícitos e exatos de `internalApplicationId`,
`targetUrl`, `usersession.device` e janela UTC de no máximo 24h.

- Requer `--allow-live-usql-read` e token de ambiente
  `DYNATRACE_USQL_API_TOKEN` com privilégio **DTAQLAccess**.
  Não reutiliza implicitamente o token `settings.read` do Settings API.
- Somente tenant SaaS `*.live.dynatrace.com` HTTPS, sem credenciais
  embutidas na URL, sem redirects/retries, HTTP GET com 10 segundos e
  resposta JSON até 256 KiB.
- Apenas `columnNames=["type","COUNT(*)"]` e grupos não ambíguos são
  aceitos. Contagens negativas, booleanas, duplicadas ou schema incerto
  tornam a análise N/D. Nenhuma linha de sessão individual, ID de usuário,
  IP ou PII é consultada, retornada ou persistida.
- `action_counts` registra Load, Xhr, Custom e outros tipos agregados,
  com total e período UTC. **Zero Xhr observado** em um filtro não prova
  captura XHR/Fetch desabilitada, nem prova que SPA não faça soft navigation.
- `rasai_same_browser_sample_verified=false` permanece: mesmo escopo
  literal de URL/dispositivo/período em RUM e RASAi não comprova que as
  ações são a mesma sessão física de Playwright/M6. Não importa
  thresholds, reprocessa AUD nem muda scores M23/M25.

Exemplo controlado com token já provisionado:

```powershell
python -m rasai.dynatrace_rum_population_355 `
  --live-base-url https://tenant-example.live.dynatrace.com `
  --application-id APPLICATION-1234567890ABCDEF `
  --target-url https://www.example.com/pagina `
  --dynatrace-device MOBILE `
  --start-timestamp-ms 1780000000000 `
  --end-timestamp-ms 1780000900000 `
  --allow-live-usql-read
```

A consulta não ocorre automaticamente; não foi realizada em tenant real
nesta entrega. O token nunca é impresso. A API clássica tem limitações de
retencão e amostragem e **não equivale** à API de eventos do RUM atual.
Validar versão Dynatrace e valores de `device` no tenant antes do aceite.
Fonte oficial: [User Sessions API - GET table]
(https://docs.dynatrace.com/docs/dynatrace-api/environment-api/rum/user-sessions/table),
[USQL no RUM Classic]
(https://docs.dynatrace.com/docs/observe/digital-experience/session-segmentation/custom-queries-segmentation-and-aggregation-of-session-data).

A issue #355 continua pendente para correlacionar dados físicos com
aplicação/URL/dispositivo e janela de AUD real. Não alegar essa validação
somente com fakes HTTP ou query agregada.

### Extrapolação e contagens USQL não equivalentes a censo

A documentação oficial do endpoint `/table` registra
`extrapolationLevel`: nível `4`, por exemplo, indica extrapolação de
dados capturados em apenas um quarto da população. O adaptador agora
exibe `usql_extrapolation_level` quando informado e
`usql_reported_counts_extrapolated=true` se for maior que um.
Campo ausente -> `null` (N/D), **nunca** significa contagem bruta
homologada; `raw_rum_action_census_verified=false` em todos os casos.
Valores inválidos ou sem tipo numérico inteiro resultam em erro
fail-closed. Por isso, as `action_counts` são quantidades reportadas
pela API, não volume físico comprovado de eventos de um mesmo browser.
Fonte: https://docs.dynatrace.com/docs/dynatrace-api/environment-api/rum/user-sessions/table


## Local JSON review input guard (13/10/2026)

The offline `dynatrace-apdex-review` command now applies the same
strict evidence boundary as the offline Settings/RUM comparison.
Both `--settings-json` and `--effective-values-json` require a
regular file of at most 1 MiB, complete byte-level reading at unchanged
initial/final size, valid UTF-8, no duplicate JSON keys at any depth
and no Python-specific `NaN` or `Infinity` constants. A malformed
file fails before generating any architecture or threshold advice.
Synthetic M23/M25, live Dynatrace requests, persisted AUD/CONS data
and score computation are not involved. Eight isolated fixture cases
cover both input modes and physical short/extra reads.


## Guia KPM contextual por arquitetura, sem defaults numericos (13/10/2026)

A saida `analyst_guidance_pt_br.revisao_de_perfis_por_arquitetura`
apresenta os tipos de acao que merecem exame na configuracao RUM
declarada. Um site CSR_SPA, HYDRATED ou MIXED preserva o perfil
Load da navegacao inicial e acrescenta revisao de XHR quando a
transicao client-side e seu gatilho async foram informados. Se a
transicao nao tem gatilho async comprovado, o guia pede confirmar
XHR/Fetch ou instrumentacao Custom antes de selecionar KPM. SSR
com navegacao de documento nao recebe por padrao perfil XHR.
Um perfil Custom aparece quando ha configuracao Custom declarada;
arquitetura UNKNOWN nao recebe recomendacao.

Cada perfil informa KPM configurada (quando declarada e valida)
e as opcoes enumeradas pelo contrato Dynatrace para o tipo de acao.
`prescribed_kpm` e limiares numericos permanecem N/D:
nao existe um limite universal de tolerancia/frustracao determinado
apenas pela arquitetura, nem esta leitura substitui Settings API,
RUM live, URL/device/janela reais, objetivo de experiencia ou
interacao explicitamente instrumentada. A falta de um perfil XHR
na fonte nao comprova que a captura esteja desabilitada.

A saida e somente consultiva. Nenhum parametro e aplicado ao
Dynatrace, M23/M25 Synthetic, score ou banco AUD/CONS. Tests offline
cobrem SPA, SSR, mixed, hydrated, Custom e arquitetura desconhecida.


## Projeção de referência na página CAT-07 (13/10/2026)

`cat-07.html`, por meio do aconselhamento arquitetural read-only,
passa a trazer uma seção expansível **Referência de KPMs Dynatrace RUM
por tipo de ação (não aplicada)** quando a arquitetura única é
identificada na captura M6 da AUD. O menu mostra os enums aceitos pelo
fornecedor para Load, XHR e Custom, consumindo o contrato determinístico
`KPM_BY_ACTION` já utilizado pelo advisory #355, sem defaults de métricas
ou limites numéricos.

Para CSR_SPA, HYDRATED e MIXED, Load é avaliado no carregamento inicial;
XHR é somente **candidato à investigação** caso soft navigation e
instrumentação XHR/Fetch sejam efetivamente comprovadas. Para
STATIC_OR_SSR, XHR não é presumido. Custom pressupõe instrumentação
explicitamente comprovada. `UNKNOWN` resulta em orientação N/D, sem
tabela de seleção contextual. O relatório não acessa o tenant nem afirma
que uma KPM ou população real foi observada: configuração vigente,
thresholds e fallback Dynatrace permanecem **N/D**.

A nova projeção é independente dos valores Synthetic M23/M25,
não modifica AUD, score, configuração ou chamadas de rede.
As fixtures abrangem as quatro arquiteturas conhecidas e UNKNOWN,
verificam que a lista de KPMs não vira uma prescrição e que
os bytes `audit.db` permanecem idênticos após renderização.
A validação live/autorizada, URL/device/janela e população RUM
continua pendente no gate humano da issue.

## Rastreabilidade da consulta live na orientação humana (#355)

A redação `Valores efetivos consultados no tenant` só é utilizada na
projeção em português quando o comando de leitura registra
**conjuntamente** os campos de escopo/transport:
`settings_provenance=LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES`,
`input_source=AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES`,
`scope_provenance=AUTHENTICATED_SETTINGS_API_SCOPE_NOT_RUM_EVENTS`,
`actual_dynatrace_tenant_consulted=true` e
`dynatrace_provider_requests=1` (inteiro, não booleano).

O objeto de resultado do advisory também pode ser instanciado a
partir de um JSON fornecido pelo operador. Portanto a mera presença
do texto `LIVE_DYNATRACE_SETTINGS_API_EFFECTIVE_VALUES` **não**
atesta uma consulta. Se o conjunto de campos estiver incompleto,
o texto permanece `Configuração fornecida pelo operador, não
verificada no tenant`, sem fingir que HTTP ou RUM foi observado.

A CLI agora insere o fato da consulta e contagem **antes** de compor
a mensagem humana. Mesmo com consulta real, Settings API apresenta
configuração do tenant, não prova população de ações Load/XHR/Custom,
mesma página/dispositivo/janela, scores nem renderização final.
Testes isolados exercitam combinações inconsistentes e o caminho
positivo, sem rede ou credenciais.


## Gate fisico de export offline em arquivo (#355, 13/10/2026)

O CLI `dynatrace-apdex-review` agora compara identidade, tamanho,
modificacao e alteracao do arquivo antes da abertura, durante a leitura
pelo descriptor real e apos encerrar a leitura. O gate abrange
`st_dev`, `st_ino`, `st_size`, `st_mtime_ns` e `st_ctime_ns`,
alem da quantidade de bytes realmente lida e do limite de 1 MiB.
Uma substituicao atomica ou regravacao in-place com **mesmo comprimento**
nao pode mais passar como a fonte original apenas porque `st_size`
coincide. Uma leitura cujo stream nao permite inspecao fisica tambem
deve falhar de forma conservadora.

Isso nao autentica um tenant Dynatrace, nao comprova consentimento,
nao e assinatura digital do export e nao atesta que os parametros
estavam ativos na mesma janela da observacao de arquitetura.
Os fatos de RUM e seus limiares permanecem somente declarativos
quando o arquivo e fornecido offline. Testes isolados simulam
substituicao atomica e alteracao in-place sem mudanca de tamanho;
nao fazem chamadas Dynatrace, M23/M25, escrita em AUD ou scoring.


## Completude declarada do HTTP Settings API live (#355, 13/10/2026)

A chamada opt-in `read_live_dynatrace_apdex_settings` limita
a resposta HTTP da Settings API a 1 MiB e valida JSON, schema
e aplicacao selecionada. Quando o servidor fornece
`Content-Length`, o adapter agora verifica o formato decimal
estrito e o teto **antes de ler o corpo**, comparando depois
o numero declarado de bytes com a quantidade efetivamente
recebida. Conteudo completo e JSON parseavel, porem menor
do que o comprimento anunciado, nao pode ser publicado como
configuracao Dynatrace autenticada. Cabecalho ambiguo ou
nao numerico tambem interrompe a interpretacao. Sem
`Content-Length`, o limite e as demais verificacoes seguem
inalterados.

O controle nao dispara nova requisicao, nao pagina e nao
consulta eventos RUM; o tenant e as credenciais nao aparecem
na mensagem de erro. O contrato do endpoint, consentimento
e transporte SaaS HTTPS pinado permanece o mesmo.
Testes em memoria exercitam resposta valida, cabecalho
ausente, comprimento menor/maior, excedente, malformado
e duplicado em formato de lista, confirmando ausencia
de rede comercial e de novas gravacoes. Como antes,
corpo completo nao comprova observabilidade de XHR,
acao Custom ou equivalencia com M25.


## Identidade literal do tenant Dynatrace (#355, 13/10/2026)

A validacao pre-egress do endereco SaaS agora rejeita caracteres
de controle ASCII e barra invertida **antes** de chamar
`urlsplit`. Versoes suportadas de Python podem remover TAB,
CR e LF embutidos na URL; nesse caso, um texto de tenant
ambiguo poderia ser aceito como o nome HTTPS canonico
apos normalizacao silenciosa. O adaptador passa a exigir
origem literal sem controles, preservando as restricoes
existentes de host `.live.dynatrace.com`, HTTPS, sem
credenciais inline, porta customizada, path ou fragmento.

Testes sem DNS/TCP ou tenant real rejeitam controles
embutidos em posicoes internas de host, inclusive
TAB/CR/LF, NUL, DEL e backslash. Erros nao incluem
token, tenant de origem ou cabecalho Authorization.
Essa protecao nao habilita requests por conta propria
nem altera metricas, engine, AUD ou configuracao
Dynatrace persistida.


## Ajuste cross-platform do gate fisico do export (#355)

A CI Windows do comparador offline revelou que o `st_ctime_ns`
de `os.fstat` e `Path.stat` pode divergir no mesmo arquivo
que nao sofreu escrita, pois no Windows representa
creation time e nao tem a mesma semantica do POSIX.
O leitor agora compara nesses dois momentos
`st_dev`, `st_ino`, `st_size` e `st_mtime_ns`
em todas as plataformas; `st_ctime_ns` continua sendo
verificado adicionalmente apenas em sistemas POSIX.

A protecao contra swap de arquivo, truncamento e
regravacao de igual comprimento continua exercitada
pelos testes fisicos; o gate nao presume que metadados
de arquivo substituam assinatura criptografica
ou provem legitimidade do tenant.
