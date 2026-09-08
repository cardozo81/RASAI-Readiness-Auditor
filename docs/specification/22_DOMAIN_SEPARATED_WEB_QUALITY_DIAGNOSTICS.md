# Acessibilidade automatizada e diagnósticos Web - Diagnósticos de Qualidade Web com Fronteiras de Domínio

**Status:** INTEGRADO
**Domínio:** `Acessibilidade automatizada e diagnósticos Web`
**Dependências:** Web Performance externo + REPORT-SITE-GEO-001
**Natureza:** projeção aditiva de evidência; sem alteração de scoring GEO

## 1. Objetivo

Acessibilidade automatizada e diagnósticos Web amplia a utilidade operacional dos relatórios sem misturar conceitos que possuem autoridades, métricas e critérios distintos.

Domínios obrigatoriamente separados no escopo Acessibilidade automatizada e diagnósticos Web:

```text
GEO
Acessibilidade
Web Performance
```

Interdependências podem ser exibidas por cross-reference de evidência, mas não autorizam conversão automática de finding entre domínios, soma de scores, recalibração de `SCORE-GEO-004`, inferência causal não demonstrada ou promoção de ferramenta automatizada a certificação normativa.

Synthetic Navigation Apdex, integrado posteriormente, adiciona um quarto domínio separado de Web Performance sintética: Synthetic Navigation Apdex. Essa evolução **não altera as fronteiras normativas do Acessibilidade automatizada e diagnósticos Web**.

## 2. Princípio de coleta compartilhada, semântica separada

Web Performance externo pode obter em uma única chamada PageSpeed/Lighthouse categorias como:

```text
performance
accessibility
best-practices
seo
```

Acessibilidade automatizada e diagnósticos Web não cria nova chamada de rede. Ele lê somente evidência Web Performance externo persistida, especialmente `web_performance_observations.pagespeed_artifact_reference` e `artifacts/web-performance/*.pagespeed.json`.

Compartilhar payload é permitido. Compartilhar score/conclusão não é.

## 3. Domínio GEO

Acessibilidade automatizada e diagnósticos Web não altera:

- `BR-GEO-*`;
- RuleExecution;
- Finding GEO;
- Recommendation GEO;
- severity/priority GEO;
- `SCORE-GEO-004`;
- Coverage;
- Confidence;
- Consolidation.

Nenhum audit Lighthouse de acessibilidade ou performance vira BR-GEO automaticamente.

## 4. Domínio Acessibilidade

### 4.1 Página própria

```text
report/accessibility.html
```

### 4.2 Fonte

Fonte automatizada: Lighthouse Accessibility. Autoridades de referência: W3C WCAG 2.2, WAI-ARIA 1.2 e documentação oficial Lighthouse/Chrome.

### 4.3 Evidência por ocorrência

Quando presente no artifact Lighthouse, preservar audit id, título/descrição, selector, snippet/HTML, node label, explanation/failure summary, score do audit e URL/device.

O relatório não pode inventar selector ou snippet ausente.

### 4.4 Identificador de projeção

```text
A11Y-LH-<lighthouse-audit-id>
```

Esse identificador não representa Success Criterion WCAG.

### 4.5 Semântica de conformidade

Lighthouse Accessibility é ferramenta automatizada e não cobre toda avaliação manual necessária. Portanto:

```text
Conformidade WCAG: NÃO DETERMINADA
```

Lighthouse 100/100 não autoriza afirmar conformidade WCAG.

### 4.6 Correções ARIA

Acessibilidade automatizada e diagnósticos Web não prescreve `aria-label` como solução universal. Para accessible name, considerar HTML nativo/texto, `<label>`, `aria-labelledby`, `aria-label` ou outros mecanismos previstos pelas especificações. Preferir semântica HTML nativa quando suficiente.

## 5. Domínio Web Performance

### 5.1 Página própria

```text
report/web-performance.html
```

Acessibilidade automatizada e diagnósticos Web adiciona diagnóstico técnico à página Web Performance externo existente, sem criar score próprio RASAi.

### 5.2 Campo e laboratório

```text
CrUX/Core Web Vitals -> field data, experiência agregada real, p75
Lighthouse           -> lab data, execução controlada
```

### 5.3 Métricas principais

Campo: LCP p75, INP p75, CLS p75.

Laboratório: Performance score, FCP, Speed Index, LCP, TBT e CLS.

Accessibility score não é métrica de Performance; é projetado na página Acessibilidade.

### 5.4 Diagnósticos técnicos

Acessibilidade automatizada e diagnósticos Web pode projetar audits/insights Lighthouse de render blocking, critical request/network dependency, LCP, layout shift, JavaScript/main thread, CSS, imagens, fontes, terceiros, server/document latency, DOM e cache quando a fonte fornece evidência.

### 5.5 Detalhe por ocorrência

Preservar somente quando fornecido pela fonte: resource URL, selector, snippet, node label, explanation, `wastedMs`, `wastedBytes`, `totalBytes`/equivalente, duração e `displayValue`.

### 5.6 Primeira renderização

Acessibilidade automatizada e diagnósticos Web não define arbitrariamente todos os elementos da primeira dobra como causa de performance. Evidências autorizadas incluem render-blocking requests, critical path, LCP element/resource, LCP breakdown/discovery, layout shift culprits e outros insights explícitos do Lighthouse.

## 6. Causalidade

A linguagem do report separa observação comprovada, recomendação técnica e causa não comprovada.

Exemplo permitido quando sustentado pela fonte:

```text
O Lighthouse identificou app.css como render-blocking.
```

Exemplo não permitido sem evidência adicional:

```text
app.css é a única causa do LCP ruim.
```

## 7. Apdex - fronteira Acessibilidade automatizada e diagnósticos Web e evolução Synthetic Navigation Apdex

### 7.1 Regra Acessibilidade automatizada e diagnósticos Web permanece válida

Acessibilidade automatizada e diagnósticos Web **não calcula Apdex a partir de**:

- LCP;
- INP;
- CLS;
- TBT;
- duração da chamada PageSpeed;
- uma única execução Lighthouse.

A especificação Apdex exige população de amostras de tempo de resposta de Task/Task Chain, threshold `T` explícito, `F = 4T` e contagem Satisfied/Tolerating/Frustrated.

```text
Apdex(T) = (Satisfied + Tolerating / 2) / Total Samples
```

Logo, **dentro do domínio Web Performance externo/Acessibilidade automatizada e diagnósticos Web**, quando não há Synthetic Navigation Apdex materializado, a leitura continua:

```text
Apdex: NÃO CALCULADO POR Web Performance externo/Acessibilidade automatizada e diagnósticos Web
```

Isso significa apenas que Lighthouse/CrUX não são usados como substitutos de Apdex.

### 7.2 Synthetic Navigation Apdex integrado posteriormente

Synthetic Navigation Apdex passou a fornecer separadamente os insumos que o Acessibilidade automatizada e diagnósticos Web deliberadamente não possuía:

- Task `NAVIGATION_LOAD` definida;
- início/fim da Task;
- navegações repetidas em Chromium;
- `T` explícito;
- população de samples por URL/device;
- tratamento de erros e amostras inválidas;
- persistência própria;
- `report/apdex.html`.

Portanto, após Synthetic Navigation Apdex:

```text
Web Performance externo/Acessibilidade automatizada e diagnósticos Web -> continuam sem inferir Apdex de Lighthouse/CrUX
Synthetic Navigation Apdex     -> pode calcular Synthetic Navigation Apdex quando explicitamente habilitado
```

Synthetic Navigation Apdex não altera `SCORE-GEO-004` e não transforma Apdex em Finding GEO.

Referência normativa específica: `23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md`.

## 8. Navegação

Ordem canônica relevante, considerando Synthetic Navigation Apdex quando materializado:

```text
Conteúdo e JSON-LD
Acessibilidade
Web Performance
Apdex              # somente quando apdex.html existe
Uso de IA
```

## 9. Referências públicas e oficiais

### Acessibilidade

- <https://www.w3.org/TR/WCAG22/>
- <https://www.w3.org/WAI/WCAG22/Understanding/name-role-value>
- <https://www.w3.org/TR/wai-aria-1.2/>
- <https://developer.chrome.com/docs/lighthouse/accessibility/scoring>
- <https://developer.chrome.com/docs/lighthouse/overview>

### Performance

- <https://developer.chrome.com/docs/performance/insights>
- <https://developer.chrome.com/docs/performance/insights/render-blocking>
- <https://developer.chrome.com/docs/performance/insights/network-dependency-tree>
- <https://developer.chrome.com/docs/lighthouse/performance/performance-scoring>
- <https://web.dev/articles/vitals>
- <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- <https://developer.chrome.com/docs/crux/api/>

### Apdex

- <https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf>

## 10. Critérios de conclusão Acessibilidade automatizada e diagnósticos Web

1. `accessibility.html` materializado sem nova chamada externa;
2. menu canônico mostra Acessibilidade quando a página existe;
3. Accessibility score separado do scorecard Performance;
4. selector/snippet Lighthouse preservados quando existem;
5. ausência de selector não gera selector inventado;
6. checks manuais permanecem fora da conclusão automatizada;
7. report não afirma conformidade WCAG;
8. diagnósticos de performance preservam URL/savings quando fornecidos;
9. diagnósticos A11Y não vazam para Performance;
10. Acessibilidade automatizada e diagnósticos Web não calcula Apdex de Lighthouse/CrUX;
11. nenhuma alteração em `SCORE-GEO-004`;
12. Acessibilidade automatizada e diagnósticos Web não cria chamada LLM ou Google adicional;
13. referências oficiais acessíveis;
14. suíte determinística permanece verde.

A integração posterior de Synthetic Navigation Apdex satisfaz um domínio adicional sem reabrir ou invalidar esses critérios.
