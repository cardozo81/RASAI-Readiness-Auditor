# Synthetic User Experience Apdex calibrável

**Estado:** INTEGRADO; baseline Dynatrace-compatible revisado em 2026-09-10.  
**Escopo:** Web Performance sintética, user-action telemetry e comparabilidade metodológica com RUM/APM.  
**Não altera:** `BR-GEO-*`, `SARI-001`, SCORE-GEO-004, Coverage, Confidence, Consolidation, findings ou recomendações GEO.

## 1. Objetivo

Synthetic User Experience Apdex é um domínio aditivo e separado do Synthetic Navigation Apdex. Mede uma `SYNTHETIC_LOAD_ACTION` controlada e permite calibração explícita ou importada.

É proibido descrever M25 como RUM. É igualmente proibido implementar uma aproximação e rotulá-la como uma KPM Dynatrace equivalente quando essa equivalência não existe.

## 2. Relação com Synthetic Navigation Apdex

```text
Synthetic Navigation Apdex - Standard
Task       = NAVIGATION_LOAD
Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T ou erro de aplicação/navegação válido
```

```text
Synthetic User Experience Apdex
Task       = SYNTHETIC_LOAD_ACTION
KPM        = configurável/importada
Satisfied  <= threshold_satisfied
Tolerating > threshold_satisfied e <= threshold_frustrated
Frustrated > threshold_frustrated ou erro qualificável quando policy=ON
```

Fórmula:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

Os dois domínios possuem persistência e relatórios independentes.

## 3. Baseline default

Quando Experience está habilitado e não há override CLI/ambiente nem importação Dynatrace, o runtime deve resolver:

```text
kpm                            = USER_ACTION_DURATION
satisfied_threshold_seconds    = 3.0
frustrated_threshold_seconds   = 12.0
errors_affect_apdex             = true
error_scope                     = first-party
target_samples_per_page         = 100
max_attempts_per_page           = ceil(1.25 * target_samples_per_page)
max_pages                       = 1
device_mix                      = mobile=60,desktop=35,tablet=5
session_mode                    = cold
settle_seconds                  = 5.0
delay_seconds                   = 1.0
concurrency                     = 1
```

Classificação de origem:

| Parâmetro | Origem normativa |
|---|---|
| `USER_ACTION_DURATION` | fallback executável compatível com a regra de fallback Dynatrace; não é apresentado como KPM primária Dynatrace |
| 3 s / 12 s | referência/fallback de Load Action no contrato público Dynatrace usado pelo RASAi |
| `errors_affect_apdex=true` | alinhamento semântico: erro qualificável pode frustrar uma ação; regras Dynatrace podem ser mais granulares |
| `first-party` | default conservador RASAi; sem enum Dynatrace equivalente 1:1 |
| samples/max attempts/max pages/device mix/session/settle/delay/concurrency | defaults operacionais sintéticos RASAi; não devem ser atribuídos ao Dynatrace RUM |

## 4. KPM Dynatrace e viabilidade técnica

Dynatrace documenta `VISUALLY_COMPLETE` como KPM padrão para Load/XHR em documentação atual. M25 não implementa Dynatrace Visually Complete com equivalência de fornecedor.

KPMs temporais diretamente mensuráveis pelo M25:

- `USER_ACTION_DURATION`;
- `DOM_INTERACTIVE`;
- `LOAD_EVENT_START`;
- `LOAD_EVENT_END`;
- `RESPONSE_START`;
- `RESPONSE_END`;
- `LARGEST_CONTENTFUL_PAINT`.

CLS pode ser persistido como telemetria, mas não é KPM temporal de Apdex. `VISUALLY_COMPLETE`, `SPEED_INDEX`, `CUMULATIVE_LAYOUT_SHIFT` e métricas sem equivalência suficiente não podem ser substituídas silenciosamente por outra KPM.

### 4.1 Fallback importado

Se a configuração Dynatrace solicitar uma KPM não mensurável e fornecer os fallback thresholds de User Action Duration:

```text
requested_kpm = KPM Dynatrace original
effective_kpm = USER_ACTION_DURATION
thresholds    = fallback thresholds importados
source        += RASAI_CAPABILITY_FALLBACK
```

O relatório deve exibir a ocorrência do fallback.

Se os fallback thresholds necessários não existirem ou forem inválidos, a execução Experience deve falhar de forma fail-open, sem alterar o audit core.

## 5. Envelope de Load Action sintética

Cada amostra observa:

1. início antes da navegação;
2. Chromium até `load`;
3. atividade posterior ao load dentro da janela limitada;
4. XHR/fetch;
5. recursos tardios;
6. request failures;
7. HTTP >= 400;
8. JavaScript runtime errors;
9. `console.error` como telemetria;
10. Navigation Timing;
11. LCP e CLS quando observáveis;
12. fim pelo último evento real observado no envelope.

A janela de settle não é acrescentada artificialmente à duração da ação.

## 6. Load, XHR e Custom Action

A importação Dynatrace deve preservar, de forma sanitizada, os contratos disponíveis de:

- Load Action;
- XHR Action;
- Custom Action.

A execução M25 atual possui os seguintes limites:

```text
Load Action    = EXECUTÁVEL
XHR Action     = XHR/fetch observado dentro do Load; não autônomo
Custom Action  = NÃO EXECUTÁVEL sem roteiro/clickpath explícito
```

Standalone XHR/Custom exigem uma futura camada de scripted journeys que defina a ação, interação, início/fim e correlação dos requests. Não é correto inferir essas ações apenas pela navegação do crawler.

## 7. Thresholds

Experience não aplica `4T`. Os thresholds são independentes.

Sem customização/importação:

```text
Satisfied <= 3.0 s
Tolerating > 3.0 s e <= 12.0 s
Frustrated > 12.0 s
```

Overrides CLI/ambiente continuam permitidos, desde que:

```text
satisfied > 0
frustrated > satisfied
```

Na importação, valores em milissegundos são convertidos explicitamente para segundos.

## 8. Política de erros

`errors_affect_apdex=true` permite que uma ação rápida seja `FRUSTRATED` quando há erro qualificável.

Escopos RASAi:

- `navigation`;
- `first-party`;
- `all`.

Regras:

- timeout/navigation error => `FRUSTRATED` quando o perfil foi aplicado;
- HTTP >= 400 do documento principal => application error;
- JavaScript runtime error pode frustrar conforme policy;
- request/HTTP errors podem frustrar conforme scope;
- `console.error` sozinho não força `FRUSTRATED`;
- falha da ferramenta/perfil fica fora do denominador.

Dynatrace admite regras de erro mais granulares. A importação deve registrar metadados sanitizados dessas regras quando disponíveis, sem reduzir toda a configuração a uma equivalência falsa com `navigation|first-party|all`.

## 9. Dispositivos e perfis

O mix default RASAi é:

```text
mobile=60,desktop=35,tablet=5
```

Esse valor **não é um default Dynatrace**. Dynatrace RUM observa a distribuição real. Para comparações com uma aplicação específica, o usuário deve substituir o mix pelos percentuais observados no período de referência, quando conhecidos.

Perfis CPU/rede continuam sintéticos, controlados e versionados. Não representam distribuição real de usuários.

## 10. Cold/warm

`cold` é default RASAi:

- novo BrowserContext por amostra;
- cache desabilitado;
- sem cookies/storage entre amostras.

`warm` reutiliza contexto por worker/perfil. Não existe equivalência 1:1 entre esse seletor e população RUM.

## 11. Amostragem e carga

Default:

```text
100 amostras válidas totais por página
max attempts = ceil(1.25 * samples)
```

Grupos menores são diagnósticos. `1000` é suportado, mas representa carga significativa. Uma amostra é uma navegação com múltiplos subrequests.

## 12. Importação Dynatrace

Modos:

1. JSON exportado — preferido para reprodutibilidade;
2. Configuration API — configuração live.

A importação deve extrair/persistir apenas dados sanitizados necessários:

- KPM solicitada;
- KPM efetiva;
- thresholds primários;
- fallback thresholds;
- contrato Load/XHR/Custom quando presente;
- indicador/política de erros quando observável;
- resumo de error rules;
- ocorrência/motivo de fallback.

O payload integral não é persistido.

`DYNATRACE_API_TOKEN`:

- somente ambiente;
- nunca CLI;
- nunca SQLite;
- nunca HTML;
- nunca logs;
- nunca `configuration` serializada.

Quando a configuração não expõe inequivocamente a policy de erro equivalente, o RASAi usa sua policy efetiva e registra a origem em vez de inventar equivalência.

## 13. CLI e variáveis de ambiente

Flags principais:

```text
--apdex-experience / --no-apdex-experience
--apdex-experience-samples
--apdex-experience-max-attempts
--apdex-experience-max-pages
--apdex-experience-device-mix
--apdex-experience-session-mode
--apdex-experience-kpm
--apdex-experience-satisfied-seconds
--apdex-experience-frustrated-seconds
--apdex-experience-errors / --no-apdex-experience-errors
--apdex-experience-error-scope
--apdex-experience-settle-seconds
--apdex-experience-delay-seconds
--apdex-experience-concurrency
--apdex-dynatrace-import
--dynatrace-base-url
--dynatrace-application-id
--apdex-dynatrace-config-json
```

Variáveis correspondentes:

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

## 14. Console interativo

O console é parte do contrato público e deve:

1. permitir configurar todas as variáveis não secretas de Experience;
2. mostrar o nome das variáveis de ambiente e seus defaults;
3. diferenciar valores `PADRÃO` e `CUSTOMIZADO`;
4. identificar valores com origem Dynatrace-compatible e valores apenas operacionais RASAi;
5. indicar `DYNATRACE IMPORT` quando a calibração é importada;
6. nunca mostrar/persistir o valor do token Dynatrace.

## 15. Persistência

Tabelas:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

A execução deve persistir configuração efetiva e metadados sanitizados suficientes para o relatório determinar proveniência. Synthetic Navigation Apdex permanece em `synthetic_apdex_*`.

## 16. Reporting

`report/apdex-experience.html` deve expor:

- fronteira Synthetic vs RUM;
- KPM efetiva;
- KPM Dynatrace solicitada, quando importada;
- thresholds efetivos;
- fallback aplicado, quando houver;
- policy/escopo de erros;
- origem da calibração;
- tabela por parâmetro com `Efetivo`, `Padrão/referência`, `Origem` e observação;
- marcação `PADRÃO`, `CUSTOMIZADO` ou `DYNATRACE IMPORT`;
- parâmetros sem equivalente RUM identificados como RASAi;
- contrato Load/XHR/Custom importado quando disponível;
- mix, session mode, população e grupos por device;
- Satisfied/Tolerating/Frustrated;
- Frustrated forçado por erro;
- p75/p90/p95/p99 quando disponíveis;
- contadores XHR/fetch/resources/errors;
- comparação com Synthetic Navigation Apdex quando houver contexto equivalente;
- referências públicas.

## 17. Fail-open e scoring

Falha do Experience:

- não altera `SARI-001`;
- não altera SCORE-GEO-004;
- não cria finding GEO;
- não muda Coverage/Confidence;
- não invalida Synthetic Navigation Apdex;
- deve ser registrada como limitação operacional.

## 18. Comparabilidade com Dynatrace RUM

Para interpretar delta:

1. mesma URL/ação;
2. KPM solicitada e efetiva;
3. thresholds e fallback;
4. error policy;
5. período;
6. device mix;
7. sessão/cache;
8. condições CPU/rede/geografia.

Mesmo alinhando o que é controlável, igualdade numérica não é esperada porque RUM observa usuários reais e M25 é laboratório sintético.

## 19. Gate de validação

Antes de integrar mudanças neste domínio:

1. testar resolução default `USER_ACTION_DURATION`, 3 s / 12 s;
2. testar overrides CLI/ambiente;
3. testar importação com KPM suportada;
4. testar `VISUALLY_COMPLETE` + fallback thresholds;
5. testar unsupported KPM sem fallback => fail-open;
6. confirmar `apdex.html` inalterado;
7. confirmar tabela de proveniência em `apdex-experience.html`;
8. confirmar console com todas as variáveis/defaults;
9. confirmar ausência do token em artefatos;
10. executar suíte automatizada antes do merge.

## 20. Referências públicas

- Apdex Technical Specification v1.1 — `https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf`
- Dynatrace — Apdex configuration for load actions — `https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions`
- Dynatrace — Work with key performance metrics — `https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/analyze-and-use/work-with-key-performance-metrics`
- Dynatrace — Apdex ratings — `https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/scores-and-ratings/apdex-ratings`
- Dynatrace — Web application configuration API — `https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application`
- Chrome DevTools Protocol — Network / Emulation
- W3C Performance Timeline
