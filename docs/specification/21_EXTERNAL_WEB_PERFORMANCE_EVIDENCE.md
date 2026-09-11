# Web Performance externo - Core Web Vitals e Lighthouse

**Estado:** IMPLEMENTADO / VIGENTE  
**Domínio:** Web Performance externo  
**Dependências:** report site e configuração opcional PageSpeed/CrUX; IA não é dependência obrigatória  
**Natureza:** evidência externa aditiva; sem impacto automático no scoring

## 1. Objetivo

Adicionar à auditoria RASAi evidências de Web Performance provenientes de fontes externas sem remover, substituir ou recalibrar silenciosamente `SCORE-GEO-004`.

Quando explicitamente habilitado, o recurso pode coletar:

- scores Lighthouse via PageSpeed Insights API;
- categorias `performance`, `accessibility`, `best-practices`, `seo` e `agentic-browsing`;
- métricas de laboratório FCP, Speed Index, LCP, Total Blocking Time e CLS;
- Core Web Vitals de campo provenientes do CrUX quando disponíveis;
- LCP, INP e CLS p75;
- telemetria de chamadas externas;
- payloads JSON sanitizados das respostas externas bem-sucedidas.

Esses dados são complementares. Nenhum valor Lighthouse/PageSpeed/CrUX é convertido automaticamente em contribuição para `SCORE-GEO-004` ou `SARI-001`.

## 2. Configuração PageSpeed/Lighthouse

| Configuração | Default efetivo | Valores permitidos | Recomendado |
|---|---|---|---|
| `RASAI_WEB_PERFORMANCE` | `false` | booleano | `false`; habilitar quando a coleta externa for necessária |
| `RASAI_WEB_PERFORMANCE_MAX_PAGES` | `10` | inteiro `>= 0`; `0=todas` | `10` ou menor em smoke |
| `RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS` | `120` | número `> 0` | `120` |
| `RASAI_WEB_PERFORMANCE_FIELD_SOURCE` | `auto` | `auto`, `pagespeed`, `crux`, `none` | `auto` |
| `RASAI_LIGHTHOUSE_CATEGORIES` | `performance,accessibility,best-practices,seo,agentic-browsing` | combinação CSV sem duplicatas das cinco categorias suportadas | default das cinco categorias |
| `RASAI_PAGESPEED_API_KEY` | sem default | API key válida | secret/env |
| `RASAI_CRUX_API_KEY` | sem default | API key válida | secret/env; necessária para `field_source=crux` |

As categorias configuradas são solicitadas na mesma chamada PageSpeed de cada contexto.

### Agentic Browsing

A integração vigente aceita `agentic-browsing` na lista de categorias do request PageSpeed. O RASAi pode persistir `agentic_browsing_score` quando a resposta materializa essa categoria.

Agentic Browsing continua experimental. Consequentemente:

- sua composição pode mudar entre versões;
- ausência da categoria na resposta mantém o score indisponível/`NULL`;
- indisponibilidade não é convertida em zero;
- Performance, Accessibility, Best Practices e SEO válidos permanecem independentes e utilizáveis;
- Agentic Browsing permanece fora de `SARI-001`/`SCORE-GEO-004`.

## 3. Core Web Vitals e CrUX

Métricas de interesse:

```text
largest_contentful_paint
interaction_to_next_paint
cumulative_layout_shift
```

Mapeamento de dispositivo:

```text
RASAi MOBILE  -> CrUX PHONE
RASAi DESKTOP -> CrUX DESKTOP
```

Thresholds externos de boa experiência aplicados pelo runtime:

| Métrica | Valor vigente | Natureza | Configurável pelo usuário? | Recomendação documental |
|---|---:|---|---|---|
| LCP | `<= 2500 ms` | threshold externo de Core Web Vitals | não nesta integração | preservar o valor oficial enquanto o contrato externo vigente não mudar |
| INP | `<= 200 ms` | threshold externo de Core Web Vitals | não nesta integração | preservar o valor oficial |
| CLS | `<= 0.10` | threshold externo de Core Web Vitals | não nesta integração | preservar o valor oficial |

Estados CWV:

```text
PASS
FAIL
INCOMPLETE
UNAVAILABLE
```

`INCOMPLETE` e `UNAVAILABLE` descrevem cobertura/ausência de field data; não representam automaticamente falha do website.

## 4. Ativação e consumo

Precedência:

```text
flag CLI explícita > variável de ambiente > false
```

Quando desabilitado, não existe chamada PageSpeed, CrUX ou LLM adicional para esta finalidade.

`--web-performance-max-pages 0` significa todas as páginas auditadas elegíveis. `--device-context both` pode gerar contextos Mobile e Desktop para a mesma página.

O timeout é aplicado por tentativa externa. Retry de falha transitória, quando previsto pelo adapter, continua sujeito aos limites internos de resiliência.

## 5. Credenciais

`RASAI_PAGESPEED_API_KEY` e `RASAI_CRUX_API_KEY` são independentes das credenciais de IA.

Chaves nunca devem ser persistidas em SQLite, artifacts, HTML ou logs, nem registradas em URL com query string de credencial. Telemetria pode registrar somente o fato de a credencial estar configurada.

## 6. Política de field data

- `auto`: usa field data da resposta PageSpeed e, quando ausente e houver configuração, pode recorrer a CrUX direto;
- `pagespeed`: usa somente field data PageSpeed;
- `crux`: usa CrUX direto para field data e PageSpeed para Lighthouse;
- `none`: desabilita field data e mantém Lighthouse PageSpeed.

## 7. Estados da execução

```text
DISABLED
NO_CONTEXTS
SUCCESS
PARTIAL
UNAVAILABLE
```

`SUCCESS` exige evidência útil nos contextos selecionados sem falha de componente solicitado. Ausência isolada de Agentic Browsing não transforma a coleta em falha quando as demais evidências solicitadas permanecem válidas.

`PARTIAL` indica evidência útil combinada com falha/indisponibilidade de componente configurado. `UNAVAILABLE` indica que nenhum contexto selecionado produziu evidência externa útil.

Esses estados qualificam a coleta e não reduzem `SCORE-GEO-004`.

## 8. Persistência

Tabelas:

```text
web_performance_runs
web_performance_observations
web_performance_attempts
```

`web_performance_runs` resume a execução. `web_performance_observations` preserva scores Lighthouse, métricas de laboratório, field data/CWV, status e proveniência. `web_performance_attempts` registra chamadas externas tentadas com serviço, contexto, status, HTTP/duração e erro sanitizado.

`agentic_browsing_score` permanece `NULL` quando não materializado pela resposta.

Respostas externas bem-sucedidas podem ser preservadas em `artifacts/web-performance/`, permitindo reabrir resultados sem nova chamada externa.

## 9. Relatório

Superfície canônica:

```text
report/web-performance.html
```

O relatório deve distinguir:

- Lighthouse de laboratório;
- CrUX/Core Web Vitals de campo;
- source e scope URL/origin;
- indisponibilidade/incompletude;
- telemetria de tentativas externas;
- separação de `SARI-001`/`SCORE-GEO-004`;
- Agentic Browsing como categoria experimental.

`report/index.html` pode resumir Web Performance, mas nunca recalcula Overall Readiness a partir dessas métricas.

## 10. Fail-open

Indisponibilidade PageSpeed/CrUX não invalida RuleExecution/scoring já concluídos. A causa deve permanecer atribuída ao serviço externo, não ao website.

## 11. Segurança e observabilidade

O log operacional deve distinguir PageSpeed/CrUX, Mobile/Desktop, sucesso/erro, HTTP status, duração e artifact produzido, sempre de forma sanitizada.

Falha na escrita de log é fail-open e não altera o resultado da auditoria.

A página e os artifacts não podem conter API keys, Authorization headers, tokens ou passwords.

## 12. Relação com IA

Web Performance externo adiciona zero chamadas LLM. Scores Lighthouse/CrUX nunca são produzidos ou recalculados por IA.

Qualquer interpretação futura por IA exige finalidade explícita, telemetria própria e contrato que preserve a medição-fonte.

## 13. Referências e direitos autorais

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

Este arquivo utiliza conceitos, nomes de métricas e thresholds definidos por fontes externas; não reproduz integralmente a documentação dos mantenedores.

- PageSpeed Insights API: <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- PageSpeed getting started: <https://developers.google.com/speed/docs/insights/v5/get-started>
- CrUX API: <https://developer.chrome.com/docs/crux/api/>
- Web Vitals: <https://web.dev/articles/vitals>
- Lighthouse Performance: <https://developer.chrome.com/docs/lighthouse/performance/performance-scoring>
- Lighthouse Agentic Browsing: <https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js>
- [`../LIGHTHOUSE_CATEGORIES.md`](../LIGHTHOUSE_CATEGORIES.md)
- [`../LIGHTHOUSE_PAGESPEED_TRANSPORT.md`](../LIGHTHOUSE_PAGESPEED_TRANSPORT.md)
- [`../GOOGLE_API_KEYS.md`](../GOOGLE_API_KEYS.md)
- [`../EXTERNAL_METRICS_INTEGRITY.md`](../EXTERNAL_METRICS_INTEGRITY.md)