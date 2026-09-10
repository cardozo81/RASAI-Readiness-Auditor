# Acessibilidade automatizada e diagnósticos de qualidade Web

**Estado:** INTEGRADO / VIGENTE  
**Domínio:** Acessibilidade automatizada e diagnósticos Web  
**Dependências:** Web Performance externo + `REPORT-SITE-GEO-001`  
**Natureza:** projeção aditiva de evidência; sem alteração automática do scoring

## 1. Objetivo

Ampliar a utilidade operacional dos relatórios sem misturar conceitos que possuem autoridades, métricas e critérios distintos.

Domínios que permanecem separados:

```text
GEO / SARI
Acessibilidade
Web Performance
Synthetic Navigation Apdex
Synthetic User Experience Apdex
```

Interdependências podem ser exibidas por referência cruzada de evidência, mas não autorizam conversão automática de finding entre domínios, soma de scores, recalibração de `SCORE-GEO-004`, inferência causal não demonstrada ou promoção de ferramenta automatizada a certificação normativa.

## 2. Coleta compartilhada, semântica separada

Web Performance pode obter em uma chamada PageSpeed/Lighthouse categorias como:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

A camada de diagnósticos não cria nova chamada de rede para reutilizar esse payload. Ela lê evidência Web Performance persistida, inclusive `web_performance_observations.pagespeed_artifact_reference` e artifacts correspondentes.

Compartilhar payload é permitido. Compartilhar score/conclusão não é. `agentic-browsing`, quando presente, continua categoria experimental e não deve ser reinterpretada como score de Acessibilidade ou Performance tradicional.

## 3. Domínio SARI/GEO

Esta capacidade não altera:

- `BR-GEO-*` fora dos contratos explicitamente versionados;
- RuleExecution do domínio GEO;
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

### 4.2 Fontes

Fonte automatizada: Lighthouse Accessibility. Referências normativas/primárias: W3C WCAG 2.2, WAI-ARIA 1.2 e documentação oficial Lighthouse/Chrome.

### 4.3 Evidência por ocorrência

Quando presente no artifact Lighthouse, preservar audit id, título/descrição, selector, snippet/HTML, node label, explanation/failure summary, score do audit e URL/device.

O relatório não pode inventar selector ou snippet ausente.

### 4.4 Identificador de projeção

```text
A11Y-LH-<lighthouse-audit-id>
```

Esse identificador não representa Success Criterion WCAG.

### 4.5 Semântica de conformidade

Lighthouse Accessibility é uma ferramenta automatizada e não cobre toda avaliação manual necessária. Portanto:

```text
Conformidade WCAG: NÃO DETERMINADA
```

Lighthouse 100/100 não autoriza afirmar conformidade WCAG integral.

### 4.6 Correções ARIA

A camada não prescreve `aria-label` como solução universal. Para accessible name, considerar HTML nativo/texto, `<label>`, `aria-labelledby`, `aria-label` ou outros mecanismos previstos pelas especificações. Preferir semântica HTML nativa quando suficiente.

## 5. Domínio Web Performance

### 5.1 Página própria

```text
report/web-performance.html
```

Os diagnósticos adicionam interpretação técnica à página de Web Performance já existente, sem criar score próprio RASAi.

### 5.2 Campo e laboratório

```text
CrUX/Core Web Vitals -> dados de campo, experiência real agregada, p75
Lighthouse           -> dados de laboratório, execução controlada
```

### 5.3 Métricas principais

Campo: LCP p75, INP p75, CLS p75.

Laboratório: Performance score, FCP, Speed Index, LCP, TBT e CLS.

Accessibility score não é métrica de Performance; é projetado na página Acessibilidade.

### 5.4 Diagnósticos técnicos

A camada pode projetar audits/insights Lighthouse de render blocking, critical request/network dependency, LCP, layout shift, JavaScript/main thread, CSS, imagens, fontes, terceiros, server/document latency, DOM e cache quando a fonte fornece evidência.

### 5.5 Detalhe por ocorrência

Preservar somente quando fornecido pela fonte: resource URL, selector, snippet, node label, explanation, `wastedMs`, `wastedBytes`, `totalBytes` ou equivalente, duração e `displayValue`.

### 5.6 Primeira renderização

A camada não define arbitrariamente todos os elementos da primeira dobra como causa de performance. Evidências autorizadas incluem render-blocking requests, critical path, LCP element/resource, LCP breakdown/discovery, layout shift culprits e outros insights explícitos do Lighthouse.

## 6. Causalidade

A linguagem do relatório deve separar observação comprovada, recomendação técnica e causa não comprovada.

É aceitável informar que o Lighthouse identificou um recurso como render-blocking quando o artifact realmente contém esse diagnóstico. Não é aceitável afirmar que esse recurso é a única causa de LCP ruim sem evidência adicional.

## 7. Apdex e fronteira metodológica

Acessibilidade/Web Performance **não calculam Apdex a partir de**:

- LCP;
- INP;
- CLS;
- TBT;
- duração da chamada PageSpeed;
- uma única execução Lighthouse.

Synthetic Navigation Apdex é uma capacidade separada que possui Task, threshold `T`, população de amostras e persistência própria. Synthetic User Experience Apdex é outra capacidade separada e calibrável.

Assim:

```text
Lighthouse/CrUX                    -> não são convertidos em Apdex
Synthetic Navigation Apdex        -> pode calcular Apdex de NAVIGATION_LOAD quando habilitado
Synthetic User Experience Apdex   -> calcula sua ação sintética calibrada quando habilitado
```

Nenhum desses domínios altera automaticamente `SCORE-GEO-004`.

## 8. Navegação

Páginas especializadas aparecem no menu canônico somente quando materializadas. Ordem e rótulos devem ser produzidos pelo componente compartilhado de navegação, não por cada página isoladamente.

## 9. Referências externas e direitos autorais

> **Nota de direitos autorais, citação e tradução:** o material externo citado nesta seção permanece de titularidade de seu respectivo autor/mantenedor. Quando necessário para precisão técnica, o RASAi reproduz apenas o trecho estritamente necessário no idioma original, identificado como citação, seguido de tradução/adaptação para pt-BR. A tradução é informativa e não substitui o texto oficial; em caso de divergência, prevalece a fonte primária vinculada.

As referências abaixo sustentam os conceitos nos respectivos domínios e não homologam `SARI-001`/`SCORE-GEO-004`.

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

## 10. Critérios de conclusão

1. `accessibility.html` pode ser materializado sem nova chamada externa quando a evidência necessária já existe;
2. menu mostra Acessibilidade quando a página existe;
3. Accessibility score permanece separado do scorecard Performance;
4. selector/snippet Lighthouse são preservados quando existem;
5. ausência de selector não gera selector inventado;
6. checks manuais permanecem fora da conclusão automatizada;
7. relatório não afirma conformidade WCAG integral a partir de Lighthouse;
8. diagnósticos de performance preservam URL/savings quando fornecidos;
9. diagnósticos A11Y não vazam para Performance;
10. Lighthouse/CrUX não são convertidos em Apdex;
11. nenhuma alteração automática ocorre em `SCORE-GEO-004`;
12. reutilizar artifact não cria chamada LLM ou Google adicional;
13. referências oficiais permanecem identificadas;
14. suíte determinística aplicável permanece verde.