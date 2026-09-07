# Synthetic User Experience Apdex calibrável

**Status:** INTEGRADO E VALIDADO.
**Escopo:** Web Performance sintética, user-action telemetry e comparabilidade metodológica com RUM/APM.
**Não altera:** `BR-GEO-*`, `SARI-001`, Coverage, Confidence, Consolidation, findings ou recomendações GEO.

## 1. Objetivo

Synthetic User Experience Apdex adiciona um segundo domínio de Apdex, separado do Synthetic Navigation Apdex, para medir uma **user action sintética enriquecida** e permitir calibração explícita com ferramentas RUM/APM, inclusive Dynatrace.

O objetivo é reduzir divergências explicáveis por metodologia de coleta - KPM, thresholds, política de erros, dispositivo e sessão - sem manipular o resultado para fazê-lo coincidir com RUM.

Synthetic User Experience Apdex **não é RUM**. Nenhuma execução automatizada deve ser descrita como população de usuários humanos observados.

## 2. Relação com Synthetic Navigation Apdex

Synthetic Navigation Apdex permanece normativo e independente:

```text
Synthetic Navigation Apdex - Standard
Task       = NAVIGATION_LOAD
Satisfied  <= T
Tolerating > T e <= 4T
Frustrated > 4T ou erro de aplicação/navegação válido
```

Synthetic User Experience Apdex é aditivo:

```text
Synthetic User Experience Apdex - Calibrated
Task       = SYNTHETIC_LOAD_ACTION
KPM        = configurável/importada
Satisfied  <= threshold_satisfied
Tolerating > threshold_satisfied e <= threshold_frustrated
Frustrated > threshold_frustrated ou erro qualificável quando policy=ON
```

A fórmula Apdex permanece:

```text
Apdex = (Satisfied + 0.5 * Tolerating) / N_valid
```

Synthetic User Experience Apdex nunca reescreve tabelas, summaries ou score do Synthetic Navigation Apdex.

## 3. Envelope de user action

Cada amostra Synthetic User Experience Apdex observa:

1. início imediatamente antes da navegação;
2. navegação real Chromium até `load`;
3. atividade de rede e recursos posterior ao `load`, limitada por janela de settle;
4. XHR/fetch;
5. recursos iniciados após o load;
6. falhas de request;
7. respostas HTTP >= 400;
8. JavaScript runtime errors;
9. `console.error` apenas como telemetria;
10. Navigation Timing;
11. LCP e CLS quando observáveis;
12. término da user action pelo último evento real observado no envelope, sem acrescentar artificialmente o período interno de quietude do `networkidle`.

A janela pós-load é limitada. O Synthetic User Experience Apdex não afirma equivalência integral ao algoritmo proprietário de duração de user action de qualquer APM.

## 4. KPMs

KPMs temporais suportadas para classificação calibrada:

- `USER_ACTION_DURATION`;
- `DOM_INTERACTIVE`;
- `LOAD_EVENT_START`;
- `LOAD_EVENT_END`;
- `RESPONSE_START`;
- `RESPONSE_END`;
- `LARGEST_CONTENTFUL_PAINT`.

Synthetic User Experience Apdex também persiste CLS, mas não o usa como KPM temporal de Apdex.

Se uma configuração Dynatrace importada usar uma KPM que o Synthetic User Experience Apdex não consegue medir com equivalência suficiente, a execução é recusada. É proibido substituir silenciosamente a KPM por outra.

## 5. Thresholds calibrados

Synthetic User Experience Apdex não assume `4T`.

Quando a calibração é manual, são obrigatórios:

- `satisfied_threshold_seconds > 0`;
- `frustrated_threshold_seconds > satisfied_threshold_seconds`.

Quando a calibração vem do Dynatrace, os thresholds observados são usados conforme a unidade identificada. Payloads legados em milissegundos são convertidos para segundos de forma explícita.

## 6. Política de erros

`errors_affect_apdex=true` permite que uma ação rápida seja `FRUSTRATED` quando houver erro qualificável.

Escopos:

- `navigation`: apenas falha da navegação/documento principal;
- `first-party`: navegação + JavaScript runtime error + request/HTTP error do mesmo host, tolerando apenas diferença `www.`;
- `all`: inclui falhas de terceiros observadas durante a ação.

Regras deliberadas:

- timeout e navigation error são `FRUSTRATED` quando o perfil foi aplicado;
- HTTP >=400 do documento principal é erro de aplicação;
- JavaScript runtime error pode forçar `FRUSTRATED` conforme policy;
- `console.error` **não** força `FRUSTRATED` por si só;
- falha da ferramenta em iniciar/aplicar perfil permanece amostra inválida e fora do denominador.

O escopo `first-party` não inventa registrable-domain/public-suffix equivalence; usa host explícito com normalização conservadora de `www.`.

## 7. Dispositivos

Synthetic User Experience Apdex suporta população explícita:

- `MOBILE`;
- `DESKTOP`;
- `TABLET`.

O mix deve somar exatamente 100%. Exemplo:

```text
mobile=62,desktop=31,tablet=7
```

O RASAi não inventa percentuais de população. Para comparação com RUM, prefira proporções observadas no período do Dynatrace.

Perfil Tablet baseline Synthetic User Experience Apdex:

```text
profile     = RASAI_TABLET_CONTROLLED4G_V1
viewport    = 1024x1366
DSF         = 2
has_touch   = true
CPU         = 2x slowdown
RTT         = 100 ms
download    = 4096 kbps
upload      = 2048 kbps
```

O perfil é controlado/reprodutível; não é declarado como distribuição real de tablets.

## 8. Cold e warm session

`cold`:

- novo BrowserContext por sample;
- cache explicitamente desabilitado;
- cookies/storage não atravessam samples.

`warm`:

- BrowserContext é reutilizado no mesmo worker/perfil;
- cache, cookies e storage podem ser reaproveitados;
- cada sample cria uma nova Page dentro do contexto.

A escolha deve aparecer no relatório e na persistência.

## 9. Amostragem

Default Synthetic User Experience Apdex:

```text
100 amostras válidas totais por página
```

`1000` é suportado, mas não é default.

As amostras são alocadas exatamente conforme o mix. Exemplo:

```text
Total = 1000
Mobile 62%  => 620
Desktop 31% => 310
Tablet 7%   => 70
```

O orçamento de tentativas default é `ceil(1.25 * target_samples)`.

Aumentar N melhora estabilidade estatística do sintético; não transforma o laboratório em RUM.

Execuções grandes contra produção exigem autorização humana de carga/capacidade.

## 10. CPU/rede e população

Synthetic User Experience Apdex baseline usa perfis controlados e versionados por device. Isso mantém reprodutibilidade.

O mix de dispositivos é populacional; CPU/rede permanecem controlados na baseline Synthetic User Experience Apdex. Nenhuma distribuição de CPU/rede é inventada quando não há fonte observada.

Uma futura distribuição estratificada de CPU/rede só poderá ser habilitada com pesos explícitos/proveniência documentada; não é permitido randomizar condições e chamar isso de população real sem fonte.

## 11. Importação Dynatrace

Há dois modos:

1. **JSON exportado** - preferido para reprodutibilidade/offline;
2. **Configuration API** - consulta HTTPS da configuração de aplicação.

A importação extrai apenas o necessário para calibração:

- KPM;
- thresholds;
- indicador de impacto de erros quando observável;
- resumo sanitizado de regras de erro.

O payload integral da configuração Dynatrace não é persistido.

Token:

```text
DYNATRACE_API_TOKEN
```

Regras obrigatórias:

- token somente por ambiente;
- nunca em CLI;
- nunca em SQLite;
- nunca em report;
- nunca em logs;
- nunca em `configuration` serializada.

Quando a configuração não expõe inequivocamente a policy de erro, Synthetic User Experience Apdex usa a policy manual explícita e registra `+MANUAL_ERROR_POLICY` na origem da calibração.

## 12. CLI

Synthetic User Experience Apdex depende de Synthetic Navigation Apdex habilitado.

Principais flags:

```text
--apdex-experience / --no-apdex-experience
--apdex-experience-samples
--apdex-experience-max-attempts
--apdex-experience-max-pages
--apdex-experience-device-mix
--apdex-experience-session-mode cold|warm
--apdex-experience-kpm
--apdex-experience-satisfied-seconds
--apdex-experience-frustrated-seconds
--apdex-experience-errors / --no-apdex-experience-errors
--apdex-experience-error-scope navigation|first-party|all
--apdex-experience-settle-seconds
--apdex-experience-delay-seconds
--apdex-experience-concurrency
--apdex-dynatrace-import
--dynatrace-base-url
--dynatrace-application-id
--apdex-dynatrace-config-json
```

`DYNATRACE_API_TOKEN` não possui flag correspondente.

## 13. Persistência

Tabelas aditivas:

```text
synthetic_ux_apdex_runs
synthetic_ux_apdex_samples
synthetic_ux_apdex_summaries
```

Synthetic Navigation Apdex continua em suas próprias tabelas `synthetic_apdex_*`.

## 14. Reporting

Quando Synthetic User Experience Apdex executa, gera:

```text
report/apdex-experience.html
```

A página deve expor:

- fronteira Synthetic vs RUM;
- KPM;
- thresholds;
- policy/escopo de erros;
- origem da calibração;
- mix de devices;
- session mode;
- população e grupos por device;
- Satisfied/Tolerating/Frustrated;
- Frustrated forçado por erro;
- p75/p90/p95/p99;
- contadores XHR/fetch/resources/errors;
- comparação com Synthetic Navigation Apdex Standard quando houver contexto equivalente;
- referências públicas.

## 15. Fail-open e scoring

Falha Synthetic User Experience Apdex:

- não altera `SARI-001`;
- não altera `SARI-001`;
- não cria finding;
- não muda Coverage/Confidence;
- não invalida Synthetic Navigation Apdex;
- é registrada como limitação operacional.

## 16. Comparabilidade com Dynatrace RUM

Uma comparação é metodologicamente mais útil quando estiverem alinhados:

1. URL/user action;
2. KPM;
3. thresholds;
4. error policy;
5. período de referência;
6. device mix;
7. origem e escopo dos erros.

Mesmo com alinhamento, igualdade numérica não é esperada porque Dynatrace RUM mede usuários reais, redes, devices, sessões e condições operacionais reais.

O delta entre Synthetic User Experience Apdex calibrado e RUM deve ser tratado como evidência, não como defeito automático.

## 17. Gate de smoke humano

Antes do merge:

1. executar 1 URL autorizada;
2. Synthetic Navigation Apdex Standard ON com T explícito;
3. Synthetic User Experience Apdex ON;
4. usar inicialmente 6-12 amostras, não 1000;
5. concorrência 1;
6. confirmar `apdex.html` inalterado;
7. confirmar `apdex-experience.html`;
8. inspecionar Mobile/Desktop/Tablet/Population;
9. confirmar erro conhecido como `Frustrated` quando policy=ON;
10. confirmar ausência de token em SQLite/report/log;
11. repetir com calibração Dynatrace manual ou importada;
12. somente depois autorizar grupo grande (100/1000) contra ambiente real.

## 18. Referências públicas

- Apdex Technical Specification v1.1 - https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf
- Dynatrace - User actions in RUM Classic - https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/user-actions
- Dynatrace - Apdex ratings - https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/scores-and-ratings/apdex-ratings
- Dynatrace - Web application configuration API - https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration
- Chrome DevTools Protocol - Network - https://chromedevtools.github.io/devtools-protocol/tot/Network/
- Chrome DevTools Protocol - Emulation - https://chromedevtools.github.io/devtools-protocol/tot/Emulation/
- W3C Performance Timeline - https://www.w3.org/TR/performance-timeline/
