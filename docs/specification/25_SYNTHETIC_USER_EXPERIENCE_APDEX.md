# Synthetic User Experience Apdex calibrável

**Estado:** INTEGRADO / VIGENTE  
**Escopo:** Web Performance sintética, telemetria de ação de usuário e comparabilidade metodológica com RUM/APM.  
**Não altera:** `BR-GEO-*`, `SARI-001`, `SCORE-GEO-004`, Coverage, Confidence, Consolidation, findings ou recomendações GEO.

## 1. Objetivo

Synthetic User Experience Apdex é um domínio aditivo e separado de Synthetic Navigation Apdex. Mede uma `SYNTHETIC_LOAD_ACTION` controlada e permite calibração explícita ou importada.

É proibido descrevê-lo como RUM. Também é proibido rotular uma aproximação como métrica Dynatrace equivalente quando não existe equivalência técnica suficiente.

## 2. Relação com Synthetic Navigation Apdex

```text
Synthetic Navigation Apdex
Task       = NAVIGATION_LOAD
Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T ou erro qualificável da navegação
```

```text
Synthetic User Experience Apdex
Task       = SYNTHETIC_LOAD_ACTION
KPM        = configurável/importada
Satisfied  < threshold_satisfied
Tolerating >= threshold_satisfied e <= threshold_frustrated
Frustrated > threshold_frustrated ou erro qualificável quando policy=ON
```

Fórmula:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

Os dois domínios possuem persistência, população, thresholds e relatórios independentes.

## 3. Configuração padrão

| Parâmetro / variável | Default efetivo | Valores permitidos | Origem |
|---|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | booleano | RASAi |
| `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | KPM temporal suportada | fallback executável compatível com referência Dynatrace |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3.0` | número finito `> 0` | referência/fallback Load Action |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12.0` | número finito `> satisfied` | referência/fallback Load Action |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | booleano | RASAi |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | `navigation`, `first-party`, `all` | política RASAi; sem enum Dynatrace 1:1 |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | inteiro `>= 1` | RASAi |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 × samples)` | inteiro `>= samples` | RASAi |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | normalmente `1` | inteiro `>= 0`; `0=todas` | RASAi |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | percentuais não negativos somando `100` | RASAi |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | `cold`, `warm` | RASAi |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5.0` | número finito `> 0` | RASAi |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | normalmente `1.0` | número finito `>= 0` | RASAi |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | normalmente `1` | `1`, `2` | RASAi |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | booleano | RASAi |
| `RASAI_DYNATRACE_BASE_URL` | sem default | URL HTTPS válida | integração Dynatrace |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | texto válido | integração Dynatrace |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | caminho para JSON válido | integração Dynatrace |
| `DYNATRACE_API_TOKEN` | sem default | secret válido | integração Dynatrace |

Precedência geral:

```text
CLI explícito > variável de ambiente > default do runtime
```

A importação Dynatrace válida substitui KPM/thresholds conforme o contrato importado e registra a origem.

## 4. KPM e fallback

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

`VISUALLY_COMPLETE`, `SPEED_INDEX`, `CUMULATIVE_LAYOUT_SHIFT` e `FIRST_INPUT_DELAY` podem aparecer em configuração externa, mas não podem ser substituídos silenciosamente quando não houver equivalência técnica suficiente.

Se a configuração Dynatrace solicitar KPM não mensurável e fornecer fallback thresholds válidos:

```text
requested_kpm = KPM original
effective_kpm = USER_ACTION_DURATION
thresholds    = fallback thresholds importados
source        = origem importada + fallback explícito de capacidade
```

Sem fallback utilizável, Experience falha de forma fail-open e não altera o audit core.

## 5. Envelope de Load Action sintética

Cada amostra observa, conforme disponibilidade:

1. navegação iniciada imediatamente antes de `page.goto`;
2. Chromium até o evento `load`;
3. Navigation Timing, incluindo `loadEventEnd`;
4. XHR/fetch;
5. recursos tardios dentro da janela limitada;
6. request failures;
7. HTTP `>= 400`;
8. JavaScript runtime errors;
9. `console.error`;
10. LCP e CLS quando observáveis;
11. atividade pós-load para telemetria até o limite `settle`.

### 5.1 USER_ACTION_DURATION

Para Load Action sintética:

```text
actionStart = navigationStart
loadBoundary = loadEventEnd
userActionEnd = max(loadBoundary, término do último XHR/fetch iniciado antes de loadEventEnd)
USER_ACTION_DURATION = userActionEnd - actionStart
```

Se Navigation Timing não fornecer `loadEventEnd`, o runtime usa fallback rastreável a partir da duração de navegação/retorno do `page.goto`.

A janela `settle` serve para **observação**, não para somar artificialmente tempo. Requests iniciados após `loadEventEnd` podem ser registrados como atividade tardia, mas não ampliam sozinhos `USER_ACTION_DURATION`.

A implementação não declara reproduzir integralmente o mecanismo proprietário Dynatrace de correlação de recursos dinâmicos e scripts.

## 6. Load, XHR e Custom Action

```text
Load Action    = EXECUTÁVEL
XHR Action     = XHR/fetch observado dentro do Load; não autônomo
Custom Action  = NÃO EXECUTÁVEL sem roteiro/clickpath explícito
```

Standalone XHR/Custom exigem scripted journeys que definam interação, início/fim e correlação dos requests.

## 7. Thresholds

Experience não aplica automaticamente `4T`.

Sem customização/importação:

```text
Satisfied  < 3.0 s
Tolerating >= 3.0 s e <= 12.0 s
Frustrated > 12.0 s
```

Overrides devem respeitar:

```text
satisfied > 0
frustrated > satisfied
```

Valores importados em milissegundos são convertidos explicitamente para segundos.

## 8. Política de erros

`errors_affect_apdex=true` permite que uma ação rápida seja `FRUSTRATED` quando existe erro qualificável.

Escopos:

- `navigation`: somente falha do documento/navegação qualifica por política;
- `first-party`: JavaScript runtime errors e `console.error` são globais; request/HTTP errors qualificam apenas no host da aplicação;
- `all`: JavaScript runtime errors e `console.error` continuam globais; request/HTTP errors de terceiros também podem qualificar.

Regras mínimas:

- timeout/navigation error -> `FRUSTRATED` quando o perfil foi aplicado;
- HTTP `>= 400` do documento principal -> application error;
- JavaScript runtime error pode forçar `FRUSTRATED` conforme policy;
- `console.error` pode forçar `FRUSTRATED` conforme policy nos escopos `first-party` e `all`;
- request/HTTP errors respeitam `navigation|first-party|all`;
- falha da ferramenta/perfil fica fora do denominador.

`console.error` é extensão de política RASAi, não equivalência declarada ao Dynatrace. Dynatrace possui regras de request error mais granulares, com filtros e `impactApdex`; o runtime não deve representar o enum RASAi como contrato idêntico ao fornecedor.

## 9. Dispositivos, perfis e sessão

Mix default:

```text
mobile=60,desktop=35,tablet=5
```

Esse valor não é default Dynatrace. Para comparação com uma aplicação específica, deve-se usar distribuição real observada quando conhecida.

`cold`:

- novo BrowserContext por amostra;
- cache desabilitado;
- sem cookies/storage entre amostras.

`warm` reutiliza contexto por worker/perfil. Perfis CPU/rede são sintéticos, controlados e versionados.

## 10. Amostragem e carga

Default operacional:

```text
100 amostras válidas totais por página
max attempts = ceil(1.25 × samples)
```

Grupos menores são diagnósticos. Uma amostra é uma navegação com múltiplos subrequests. Carga relevante contra produção exige autorização e avaliação de capacidade.

## 11. Importação Dynatrace

A importação pode usar:

1. JSON exportado - preferido para reprodutibilidade;
2. Configuration API - leitura live.

Persistir somente dados sanitizados necessários:

- KPM solicitada e efetiva;
- thresholds primários e fallback;
- contrato Load/XHR/Custom quando presente;
- indicador/política de erros quando observável;
- resumo de error rules;
- ocorrência/motivo de fallback.

Payload integral e `DYNATRACE_API_TOKEN` não são persistidos em CLI serializada, SQLite, HTML, logs ou configuração.

## 12. Persistência

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

A execução persiste configuração efetiva, contrato de medição e ambiente suficiente para proveniência. Synthetic Navigation Apdex permanece separado.

## 13. Relatório

`report/apdex-experience.html` deve expor:

- fronteira Synthetic vs RUM;
- KPM efetiva;
- thresholds efetivos;
- fallback, quando houver;
- policy/escopo de erros;
- regra efetiva de `USER_ACTION_DURATION`;
- papel de `settle` como observação;
- JavaScript runtime errors e `console.error` conforme policy;
- origem da calibração;
- parâmetros com `Efetivo`, `Padrão/referência`, `Origem` e observação;
- mix, session mode, população e grupos por device;
- Satisfied/Tolerating/Frustrated;
- Frustrated forçado por erro;
- p75/p90/p95/p99 quando disponíveis;
- contadores XHR/fetch/resources/errors;
- comparação com Synthetic Navigation Apdex quando houver contexto equivalente;
- referências públicas.

O HTML deve refletir o estado persistido e não pode descrever a regra anterior após mudança metodológica.

## 14. Fail-open e scoring

Falha de Experience:

- não altera `SARI-001`;
- não altera `SCORE-GEO-004`;
- não cria finding GEO;
- não muda Coverage/Confidence;
- não invalida Synthetic Navigation Apdex;
- deve ser registrada como limitação operacional.

## 15. Comparabilidade

Antes de comparar com Dynatrace RUM ou outra execução, conferir:

1. mesma URL/ação;
2. mesmo contrato metodológico;
3. KPM solicitada e efetiva;
4. thresholds e fallback;
5. política de erros;
6. período;
7. device mix;
8. sessão/cache;
9. condições CPU/rede/geografia.

Igualdade numérica não é objetivo porque RUM observa usuários reais e Experience Apdex é laboratório sintético.

## 16. Validação mínima

A regressão deve cobrir:

1. default `USER_ACTION_DURATION`, `3 s / 12 s`;
2. igualdade no limiar inferior -> `TOLERATING`;
3. igualdade no limiar superior -> `TOLERATING`;
4. `console.error` global nos escopos `first-party` e `all` quando errors affect está ativo;
5. `navigation` permanece restrito a erro de navegação/documento;
6. request pós-`loadEventEnd` pode ser observado sem estender sozinho a duração;
7. importação com KPM suportada;
8. fallback explícito de KPM não suportada;
9. `apdex.html` permanece independente;
10. relatório HTML segue o contrato efetivo;
11. token não aparece em artifacts;
12. suíte automatizada aplicável permanece verde.

## 17. Referências externas

- Apdex Technical Specification v1.1: <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>
- Dynatrace - User actions in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions>
- Dynatrace - User action metrics in RUM Classic: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-action-metrics>
- Dynatrace - Apdex configuration for load actions: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions>
- Dynatrace - Request errors: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-request-errors>
- Dynatrace - Web application configuration API: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application>
- W3C Navigation Timing / Performance Timeline
- Chrome DevTools Protocol - Network / Emulation
