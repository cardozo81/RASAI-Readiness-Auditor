# Synthetic User Experience Apdex

## 1. Finalidade

Synthetic User Experience Apdex adiciona ao RASAi uma medição sintética calibrável, separada de Synthetic Navigation Apdex.

| Domínio | Natureza | Task / população | Thresholds |
|---|---|---|---|
| Synthetic Navigation Apdex | laboratório sintético controlado | `NAVIGATION_LOAD`, por URL/dispositivo | `T` e `4T` conforme Apdex |
| Synthetic User Experience Apdex | laboratório sintético enriquecido/calibrável | `SYNTHETIC_LOAD_ACTION`, mix explícito de dispositivos | limites Satisfied/Frustrated independentes, com baseline compatível com referências Dynatrace ou importação |
| Dynatrace RUM | usuários reais | Load/XHR/Custom actions observadas no período | configuração efetiva da aplicação/ação |

Synthetic User Experience Apdex **não é RUM**. O objetivo é reduzir diferenças metodológicas controláveis - KPM, thresholds, política de erros, sessão e mix de dispositivos - sem manipular o score para coincidir com Dynatrace.

Mudanças da fronteira de medição são versionadas internamente e persistidas junto ao ambiente de execução. Resultados gerados por contratos metodológicos diferentes não devem ser tratados como diretamente equivalentes em comparação longitudinal.

## 2. Baseline padrão compatível com referências Dynatrace

Quando `--apdex-experience` é habilitado e o usuário não fornece calibração própria nem importa configuração Dynatrace, o runtime resolve:

| Parâmetro | Default efetivo | Valores permitidos | Recomendado | Origem |
|---|---|---|---|---|
| KPM | `USER_ACTION_DURATION` | KPM temporal suportada pelo runtime | default quando não houver importação | fallback executável compatível com a regra pública Dynatrace; não é a KPM primária do fornecedor |
| Satisfied | `3.0 s` | número `> 0` | `3.0 s` no baseline compatível | referência/fallback Load Action |
| Frustrated | `12.0 s` | número `> Satisfied` | `12.0 s` no baseline compatível | referência/fallback Load Action |
| erros afetam Apdex | `true` | booleano | `true` | default Dynatrace: erros elegíveis podem tornar a ação Frustrated |
| erros JavaScript afetam Apdex | `true` | booleano | `true` | default Dynatrace; exceções JavaScript são erros da ação, salvo exclusão |
| erros de requisição afetam Apdex | `true` | booleano | `true` | default Dynatrace; inclui request failures, HTTP 4xx/5xx e CSP quando capturados |
| erros de console afetam Apdex | `false` | booleano | `false` | Dynatrace não captura genericamente `console.error` por padrão; habilitar quando a aplicação usa política equivalente a `cce=1` |
| captura de erros JavaScript | `true` | booleano | `true` | default Dynatrace WebApplicationConfig |
| captura de XMLHttpRequest | `true` | booleano | `true` | default Dynatrace WebApplicationConfig |
| captura de Fetch | `true` | booleano | `true` | default Dynatrace WebApplicationConfig |
| captura de `console.error` | `false` | booleano | `false` | default Dynatrace; `cce=1` é opt-in |
| máximo de erros detalhados | `10` | inteiro `0..50` | `10` | referência Dynatrace `maxErrorsToCapture=10`; limita evidência detalhada por amostra/página carregada, sem truncar contadores agregados |
| escopo de erro de requisição | `all` | `navigation`, `first-party`, `all` | `all` | `all` aproxima a cobertura default Dynatrace; os demais escopos são políticas RASAi deliberadas |
| amostras por página | `100` | inteiro `>= 1` | `100`; reduzir somente em smoke controlado | política operacional RASAi |
| máximo de tentativas | `ceil(1.25 × samples)` | inteiro `>= 1` | default derivado | política operacional RASAi |
| máximo de páginas | `1` | inteiro `>= 0`; `0=todas` | `1` | política operacional RASAi |
| mix de dispositivos | `mobile=60,desktop=35,tablet=5` | percentuais não negativos somando `100` | usar distribuição real observada quando houver | política sintética RASAi |
| modo de sessão | `cold` | `cold`, `warm` | `cold` | política sintética RASAi |
| settle | `5.0 s` | número `> 0` | `5.0 s` | janela de observação pós-load; não é somada automaticamente à duração |
| delay | `1.0 s` | número `>= 0` | `1.0 s` ou maior conforme capacidade do alvo | política de carga RASAi |
| concorrência | `1` | inteiro `1..3` | `1`; `3` é avançado e exige delay >= `1 s` | política de carga RASAi |

A classificação temporal segue:

```text
valor < limiar Satisfied                         -> SATISFIED
limiar Satisfied <= valor <= limiar Frustrated  -> TOLERATING
valor > limiar Frustrated                        -> FRUSTRATED
```

Um erro qualificável pode forçar `FRUSTRATED` independentemente da duração quando a política de erros efetiva estiver habilitada. Synthetic Navigation Apdex permanece separado e continua usando `T/4T`.

## 3. Fronteira temporal de USER_ACTION_DURATION

Para Load Action, a documentação Dynatrace define o início em `navigationStart`. O término usa `loadEventEnd` ou, quando uma requisição XHR associada à ação permanece ativa depois do `loadEventEnd`, o término da última requisição correlacionada.

O RASAi aplica uma aproximação sintética explícita:

```text
actionStart = navigationStart
loadBoundary = loadEventEnd
userActionEnd = max(loadBoundary, término do último XHR/fetch iniciado antes do loadEventEnd)
USER_ACTION_DURATION = userActionEnd - actionStart
```

Requests iniciados **depois** do `loadEventEnd` continuam observáveis durante `settle`, inclusive para telemetria de erros e recursos tardios, mas não estendem automaticamente `USER_ACTION_DURATION`. Isso evita incorporar ao tempo da Load Action qualquer analytics, beacon, polling ou tráfego tardio apenas porque terminou dentro da janela de observação.

A documentação Dynatrace também descreve recursos dinâmicos e execução de scripts associados à ação. O RASAi não declara equivalência integral do mecanismo proprietário de correlação do fornecedor; a regra acima é o contrato sintético reproduzível efetivamente executado.

Fontes oficiais:

- Dynatrace - User actions in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions>
- Dynatrace - User action metrics in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-action-metrics>

## 4. KPM e fallback

O RASAi não implementa Dynatrace Visually Complete com equivalência de fornecedor.

KPMs temporais diretamente mensuráveis:

```text
USER_ACTION_DURATION
DOM_INTERACTIVE
LOAD_EVENT_START
LOAD_EVENT_END
RESPONSE_START
RESPONSE_END
LARGEST_CONTENTFUL_PAINT
```

Ao importar configuração Dynatrace:

1. a KPM originalmente solicitada é registrada;
2. se for diretamente mensurável, os thresholds primários são usados;
3. se não for mensurável com equivalência suficiente e houver fallback válido, `USER_ACTION_DURATION` é usado explicitamente com os fallback thresholds;
4. a substituição aparece na proveniência e no relatório;
5. sem fallback utilizável, Experience falha de forma fail-open e não altera o audit principal.

Não existe fallback silencioso.

## 5. Política de erros

A política separa **coleta** de **impacto no Apdex**. O limite `max_error_details` controla somente a quantidade de eventos detalhados persistidos por amostra/página carregada; contadores agregados de JavaScript/request/HTTP/CSP não são truncados por esse limite. O RASAi pode observar um evento e mantê-lo como evidência sem necessariamente torná-lo Frustrated.

Defaults efetivos alinhados ao Dynatrace RUM Web:

- `errors_affect_apdex=true`: chave mestra;
- `javascript_errors_affect_apdex=true`: `pageerror`/exceção JavaScript da ação pode forçar `FRUSTRATED`;
- `request_errors_affect_apdex=true`: erros de requisição qualificáveis, HTTP `4xx/5xx`, failed images e CSP violations podem forçar `FRUSTRATED`; `net::ERR_ABORTED` genérico de subrecurso permanece evidência diagnóstica por default porque não é equivalência automática de um request error Dynatrace;
- `console_errors_affect_apdex=false`: `console.error` é capturado pelo RASAi quando a captura estiver habilitada; por default permanece desligado e só afeta o Apdex quando captura e impacto forem explicitamente habilitados;
- `error_scope=all`: o escopo controla apenas a família de request/HTTP/CSP errors. JavaScript runtime errors não deixam de ser erros da ação por serem first/third-party.

Escopos de request error:

- `navigation`: somente erro do documento/navegação principal;
- `first-party`: request/HTTP/CSP de recursos próprios;
- `all`: recursos próprios e terceiros.

Failed image requests são reconhecidos dentro de `requestfailed` e materializados como evidência. CSP violations são observadas via evento `securitypolicyviolation`.

Ao importar configuração Dynatrace, o RASAi respeita, quando presentes e diretamente reproduzíveis, os switches de inclusão/exclusão de JavaScript e request/HTTP errors. `customConfigurationProperties` com `cce=1` é reconhecido como habilitação de impacto de `console.error`. Regras públicas de request/HTTP errors importadas são normalizadas e aplicadas em ordem (primeira correspondência), incluindo códigos/faixas HTTP, filtro de URL, CSP/blocked request, failed image quando presente, `capture` e `impactApdex`. Custom Errors acionados pela API da aplicação permanecem limitação explícita quando o RASAi não possui o evento equivalente.

Além dos contadores, o runtime persiste evidência individual limitada dos eventos observados por amostra: falhas de request, respostas HTTP `>=400`, `console.error` e erros JavaScript. Quando disponíveis, são mantidos URL/fonte, first-party/third-party, tipo de recurso, status HTTP e mensagem técnica. Response bodies, cookies e secrets não são capturados por esta camada.

Esses eventos alimentam também a correlação determinística de remediações descrita em [REQUEST_REMEDIATION_INTELLIGENCE.md](REQUEST_REMEDIATION_INTELLIGENCE.md). O agrupamento não altera a política de erro nem a classificação Apdex: ele apenas organiza a mesma evidência por padrão recorrente e solução possível.

Fontes oficiais:

- Dynatrace - Request errors: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-request-errors>
- Dynatrace - Error rules: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/error-rules/get-configuration>

## 6. Cobertura do contrato Dynatrace

| Contrato | RASAi | Situação |
|---|---|---|
| Load Action thresholds | sim | executável |
| `USER_ACTION_DURATION` | sim | executável com fronteira temporal explícita |
| `VISUALLY_COMPLETE` | parcial | importável; usa fallback quando válido; sem alegação de equivalência |
| LCP, DOM Interactive, Load Event, Response Start/End | sim | KPMs temporais suportadas |
| XHR Action autônoma | não | XHR/fetch é observado dentro da Load Action |
| Custom Action | não | exige roteiro/clickpath explícito |
| Custom Errors da API Dynatrace | parcial | configuração pode ser registrada; o evento só é classificável quando existir evidência equivalente observável no navegador/aplicação |
| JavaScript runtime errors | sim | observados globalmente |
| `console.error` | extensão RASAi | observado globalmente; default não impacta Apdex; pode acompanhar `cce=1` importado/configuração explícita |
| CSP violations | sim | observadas e tratadas como request error quando a política de request errors está ativa |
| failed image requests | sim | reconhecidas dentro de request failures e persistidas como evidência |
| request/HTTP errors | amplo | 4xx/5xx/requestfailed/CSP/failed-image cobertos; regras públicas ordenadas de captura/impacto e filtros HTTP/URL são aplicadas quando importadas |
| população real de devices/redes/sessões | não | perfis sintéticos controlados |

## 7. Configuração e console interativo

Variáveis de Experience:

```text
RASAI_APDEX_EXPERIENCE
RASAI_APDEX_EXPERIENCE_SAMPLES
RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS
RASAI_APDEX_EXPERIENCE_MAX_PAGES
RASAI_APDEX_EXPERIENCE_DEVICE_MIX
RASAI_APDEX_EXPERIENCE_SESSION_MODE
RASAI_APDEX_EXPERIENCE_KPM
RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS
RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS
RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT
RASAI_APDEX_EXPERIENCE_JAVASCRIPT_ERRORS_AFFECT
RASAI_APDEX_EXPERIENCE_REQUEST_ERRORS_AFFECT
RASAI_APDEX_EXPERIENCE_CONSOLE_ERRORS_AFFECT
RASAI_APDEX_EXPERIENCE_JAVASCRIPT_ERROR_CAPTURE
RASAI_APDEX_EXPERIENCE_XHR_CAPTURE
RASAI_APDEX_EXPERIENCE_FETCH_CAPTURE
RASAI_APDEX_EXPERIENCE_CONSOLE_ERROR_CAPTURE
RASAI_APDEX_EXPERIENCE_MAX_ERROR_DETAILS
RASAI_APDEX_EXPERIENCE_ERROR_SCOPE
RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS
RASAI_APDEX_EXPERIENCE_DELAY_SECONDS
RASAI_APDEX_EXPERIENCE_CONCURRENCY
RASAI_APDEX_DYNATRACE_IMPORT
RASAI_DYNATRACE_BASE_URL
RASAI_DYNATRACE_APPLICATION_ID
RASAI_DYNATRACE_CONFIG_JSON
DYNATRACE_API_TOKEN
```

O console deve mostrar default, valor efetivo, origem e domínio permitido. Secrets aparecem somente como estado de configuração. `DYNATRACE_API_TOKEN` nunca é persistido em INI, SQLite, HTML, logs ou argumentos serializados.

Os perfis de cliente/hardware/rede são compartilhados com Synthetic Navigation Apdex e usam as mesmas nove variáveis `RASAI_APDEX_{MOBILE|DESKTOP|TABLET}_{CLIENT|HARDWARE|NETWORK}_PROFILE`. O fluxo de configuração do Experience mostra os perfis efetivos por device, permite editá-los com o mesmo catálogo e mantém a precedência **ação/CLI > ambiente > rasai-console.ini > defaults controlados**. Alterar perfil muda a condição de laboratório das medições futuras de Navigation e Experience; não muda a fórmula Apdex.

A concorrência do Experience permanece própria em `RASAI_APDEX_EXPERIENCE_CONCURRENCY`. Concorrência e perfis podem alterar os valores medidos por contenção local, carga simultânea, viewport, CPU relativa e envelope de rede, portanto fazem parte do contexto metodológico da execução.

## 8. Persistência e rastreabilidade

Tabelas principais:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
synthetic_ux_apdex_error_details
```

`synthetic_ux_apdex_error_details` é evidência diagnóstica subordinada à amostra. As tabelas `request_remediation_*` são uma projeção aditiva para agrupamento/solução e não substituem essa evidência de origem.

A fórmula permanece:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

A execução persiste configuração efetiva, contrato de medição, ambiente de browser e versão metodológica interna suficientes para rastreabilidade. Isso inclui concorrência, delay, device mix, sessão e os IDs efetivos de cliente/hardware/rede por device.

No reprocessamento, os perfis e a concorrência vêm da configuração congelada da própria AUD. O RPR não pode adotar silenciosamente presets atuais do INI, ambiente do operador ou worker. Para AUD legado sem `runtime_profiles`, o runtime tenta recuperar a identidade pelo `profile_id` já persistido nas amostras; somente na ausência dessa evidência usa o default histórico do catálogo e registra provenance operacional explícita. Synthetic Navigation Apdex permanece em persistência separada.

## 9. Relatório HTML

`report-catalog/cat-07.html` deve refletir exatamente a execução persistida e apresentar:

- KPM efetiva e thresholds;
- origem da calibração e fallback, quando aplicável;
- política e escopo de erros;
- regra de `USER_ACTION_DURATION`;
- indicação de que `settle` é janela de observação e não acréscimo automático de duração;
- `console.error` como erro global quando a política de erros está ativa;
- Satisfied/Tolerating/Frustrated e Frustrated forçado por erro;
- p75/p90/p95/p99 quando disponíveis;
- contadores XHR/fetch, recursos tardios e erros;
- eventos individuais com URL/status/tipo/mensagem quando coletados;
- padrões de erro agrupados entre amostras, com `N/Y`, percentual e frequência recorrente/intermitente/ocasional;
- mix, session mode e grupos por device;
- comparação com Synthetic Navigation Apdex quando houver contexto equivalente;
- referências públicas.

Os rótulos de recorrência descrevem frequência e não são usados isoladamente para afirmar causa estrutural. O detalhamento de solução fica no CAT-09; o CAT-07 permanece a projeção de observação/evidência.

Nenhuma página HTML deve afirmar uma regra diferente da executada pelo runtime.

## 10. Smoke humano recomendado

Use URL autorizada e baixo volume. Grupo com menos de 100 amostras é diagnóstico, não baseline estatístico final.

Verificações mínimas:

1. `cat-06.html` permanece independente e baseado em `T/4T`;
2. `cat-07.html` é gerado quando Experience executa;
3. KPM/thresholds efetivos correspondem à configuração;
4. JavaScript runtime error força `FRUSTRATED` por default;
5. request/HTTP/CSP error força `FRUSTRATED` por default e respeita o escopo de request configurado;
6. `console.error` permanece diagnóstico por default e só força `FRUSTRATED` quando sua política específica está habilitada;
7. o agrupamento de recorrência não altera classificação, score ou a evidência individual e a solução correspondente aparece no CAT-09 sem criar uma recomendação por ocorrência;
8. request iniciado depois de `loadEventEnd` pode ser observado durante `settle`, mas não estende sozinho `USER_ACTION_DURATION`;
9. igualdade com o limiar inferior é `TOLERATING` e igualdade com o limiar Frustrated também é `TOLERATING`;
10. token Dynatrace não aparece em artifacts;
11. Synthetic Navigation Apdex, scoring e demais domínios permanecem inalterados.

## 11. Cold/warm, amostragem e carga

`cold` é o baseline reproduzível: novo BrowserContext, cache desabilitado e sem storage reaproveitado. `warm` reutiliza contexto por worker/perfil.

O default é 100 amostras válidas totais por página. Valores maiores representam carga relevante: uma navegação gera múltiplos subrequests. Não execute carga relevante contra produção sem autorização e avaliação de capacidade.

A concorrência do Experience é limitada a `1..3`: `1` é recomendado, `2` é moderado e `3` é avançado/alto. O valor `3` exige `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS >= 1` e deve ser configurado explicitamente; quando não existe override próprio, a herança vinda do Navigation fica limitada a `2`. O scheduler limita os trabalhos em voo às amostras válidas ainda necessárias, evitando user actions físicas excedentes não representadas pela população persistida. Como cada worker inclui observação pós-load, concorrência elevada pode aumentar contenção local, pressão sobre o alvo, bloqueios e auto-interferência na medição.

## 12. Comparabilidade com Dynatrace RUM

Antes de interpretar diferenças, confira:

- mesma URL/ação;
- mesmo contrato metodológico;
- KPM solicitada e efetiva;
- thresholds e fallback;
- política de erros;
- período Dynatrace;
- device mix;
- cold/warm;
- perfis de CPU/rede e geografia.

Mesmo com fatores controláveis alinhados, igualdade numérica não é esperada porque RUM observa usuários reais e Synthetic User Experience Apdex é laboratório sintético.

## 13. Referências

- Apdex Technical Specification v1.1: <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>
- Dynatrace - User actions in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions>
- Dynatrace - User action metrics in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-action-metrics>
- Dynatrace - Apdex configuration for load actions: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions>
- Dynatrace - Request errors: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-request-errors>
- Dynatrace - Web application configuration API: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application>
