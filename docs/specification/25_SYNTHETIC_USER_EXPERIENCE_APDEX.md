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
Satisfied  <= threshold_satisfied
Tolerating > threshold_satisfied e <= threshold_frustrated
Frustrated > threshold_frustrated ou erro qualificável quando policy=ON
```

Fórmula:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

Os dois domínios possuem persistência e relatórios independentes.

## 3. Configuração padrão e valores permitidos

Quando Experience está habilitado e não existe override CLI/ambiente nem importação Dynatrace, o runtime resolve os valores abaixo.

| Parâmetro / variável | Default efetivo | Valores permitidos | Recomendado | Origem |
|---|---|---|---|---|
| `RASAI_APDEX_EXPERIENCE` | `false` | booleano | `false`; habilitar deliberadamente | RASAi |
| KPM / `RASAI_APDEX_EXPERIENCE_KPM` | `USER_ACTION_DURATION` | `USER_ACTION_DURATION`, `DOM_INTERACTIVE`, `LOAD_EVENT_START`, `LOAD_EVENT_END`, `RESPONSE_START`, `RESPONSE_END`, `LARGEST_CONTENTFUL_PAINT` | default quando não houver calibração importada | fallback executável compatível com referência Dynatrace |
| `RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS` | `3.0` | número finito `> 0` | `3.0` no baseline compatível; calibrar quando houver SLO/configuração real | referência/fallback Load Action |
| `RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS` | `12.0` | número finito `> satisfied` | `12.0` no baseline compatível | referência/fallback Load Action |
| `RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT` | `true` | booleano | `true`, salvo política deliberadamente diferente | RASAi alinhado semanticamente a erro frustrante |
| `RASAI_APDEX_EXPERIENCE_ERROR_SCOPE` | `first-party` | `navigation`, `first-party`, `all` | `first-party` | política RASAi; sem enum Dynatrace 1:1 |
| `RASAI_APDEX_EXPERIENCE_SAMPLES` | `100` | inteiro `>= 1` | `100`; reduzir apenas em smoke controlado | RASAi |
| `RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS` | `ceil(1.25 × samples)` | inteiro `>= 1` validado pelo runtime | default derivado | RASAi |
| `RASAI_APDEX_EXPERIENCE_MAX_PAGES` | herda o limite padrão da execução sintética; normalmente `1` | inteiro `>= 0`; `0=todas` | `1` como baseline de carga | RASAi |
| `RASAI_APDEX_EXPERIENCE_DEVICE_MIX` | `mobile=60,desktop=35,tablet=5` | percentuais não negativos para Mobile/Desktop/Tablet somando exatamente `100` | usar distribuição real observada quando o objetivo for comparar com RUM | RASAi |
| `RASAI_APDEX_EXPERIENCE_SESSION_MODE` | `cold` | `cold`, `warm` | `cold` para reprodutibilidade | RASAi |
| `RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS` | `5.0` | número finito `> 0` | `5.0` | RASAi |
| `RASAI_APDEX_EXPERIENCE_DELAY_SECONDS` | herda o delay sintético; normalmente `1.0` | número finito `>= 0` | `1.0` ou maior conforme sensibilidade do alvo | RASAi |
| `RASAI_APDEX_EXPERIENCE_CONCURRENCY` | herda a concorrência sintética; normalmente `1` | `1`, `2` | `1` | RASAi |
| `RASAI_APDEX_DYNATRACE_IMPORT` | `false` | booleano | `false`; habilitar somente quando houver configuração Dynatrace a importar | RASAi |
| `RASAI_DYNATRACE_BASE_URL` | sem default | URL HTTPS válida | configurar apenas para importação via API | integração Dynatrace |
| `RASAI_DYNATRACE_APPLICATION_ID` | sem default | identificador textual válido | configurar apenas para importação via API | integração Dynatrace |
| `RASAI_DYNATRACE_CONFIG_JSON` | sem default | caminho para JSON exportado válido | preferido para auditoria reproduzível | integração Dynatrace |
| `DYNATRACE_API_TOKEN` | sem default | token não vazio aceito pelo ambiente Dynatrace | secret/env; nunca persistir | integração Dynatrace |

Precedência geral para parâmetros configuráveis:

```text
CLI explícito > variável de ambiente > default do runtime
```

A importação Dynatrace, quando habilitada e válida, substitui os valores de KPM/thresholds conforme o contrato importado e registra a origem.

## 4. KPM Dynatrace e viabilidade técnica

O RASAi não implementa Dynatrace Visually Complete com equivalência de fornecedor.

KPMs temporais diretamente mensuráveis pelo runtime:

```text
USER_ACTION_DURATION
DOM_INTERACTIVE
LOAD_EVENT_START
LOAD_EVENT_END
RESPONSE_START
RESPONSE_END
LARGEST_CONTENTFUL_PAINT
```

O importador reconhece ainda nomes/aliases externos que podem não ser executáveis diretamente, como `VISUALLY_COMPLETE`, `SPEED_INDEX`, `CUMULATIVE_LAYOUT_SHIFT` e `FIRST_INPUT_DELAY`. Reconhecer um valor importado não significa que ele possa ser usado como KPM temporal efetiva.

CLS pode ser persistido como telemetria, mas não é KPM temporal de Apdex. Métrica sem equivalência suficiente não pode ser substituída silenciosamente.

### 4.1 Fallback importado

Se a configuração Dynatrace solicitar KPM não mensurável e fornecer fallback thresholds utilizáveis:

```text
requested_kpm = KPM Dynatrace original
effective_kpm = USER_ACTION_DURATION
thresholds    = fallback thresholds importados
source        += RASAI_CAPABILITY_FALLBACK
```

O relatório deve exibir o fallback. Se os thresholds necessários não existirem ou forem inválidos, a execução Experience falha de forma fail-open, sem alterar o audit core.

## 5. Envelope de Load Action sintética

Cada amostra observa, conforme disponibilidade:

1. início antes da navegação;
2. Chromium até `load`;
3. atividade posterior ao load dentro da janela limitada;
4. XHR/fetch;
5. recursos tardios;
6. request failures;
7. HTTP `>= 400`;
8. JavaScript runtime errors;
9. `console.error` como telemetria;
10. Navigation Timing;
11. LCP e CLS quando observáveis;
12. término pelo último evento real observado dentro do envelope.

A janela de settle não é acrescentada artificialmente à duração da ação.

## 6. Load, XHR e Custom Action

A importação Dynatrace deve preservar, de forma sanitizada, contratos disponíveis de Load, XHR e Custom Action.

Cobertura executável atual:

```text
Load Action    = EXECUTÁVEL
XHR Action     = XHR/fetch observado dentro do Load; não autônomo
Custom Action  = NÃO EXECUTÁVEL sem roteiro/clickpath explícito
```

Standalone XHR/Custom exigem uma futura camada de scripted journeys que defina ação, interação, início/fim e correlação dos requests. Não é correto inferir essas ações apenas pela navegação do crawler.

## 7. Thresholds

Experience não aplica automaticamente `4T`. Os thresholds Satisfied e Frustrated são independentes.

Sem customização/importação:

```text
Satisfied <= 3.0 s
Tolerating > 3.0 s e <= 12.0 s
Frustrated > 12.0 s
```

Overrides são aceitos desde que:

```text
satisfied > 0
frustrated > satisfied
```

Valores Dynatrace importados em milissegundos são convertidos explicitamente para segundos.

## 8. Política de erros

`errors_affect_apdex=true` permite que uma ação rápida seja `FRUSTRATED` quando existe erro qualificável.

Escopos RASAi:

- `navigation`;
- `first-party`;
- `all`.

Regras:

- timeout/navigation error → `FRUSTRATED` quando o perfil foi aplicado;
- HTTP `>= 400` do documento principal → application error;
- JavaScript runtime error pode frustrar conforme policy;
- request/HTTP errors podem frustrar conforme scope;
- `console.error` isolado não força `FRUSTRATED`;
- falha da ferramenta/perfil fica fora do denominador.

Dynatrace admite regras de erro mais granulares. A importação registra metadados sanitizados dessas regras quando disponíveis, sem inventar equivalência com `navigation|first-party|all`.

## 9. Dispositivos e perfis

O mix default RASAi é:

```text
mobile=60,desktop=35,tablet=5
```

Esse valor **não é default Dynatrace**. RUM observa a distribuição real. Para comparação com aplicação específica, o usuário deve substituir o mix pelos percentuais observados no período de referência, quando conhecidos.

Perfis CPU/rede continuam sintéticos, controlados e versionados.

## 10. Cold/warm

`cold` é default RASAi:

- novo BrowserContext por amostra;
- cache desabilitado;
- sem cookies/storage entre amostras.

`warm` reutiliza contexto por worker/perfil. Não existe equivalência 1:1 entre esse seletor e população RUM.

## 11. Amostragem e carga

Default operacional:

```text
100 amostras válidas totais por página
max attempts = ceil(1.25 × samples)
```

Grupos menores são diagnósticos. Valores maiores são tecnicamente aceitos como inteiros positivos, mas ampliam carga. Uma amostra é uma navegação com múltiplos subrequests.

Carga relevante contra produção depende de autorização e avaliação de capacidade.

## 12. Importação Dynatrace

Modos:

1. JSON exportado — recomendado para reprodutibilidade;
2. Configuration API — leitura live de configuração.

A importação deve extrair/persistir somente dados sanitizados necessários:

- KPM solicitada;
- KPM efetiva;
- thresholds primários;
- fallback thresholds;
- contrato Load/XHR/Custom quando presente;
- indicador/política de erros quando observável;
- resumo de error rules;
- ocorrência/motivo de fallback.

O payload integral não é persistido.

`DYNATRACE_API_TOKEN` fica somente em runtime e não deve ser persistido em CLI serializada, SQLite, HTML, logs ou `configuration`.

## 13. Console interativo

O console deve:

1. permitir configurar todas as variáveis não secretas de Experience;
2. mostrar nome da variável, default e valor efetivo;
3. diferenciar `PADRÃO` e `CUSTOMIZADO`;
4. identificar valores com origem Dynatrace-compatible e valores operacionais RASAi;
5. indicar `DYNATRACE IMPORT` quando a calibração for importada;
6. nunca mostrar/persistir o valor do token Dynatrace.

## 14. Persistência

Tabelas:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

A execução persiste configuração efetiva e metadados sanitizados suficientes para proveniência. Synthetic Navigation Apdex permanece em `synthetic_apdex_*`.

## 15. Relatório

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

## 16. Fail-open e scoring

Falha de Experience:

- não altera `SARI-001`;
- não altera `SCORE-GEO-004`;
- não cria finding GEO;
- não muda Coverage/Confidence;
- não invalida Synthetic Navigation Apdex;
- deve ser registrada como limitação operacional.

## 17. Comparabilidade com Dynatrace RUM

Para interpretar diferenças, comparar:

1. mesma URL/ação;
2. KPM solicitada e efetiva;
3. thresholds e fallback;
4. política de erros;
5. período;
6. device mix;
7. sessão/cache;
8. condições CPU/rede/geografia.

Mesmo alinhando fatores controláveis, igualdade numérica não é esperada porque RUM observa usuários reais e Synthetic User Experience Apdex é laboratório sintético.

## 18. Validação mínima

A regressão deve cobrir:

1. resolução default `USER_ACTION_DURATION`, 3 s / 12 s;
2. overrides CLI/ambiente;
3. importação com KPM suportada;
4. `VISUALLY_COMPLETE` com fallback thresholds utilizáveis;
5. KPM não suportada sem fallback → fail-open;
6. `apdex.html` permanece independente;
7. tabela de proveniência em `apdex-experience.html`;
8. console expõe variáveis/defaults/valores efetivos;
9. token não aparece em artifacts;
10. suíte automatizada aplicável permanece verde.

## 19. Referências externas e direitos autorais

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

Os excertos originais necessários para justificar a KPM padrão/fallback Dynatrace e os thresholds de referência estão documentados, com tradução pt-BR, em `../SYNTHETIC_USER_EXPERIENCE_APDEX.md`. Esta especificação não repete os trechos para evitar reprodução redundante.

- Apdex Technical Specification v1.1: <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>
- Dynatrace — Apdex configuration for load actions: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions>
- Dynatrace — Key performance metrics: <https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-synthetic-browser-kpms>
- Dynatrace — Work with key performance metrics: <https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/analyze-and-use/work-with-key-performance-metrics>
- Dynatrace — Web application configuration API: <https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application>
- Chrome DevTools Protocol — Network / Emulation
- W3C Performance Timeline