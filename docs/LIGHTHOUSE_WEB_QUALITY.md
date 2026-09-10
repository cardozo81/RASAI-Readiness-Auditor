# Lighthouse Web Quality no RASAi

## Objetivo

Este documento define o contrato público do RASAi para as cinco categorias solicitadas do Google Chrome Lighthouse e para os Core Web Vitals provenientes de CrUX.

O objetivo é impedir três ambiguidades:

1. confundir um score externo Lighthouse com um índice proprietário RASAi;
2. confundir `SEO` do Lighthouse com uma avaliação integral de SEO, ranking ou visibilidade em SERP;
3. confundir uma categoria Lighthouse com métricas ou diagnósticos que pertencem a outra categoria.

## Regra arquitetural

O RASAi usa PageSpeed Insights como transporte para obter o `lighthouseResult` e pode obter field data pelo payload PageSpeed/CrUX ou pela CrUX API direta.

A camada RASAi:

- solicita as categorias configuradas;
- persiste o artifact bruto PageSpeed;
- valida integridade do `lighthouseResult`;
- persiste os scores válidos em escala 0-100;
- projeta os resultados no HTML;
- expõe proveniência e rastreabilidade;
- pode selecionar checks/diagnósticos do artifact para facilitar interpretação.

A camada RASAi **não**:

- recalcula pesos ou curvas do Lighthouse;
- combina as categorias Lighthouse em um novo score;
- transforma Lighthouse em `SARI-001` ou `SCORE-GEO-004`;
- transforma `SEO` Lighthouse em ranking, tráfego, autoridade, posição SERP ou probabilidade de citação por IA;
- transforma Lighthouse Accessibility em declaração de conformidade WCAG;
- transforma Agentic Browsing em requisito universal de Search & AI readiness;
- transforma ausência de categoria, runtime error ou indisponibilidade de API em score zero.

## Categorias Lighthouse coletadas

O default vigente de Web Performance solicita:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

A origem técnica é:

```text
lighthouseResult.categories.performance.score
lighthouseResult.categories.accessibility.score
lighthouseResult.categories.best-practices.score
lighthouseResult.categories.seo.score
lighthouseResult.categories["agentic-browsing"].score
```

A API fornece score de categoria em escala `0..1`. O RASAi persiste a projeção `0..100` nas colunas:

```text
performance_score
accessibility_score
best_practices_score
seo_score
agentic_browsing_score
```

Multiplicar por 100 é apenas normalização de apresentação. Não existe reponderação ou fórmula RASAi aplicada ao score Lighthouse.

As cinco categorias são solicitadas na mesma chamada PageSpeed por contexto. A categoria `agentic-browsing` é tratada como experimental; se o provider/versão da execução não a materializar, a ausência permanece como evidência indisponível e não como score zero.

## Performance · Lighthouse

**Proprietário/metodologia:** Google Chrome Lighthouse.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC`.

**Página principal:** `report/web-performance.html`.

O score apresentado como `Performance · Lighthouse` vem de:

```text
lighthouseResult.categories.performance.score
```

Métricas de laboratório associadas à leitura de Performance:

- First Contentful Paint (`FCP lab`);
- Speed Index;
- Largest Contentful Paint de laboratório (`LCP lab`);
- Total Blocking Time (`TBT lab`);
- Cumulative Layout Shift de laboratório (`CLS lab`).

Essas métricas não devem aparecer como detalhes técnicos de Accessibility, Best Practices, SEO ou Agentic Browsing.

Referência oficial:

- https://developer.chrome.com/docs/lighthouse/performance/performance-scoring

## Accessibility · Lighthouse

**Proprietário/metodologia:** Google Chrome Lighthouse.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC`.

**Página analítica detalhada:** `report/accessibility.html`.

**Resumo também visível:** `report/web-performance.html`, para que o conjunto das categorias Lighthouse seja reconhecível e comparável no mesmo contexto URL/dispositivo.

O score vem de:

```text
lighthouseResult.categories.accessibility.score
```

O RASAi não recalcula esse valor. A página de Acessibilidade continua responsável pelos findings automatizados, evidências, referência WCAG aplicável e pela advertência de que automação Lighthouse não equivale a certificação/conformidade integral WCAG.

Referências oficiais:

- https://developer.chrome.com/docs/lighthouse/accessibility/scoring
- https://www.w3.org/TR/WCAG22/

## Best Practices · Lighthouse

**Proprietário/metodologia:** Google Chrome Lighthouse.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC`.

**Página principal:** `report/web-performance.html`.

O score vem de:

```text
lighthouseResult.categories.best-practices.score
```

O RASAi trata Best Practices como indicador complementar de qualidade técnica. Ele não recebe peso automático em `SARI-001`/`SCORE-GEO-004`.

Quando o artifact contém `auditRefs` e `audits`, o HTML pode mostrar, de forma explicável:

- quantidade de checks aprovados;
- quantidade de checks reprovados;
- checks manuais;
- checks não aplicáveis;
- `audit id` do Lighthouse;
- score do check;
- peso informado no `auditRef`, quando presente;
- título, `displayValue`, descrição e explicação fornecidos pelo Lighthouse.

Essa projeção detalhada é uma camada de leitura RASAi sobre evidência Lighthouse. Ela **não cria um segundo score Best Practices**.

Referência oficial:

- https://developer.chrome.com/docs/lighthouse/best-practices/

## SEO técnico · Lighthouse

**Proprietário/metodologia:** Google Chrome Lighthouse.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC`.

**Página principal:** `report/web-performance.html`.

O score vem de:

```text
lighthouseResult.categories.seo.score
```

O rótulo público adotado pelo RASAi é **SEO técnico · Lighthouse** para reduzir risco de interpretação incorreta.

O score representa o conjunto automatizado de auditorias SEO suportadas pelo Lighthouse naquela versão/execução. Ele não representa, isoladamente:

- qualidade integral do conteúdo;
- relevância semântica para uma query específica;
- autoridade;
- backlinks;
- tráfego orgânico;
- posição em SERP;
- Search Console;
- competitividade de uma consulta;
- E-E-A-T como score;
- desempenho comercial;
- Search & AI readiness;
- probabilidade de ser citado por um LLM ou mecanismo generativo.

Quando o artifact contém `auditRefs` e `audits`, `web-performance.html` pode detalhar checks reprovados exatamente como evidência Lighthouse, sem promovê-los a finding proprietário do RASAi.

Search Intelligence/SERP permanece um domínio separado. Uma posição observada em mecanismo de busca não pode ser inferida do score SEO Lighthouse.

Referência oficial:

- https://developer.chrome.com/docs/lighthouse/seo/

## Agentic Browsing · Lighthouse (experimental)

**Proprietário/metodologia:** Google Chrome Lighthouse.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC` experimental.

**Página principal:** `report/web-performance.html`.

O score vem de:

```text
lighthouseResult.categories["agentic-browsing"].score
```

O RASAi persiste esse valor em `agentic_browsing_score`, quando presente, e o apresenta separadamente. O sinal é complementar e experimental. Ele não representa, isoladamente:

- capacidade universal de qualquer agente ou LLM navegar no site;
- conformidade com um padrão web obrigatório;
- indexabilidade ou ranking em Search;
- probabilidade de citação por IA;
- SARI-001 ou SCORE-GEO-004.

Ausência da categoria em uma execução válida não é convertida em zero e pode coexistir com as demais categorias Lighthouse válidas.

Referência primária do código Lighthouse:

- https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js

## Core Web Vitals · CrUX

**Proprietário/metodologia:** Google Chrome / Web Vitals e Chrome UX Report.

**Classificação RASAi:** `EXTERNAL_DEFINED_METRIC`.

**Página principal:** `report/web-performance.html`.

Field data permanece separado do laboratório Lighthouse. O RASAi apresenta, quando materializados:

- LCP p75;
- INP p75;
- CLS p75;
- source;
- scope URL/origin;
- avaliação conjunta quando a cobertura permite.

Ausência de amostra não é falha do website e não vira zero.

Referências oficiais:

- https://web.dev/articles/vitals
- https://developer.chrome.com/docs/crux/api/

## Integridade e disponibilidade

`PageSpeed HTTP 200` não significa automaticamente `Lighthouse válido`.

O gate de integridade externo valida:

1. presença de `lighthouseResult`;
2. ausência de `runtimeError` fatal;
3. presença de cada categoria solicitada;
4. score numérico válido em `0..1`.

Para categoria ausente/inválida:

- o score interpretável permanece ausente/`NULL`;
- ausência não vira zero;
- categorias válidas do mesmo contexto podem ser preservadas;
- o contexto pode ficar `PARTIAL`;
- o artifact bruto permanece disponível para auditoria.

Consulte também `EXTERNAL_METRICS_INTEGRITY.md`.

## Contrato do HTML

`report/web-performance.html` deve deixar explícito, no mesmo contexto URL/dispositivo:

1. os cinco scores Lighthouse quando válidos, com Agentic Browsing identificado como experimental;
2. o proprietário/metodologia de cada categoria;
3. a origem técnica do dado;
4. a diferença entre score de categoria e detalhes técnicos;
5. as métricas lab que pertencem a Performance;
6. os Core Web Vitals que pertencem ao CrUX/field data;
7. a página detalhada de Accessibility;
8. os checks reprovados de Best Practices, SEO e Agentic Browsing quando existentes no artifact;
9. Lighthouse version, fetch time e artifact de origem;
10. erros/limitações da coleta;
11. independência em relação a `SARI-001`, `SCORE-GEO-004` e Search Intelligence/SERP.

`report/index.html` pode resumir a média descritiva dos contextos válidos para cada categoria disponível. Essa média não deve ser renomeada como “score do site” nem usada para produzir score composto. Agentic Browsing deve continuar explicitamente marcado como experimental.

`report/references.html` deve incluir referências específicas de Performance, Accessibility, Best Practices, SEO, Agentic Browsing, PageSpeed, CrUX e Core Web Vitals.

## Relação com Search Intelligence / SERP

A integração de Search Intelligence/SERP é arquiteturalmente independente desta camada.

```text
Lighthouse SEO técnico
= checks automatizados do documento/execução Lighthouse

Lighthouse Agentic Browsing
= categoria experimental externa de qualidade para navegação agentic

Search Intelligence / SERP
= observação externa de resultados, posições, concorrentes e evidências de busca conforme provider/protocolo

SARI-001 / SCORE-GEO-004
= readiness proprietário do RASAi
```

Não existe conversão automática entre esses domínios.

## Persistência e compatibilidade

`web_performance_observations` persiste as cinco colunas de score, incluindo `agentic_browsing_score`. Workspaces históricos podem não possuir esse campo; a persistência aditiva e o reporting devem manter compatibilidade e tratar valor ausente como indisponível.

Nenhuma chamada externa adicional por categoria é necessária quando Performance, Accessibility, Best Practices, SEO e Agentic Browsing fazem parte da mesma execução PageSpeed/Lighthouse configurada.

## Referências primárias

- Lighthouse overview: https://developer.chrome.com/docs/lighthouse/overview/
- Lighthouse Performance: https://developer.chrome.com/docs/lighthouse/performance/performance-scoring
- Lighthouse Accessibility: https://developer.chrome.com/docs/lighthouse/accessibility/scoring
- Lighthouse Best Practices: https://developer.chrome.com/docs/lighthouse/best-practices/
- Lighthouse SEO: https://developer.chrome.com/docs/lighthouse/seo/
- Lighthouse Agentic Browsing config: https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js
- PageSpeed Insights API v5: https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed
- Chrome UX Report API: https://developer.chrome.com/docs/crux/api/
- Core Web Vitals: https://web.dev/articles/vitals
