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
