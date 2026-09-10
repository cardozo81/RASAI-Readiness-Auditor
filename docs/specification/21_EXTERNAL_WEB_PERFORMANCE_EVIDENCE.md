# Web Performance externo - Evidência Externa de Web Performance: Core Web Vitals + Lighthouse

**Estado:** IMPLEMENTADO  
**Domínio:** `Web Performance externo`  
**Dependências:** report site + configuração opcional PageSpeed/CrUX; IA não é dependência obrigatória  
**Natureza:** evidência externa aditiva; sem impacto no scoring por padrão

## 1. Objetivo

O Web Performance externo adiciona à auditoria RASAi evidências de Web Performance fundamentadas em fontes externas, sem remover, substituir ou recalibrar silenciosamente `SCORE-GEO-004`.

Quando explicitamente habilitado, o recurso pode coletar:

- scores Lighthouse por meio da PageSpeed Insights API;
- categorias `performance`, `accessibility`, `best-practices` e `seo`;
- métricas de laboratório FCP, Speed Index, LCP, Total Blocking Time e CLS;
- Core Web Vitals de campo provenientes do CrUX quando disponíveis;
- LCP, INP e CLS p75;
- telemetria de chamadas externas;
- payloads JSON das respostas externas bem-sucedidas.

Esses dados são externos e complementares. Nenhum valor Lighthouse/PageSpeed/CrUX é convertido automaticamente em contribuição para `SCORE-GEO-004` ou `SARI-001`.

## 2. Contrato PageSpeed/Lighthouse

O adapter PageSpeed Insights vigente solicita somente:

```text
performance
accessibility
best-practices
seo
```

Configuração:

```text
--lighthouse-categories performance,accessibility,best-practices,seo
RASAI_LIGHTHOUSE_CATEGORIES=performance,accessibility,best-practices,seo
```

As categorias configuradas são solicitadas na mesma chamada PageSpeed de cada contexto.

### Agentic Browsing

`agentic-browsing` não faz parte do request do adapter PageSpeed vigente. O campo `agentic_browsing_score` pode permanecer na persistência e em leitores por compatibilidade/evolução, mas só pode receber valor de uma fonte Lighthouse direta compatível.

Enquanto essa fonte separada não existir:

- o score deve permanecer indisponível/`NULL`;
- indisponibilidade não pode ser convertida em zero;
- as quatro categorias PageSpeed válidas permanecem independentes;
- Agentic Browsing permanece fora de `SARI-001`/`SCORE-GEO-004`.

Referências:

- PageSpeed Insights API: <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- PageSpeed getting started: <https://developers.google.com/speed/docs/insights/v5/get-started>
- configuração experimental Agentic no Lighthouse: <https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js>

## 3. Core Web Vitals / CrUX

A API CrUX direta pode ser usada em:

```text
POST https://chromeuxreport.googleapis.com/v1/records:queryRecord
```

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

Thresholds de boa experiência usados pelo runtime:

```text
LCP <= 2500 ms
INP <= 200 ms
CLS <= 0.10
```

Estados CWV:

```text
PASS
FAIL
INCOMPLETE
UNAVAILABLE
```

`INCOMPLETE` e `UNAVAILABLE` descrevem cobertura/ausência de field data; não representam automaticamente falha do website.

Referências:

- <https://developer.chrome.com/docs/crux/api/>
- <https://developer.chrome.com/docs/crux/guides/crux-api>
- <https://web.dev/articles/vitals>

## 4. Ativação e consumo

A coleta é OFF por padrão:

```text
--web-performance
--no-web-performance
RASAI_WEB_PERFORMANCE
```

Precedência:

1. flag CLI explícita;
2. variável de ambiente;
3. `false`.

Quando desabilitado não existe chamada PageSpeed, CrUX ou LLM adicional para esta finalidade.

### Limite de páginas

```text
--web-performance-max-pages N
RASAI_WEB_PERFORMANCE_MAX_PAGES
```

Default: `10`.

- `N > 0`: primeiras N páginas, em ordem determinística;
- `0`: todas as páginas auditadas elegíveis;
- `--device-context both` pode gerar contextos Mobile e Desktop para a mesma página.

### Timeout

```text
--web-performance-timeout-seconds SECONDS
RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS
```

Default: `120` segundos por request externo. Não há retry automático do mesmo request Web Performance após timeout.

## 5. Credenciais

```text
RASAI_PAGESPEED_API_KEY
RASAI_CRUX_API_KEY
```

A chave CrUX é obrigatória quando `field_source=crux`. Credenciais Web Performance são independentes das credenciais de IA.

Chaves nunca devem ser persistidas em SQLite, artifacts, HTML ou logs, nem registradas em URL com query string de credencial. Telemetria pode registrar apenas o fato de a chave estar configurada.

## 6. Política de field data

```text
--web-performance-field-source auto|pagespeed|crux|none
RASAI_WEB_PERFORMANCE_FIELD_SOURCE
```

Default: `auto`.

- `auto`: usa field data da resposta PageSpeed e, quando ausente e houver configuração, tenta CrUX direto;
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

`SUCCESS` exige evidência útil nos contextos selecionados sem falha de componente solicitado. A ausência de Agentic Browsing não afeta esse estado porque Agentic não é componente solicitado pelo adapter PageSpeed.

`PARTIAL` indica evidência útil combinada com uma ou mais falhas/indisponibilidades de componentes configurados. `UNAVAILABLE` indica que nenhum contexto selecionado produziu evidência externa útil.

Esses estados qualificam a coleta e não reduzem `SCORE-GEO-004`.

## 8. Persistência

Tabelas:

```text
web_performance_runs
web_performance_observations
web_performance_attempts
```

`web_performance_runs` resume a execução. `web_performance_observations` preserva os scores Lighthouse, métricas de laboratório, field data/CWV, status e proveniência. `web_performance_attempts` registra cada chamada externa tentada, com serviço, contexto, status, HTTP/duração e erro sanitizado.

`agentic_browsing_score` permanece como campo de compatibilidade e deve ficar `NULL` em coleta exclusivamente PageSpeed.

Respostas externas bem-sucedidas podem ser materializadas em `artifacts/web-performance/`, permitindo reabrir resultados sem nova chamada externa.

## 9. Reporting

A superfície principal é:

```text
report/web-performance.html
```

O relatório deve distinguir claramente:

- Lighthouse de laboratório;
- CrUX/Core Web Vitals de campo;
- source e scope URL/origin;
- indisponibilidade/incompletude;
- telemetria de tentativas externas;
- separação de `SARI-001`/`SCORE-GEO-004`;
- Agentic Browsing como indisponível via provider atual enquanto não houver adapter Lighthouse direto.

`report/index.html` pode resumir Web Performance, mas nunca recalcula Overall Readiness a partir dessas métricas.

## 10. Fail-open

Indisponibilidade PageSpeed/CrUX não invalida RuleExecution/scoring já concluídos. A causa deve permanecer atribuída ao serviço externo, não ao website.

Erro da camada Web Performance é capturado e registrado quando possível. O audit principal permanece utilizável e pode apresentar resultado parcial.

## 11. Segurança e observabilidade

O log operacional deve distinguir PageSpeed/CrUX, Mobile/Desktop, sucesso/erro, HTTP status, duração e artifact produzido, sempre de forma sanitizada.

Falha na escrita do log é fail-open e não muda o resultado da auditoria.

A página e os artifacts não podem conter API keys, Authorization headers, tokens ou passwords.

## 12. Relação com IA

Web Performance externo adiciona zero chamadas a LLM. Scores Lighthouse/CrUX nunca são produzidos ou recalculados por IA.

Qualquer interpretação futura por IA exige finalidade explícita, telemetria própria e contrato que preserve a medição-fonte.

## 13. Referências adicionais

- [../LIGHTHOUSE_CATEGORIES.md](../LIGHTHOUSE_CATEGORIES.md)
- [../LIGHTHOUSE_PAGESPEED_TRANSPORT.md](../LIGHTHOUSE_PAGESPEED_TRANSPORT.md)
- [../GOOGLE_API_KEYS.md](../GOOGLE_API_KEYS.md)
- [../EXTERNAL_METRICS_INTEGRITY.md](../EXTERNAL_METRICS_INTEGRITY.md)
