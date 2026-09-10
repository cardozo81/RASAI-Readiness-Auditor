# Synthetic Navigation Apdex e rastreabilidade Lighthouse

**Estado:** INTEGRADO / VIGENTE  
**Escopo:** Web Performance sintética e rastreabilidade da configuração Lighthouse.  
**Não altera:** `BR-GEO-*`, `SARI-001`, Coverage, Confidence, Consolidation, findings GEO ou recomendações GEO.

## 1. Objetivo

Synthetic Navigation Apdex adiciona uma medição sintética baseada em uma Task explícita de navegação e torna auditável a configuração efetiva de execução Lighthouse já persistida pelo domínio Web Performance.

A capacidade existe porque Lighthouse/Core Web Vitals não são substitutos de Apdex. Um índice Apdex só é calculável quando existem:

1. Task definida;
2. threshold `T` explícito;
3. população de tempos de resposta dessa Task;
4. classificação Satisfied/Tolerating/Frustrated segundo o contrato Apdex adotado.

## 2. Task medida

```text
TASK_ID = NAVIGATION_LOAD
```

- início: imediatamente antes de `page.goto`;
- término: conclusão de `page.goto(..., wait_until="load")`;
- unidade persistida: milissegundos;
- cada amostra usa BrowserContext novo;
- cache do browser é explicitamente desabilitado;
- perfis de CPU/rede são determinísticos e versionados;
- não existe randomização de RTT/throughput/CPU no baseline.

A Task mede navegação sintética controlada. Não deve ser apresentada como RUM, APM, experiência real de usuário ou tempo de transação de negócio.

## 3. Fórmula e classificação

Para `N` amostras válidas:

```text
Apdex = (Satisfied + 0.5 × Tolerating) / N
```

Classificação:

```text
Satisfied : duração <= T
Tolerating: duração > T e <= 4T
Frustrated: duração > 4T
```

Erros de aplicação/servidor, timeout e erro de navegação são `FRUSTRATED` quando o perfil sintético foi aplicado e a tentativa representa uma execução válida da Task.

Falha da ferramenta em iniciar/aplicar browser, CPU ou rede é amostra inválida e fica fora do denominador. A exclusão deve permanecer persistida e auditável.

## 4. Configuração pública

Synthetic Navigation Apdex é desabilitado por padrão. `T` não possui default deliberadamente: deve representar o objetivo/SLO da Task e não pode ser inventado a partir de Lighthouse, LCP, INP, CLS ou dados históricos.

| Parâmetro / variável | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_SYNTHETIC_APDEX` | `false` | booleano | `false`; habilitar somente quando houver objetivo e autorização de carga |
| `RASAI_APDEX_THRESHOLD_SECONDS` | sem default | número finito `> 0` | usar threshold da Task/SLO definido pela organização |
| `RASAI_APDEX_SAMPLES_PER_CONTEXT` | `100` | inteiro `>= 1` | `100`; reduzir somente em smoke controlado |
| `RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT` | `ceil(1.25 × samples)` | inteiro positivo validado pelo runtime | default derivado |
| `RASAI_APDEX_MAX_PAGES` | `1` | inteiro `>= 0`; `0=todas` | `1` como baseline seguro de carga |
| `RASAI_APDEX_TIMEOUT_SECONDS` | `max(45, 4T + 5)` | número finito positivo e, no contrato efetivo, maior que `4T` | default derivado |
| `RASAI_APDEX_DELAY_SECONDS` | `1.0` | número finito `>= 0` | `1.0` ou maior conforme sensibilidade do alvo |
| `RASAI_APDEX_CONCURRENCY` | `1` | `1`, `2` | `1`; usar `2` apenas quando a carga paralela for aceitável |

Precedência:

```text
CLI explícito > variável de ambiente > default seguro
```

Flags correspondentes:

```text
--synthetic-apdex / --no-synthetic-apdex
--apdex-threshold-seconds
--apdex-samples-per-context
--apdex-max-attempts-per-context
--apdex-max-pages
--apdex-timeout-seconds
--apdex-delay-seconds
--apdex-concurrency
```

## 5. Tamanho do grupo

O alvo padrão é `100` amostras válidas por URL/dispositivo.

Grupos com 1–99 amostras válidas podem ser calculados para diagnóstico, mas são marcados como `small_group=*` e não representam o grupo final normal.

O runtime tenta substituir amostras inválidas até `max_attempts_per_context`; quando não configurado, o orçamento é `ceil(1.25 × target_valid_samples)`.

## 6. Perfis e reprodutibilidade

Perfis sintéticos Mobile/Desktop possuem versão explícita. O executor registra, quando disponível:

- viewport e propriedades do device;
- User-Agent;
- CPU slowdown;
- RTT;
- download/upload throughput;
- connection type;
- cache policy;
- versão do profile;
- ambiente do host;
- versão Chromium/Playwright.

A implementação não deve afirmar equivalência entre o perfil Synthetic Navigation Apdex e o profile efetivo do Lighthouse.

## 7. Pacing, concorrência e carga

Defaults de carga:

```text
max_pages   = 1
delay       = 1 s entre inícios
concurrency = 1
maximum     = 2 workers
```

O pacer controla inícios de navegação. Uma navegação pode carregar HTML, CSS, JavaScript, imagens, fontes e terceiros; portanto, `N` amostras não equivale a `N` requests HTTP.

Synthetic Navigation Apdex:

- não chama LLM;
- não chama PageSpeed/CrUX por si só;
- não possui preço monetário de API próprio;
- consome CPU/RAM/tempo local e tráfego HTTP real contra o alvo.

Execução de grupo grande contra produção exige autorização e avaliação de capacidade do ambiente auditado.

## 8. Persistência

Tabelas aditivas:

```text
synthetic_apdex_runs
synthetic_apdex_samples
synthetic_apdex_summaries
lighthouse_execution_profiles
```

Cada amostra mantém status, classificação, duração, HTTP status, URL final, profile, métodos CPU/rede, cache policy, erro sanitizado e timestamp conforme disponibilidade.

Nenhum secret deve ser persistido.

## 9. Rastreabilidade Lighthouse

Synthetic Navigation Apdex lê exclusivamente artifacts de Web Performance já existentes e extrai `lighthouseResult.configSettings`, environment e timing quando disponíveis.

Campos não observados permanecem `NULL`/ausentes. É proibido inventar throttling method, RTT/throughput, CPU slowdown, viewport, User-Agent, benchmark index ou duração do Lighthouse.

Tempo total de execução Lighthouse é telemetria do Lighthouse e não entra no cálculo Apdex.

## 10. Relatório

Quando a capacidade é habilitada e chega ao estágio de reporting, gera:

```text
report/apdex.html
```

A página deve mostrar:

- estado da execução;
- `T` e `4T`;
- tamanho do grupo;
- Satisfied/Tolerating/Frustrated;
- Apdex;
- min/max/média/mediana;
- p75/p90/p95/p99;
- desvio padrão/CV;
- tendência entre metades da amostra;
- perfil sintético;
- rastreabilidade Lighthouse quando existente;
- ambiente do executor;
- aviso de carga;
- separação explícita de SARI-001, Lighthouse, CrUX e IA.

`apdex.html` participa do menu canônico somente quando o arquivo existe.

## 11. Fail-open

Falha do Synthetic Navigation Apdex:

- não transforma o site em `FAIL` GEO;
- não altera findings/scoring;
- não invalida o audit principal;
- deve ser registrada como estado operacional quando possível.

Web Performance e Synthetic Navigation Apdex são independentes: falha PageSpeed/CrUX não impede, por si só, Synthetic Navigation Apdex; falha Synthetic Navigation Apdex não invalida Web Performance.

## 12. Console interativo

O console deve expor:

- habilitação da capacidade;
- `T` obrigatório quando ON;
- amostras/tentativas/páginas/timeout/delay/concorrência;
- default e valor efetivo;
- indicação `PADRÃO`/`CUSTOMIZADO` quando aplicável;
- teto estimado de navegações;
- aviso de que subresources multiplicam requests;
- zero custo de API próprio;
- progresso por amostra;
- totais reais persistidos no resumo final.

## 13. Validação mínima

A regressão deve cobrir:

- configuração default OFF;
- erro quando ON sem `T`;
- validação de `samples`, `max_attempts`, `max_pages`, timeout, delay e concorrência;
- classificação Satisfied/Tolerating/Frustrated;
- exclusão de falha de ferramenta do denominador;
- grupos pequenos marcados explicitamente;
- persistência e reabertura;
- `apdex.html` e navegação canônica;
- ausência de alteração em `SARI-001/SCORE-GEO-004`;
- ausência de chamadas LLM/PageSpeed/CrUX criadas exclusivamente por esta capacidade.

## 14. Referências e direitos autorais

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

Este arquivo não reproduz integralmente os documentos abaixo; usa apenas conceitos e valores técnicos necessários ao contrato. Quando um trecho literal for acrescentado futuramente, deve seguir a regra acima.

- Apdex Technical Specification v1.1: <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>
- Chrome DevTools Protocol — Emulation: <https://chromedevtools.github.io/devtools-protocol/tot/Emulation/>
- Chrome DevTools Protocol — Network: <https://chromedevtools.github.io/devtools-protocol/tot/Network/>
- Lighthouse — Understanding results: <https://github.com/GoogleChrome/lighthouse/blob/main/docs/understanding-results.md>
- Lighthouse — Emulation: <https://github.com/GoogleChrome/lighthouse/blob/main/docs/emulation.md>