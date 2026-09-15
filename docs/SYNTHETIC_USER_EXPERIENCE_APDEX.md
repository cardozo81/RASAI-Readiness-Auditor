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
| erros afetam Apdex | `true` | booleano | `true`, salvo política deliberadamente diferente | alinhamento semântico; Dynatrace pode possuir regras mais granulares |
| escopo de erro | `first-party` | `navigation`, `first-party`, `all` | `first-party` | escopo RASAi para request/HTTP errors; JavaScript runtime errors e `console.error` observados são globais quando a política de erros está ativa |
| amostras por página | `100` | inteiro `>= 1` | `100`; reduzir somente em smoke controlado | política operacional RASAi |
| máximo de tentativas | `ceil(1.25 × samples)` | inteiro `>= 1` | default derivado | política operacional RASAi |
| máximo de páginas | `1` | inteiro `>= 0`; `0=todas` | `1` | política operacional RASAi |
| mix de dispositivos | `mobile=60,desktop=35,tablet=5` | percentuais não negativos somando `100` | usar distribuição real observada quando houver | política sintética RASAi |
| modo de sessão | `cold` | `cold`, `warm` | `cold` | política sintética RASAi |
| settle | `5.0 s` | número `> 0` | `5.0 s` | janela de observação pós-load; não é somada automaticamente à duração |
| delay | `1.0 s` | número `>= 0` | `1.0 s` ou maior conforme capacidade do alvo | política de carga RASAi |
| concorrência | `1` | `1`, `2` | `1` | política de carga RASAi |

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

A política separa **runtime errors** de **request/HTTP errors**.

- `navigation`: somente falha do documento/navegação qualifica por política;
- `first-party`: JavaScript runtime errors (`pageerror`) e `console.error` observados são globais; request/HTTP errors qualificam apenas quando pertencem ao host da aplicação;
- `all`: runtime errors continuam globais e request/HTTP errors de terceiros também podem qualificar.

Com `errors_affect_apdex=true`, JavaScript runtime error ou `console.error` pode forçar uma ação rápida para `FRUSTRATED` nos escopos `first-party` e `all`. `console.error` é uma **extensão de política RASAi**; não é apresentado como equivalência 1:1 ao Dynatrace.

Dynatrace possui regras de request errors mais granulares, incluindo filtros e `impactApdex`. Portanto, `navigation/first-party/all` é uma política RASAi e não um enum do fornecedor.

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
| JavaScript runtime errors | sim | observados globalmente |
| `console.error` | extensão RASAi | observado globalmente e pode afetar Apdex conforme policy |
| request/HTTP errors | parcial | política sintética simplificada; fornecedor possui regras mais granulares |
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

## 8. Persistência e rastreabilidade

Tabelas:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

A fórmula permanece:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

A execução persiste configuração efetiva, contrato de medição, ambiente de browser e versão metodológica interna suficientes para rastreabilidade. Synthetic Navigation Apdex permanece em persistência separada.

## 9. Relatório HTML

`report/apdex-experience.html` deve refletir exatamente a execução persistida e apresentar:

- KPM efetiva e thresholds;
- origem da calibração e fallback, quando aplicável;
- política e escopo de erros;
- regra de `USER_ACTION_DURATION`;
- indicação de que `settle` é janela de observação e não acréscimo automático de duração;
- `console.error` como erro global quando a política de erros está ativa;
- Satisfied/Tolerating/Frustrated e Frustrated forçado por erro;
- p75/p90/p95/p99 quando disponíveis;
- contadores XHR/fetch, recursos tardios e erros;
- mix, session mode e grupos por device;
- comparação com Synthetic Navigation Apdex quando houver contexto equivalente;
- referências públicas.

Nenhuma página HTML deve afirmar uma regra diferente da executada pelo runtime.

## 10. Smoke humano recomendado

Use URL autorizada e baixo volume. Grupo com menos de 100 amostras é diagnóstico, não baseline estatístico final.

Verificações mínimas:

1. `apdex.html` permanece independente e baseado em `T/4T`;
2. `apdex-experience.html` é gerado quando Experience executa;
3. KPM/thresholds efetivos correspondem à configuração;
4. `console.error` força `FRUSTRATED` quando errors affect está ativo e o escopo não é `navigation`;
5. JavaScript runtime error segue a mesma regra;
6. request/HTTP error respeita o escopo configurado;
7. request iniciado depois de `loadEventEnd` pode ser observado durante `settle`, mas não estende sozinho `USER_ACTION_DURATION`;
8. igualdade com o limiar inferior é `TOLERATING` e igualdade com o limiar Frustrated também é `TOLERATING`;
9. token Dynatrace não aparece em artifacts;
10. Synthetic Navigation Apdex, scoring e demais domínios permanecem inalterados.

## 11. Cold/warm, amostragem e carga

`cold` é o baseline reproduzível: novo BrowserContext, cache desabilitado e sem storage reaproveitado. `warm` reutiliza contexto por worker/perfil.

O default é 100 amostras válidas totais por página. Valores maiores representam carga relevante: uma navegação gera múltiplos subrequests. Não execute carga relevante contra produção sem autorização e avaliação de capacidade.

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
