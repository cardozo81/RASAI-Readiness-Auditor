# Categorias Lighthouse no RASAi

Web Performance usa o resultado Lighthouse transportado pelo PageSpeed Insights e mantém a metodologia externa separada do SARI-001.

## Categorias solicitadas por default

Quando Web Performance está habilitado e nenhuma lista explícita é fornecida, o RASAi solicita:

```text
performance
accessibility
best-practices
seo
agentic-browsing
```

A configuração equivalente é:

```text
--lighthouse-categories performance,accessibility,best-practices,seo,agentic-browsing
RASAI_LIGHTHOUSE_CATEGORIES=performance,accessibility,best-practices,seo,agentic-browsing
```

As cinco categorias são solicitadas na mesma chamada PageSpeed por contexto. Isso não cria uma chamada adicional por categoria.

## Proveniência

| Categoria | Proveniência | Papel no RASAi |
|---|---|---|
| Performance | Google Chrome Lighthouse | métrica externa complementar |
| Accessibility | Google Chrome Lighthouse | métrica externa complementar; não equivale a certificação WCAG |
| Best Practices | Google Chrome Lighthouse | métrica externa complementar |
| SEO | Google Chrome Lighthouse | SEO técnico automatizável; não equivale a SEO total ou ranking |
| Agentic Browsing | Google Chrome Lighthouse, experimental | métrica externa experimental e complementar |

O RASAi persiste os category scores em escala 0-100 e pode projetar os audit-level diagnostics disponíveis no artifact. Ele não recalcula a metodologia Lighthouse.

## Agentic Browsing

`agentic-browsing` é uma categoria experimental presente no Lighthouse. Por isso o RASAi:

- identifica explicitamente a natureza experimental;
- persiste `agentic_browsing_score` separadamente;
- exibe o resultado em Web Performance e no dashboard executivo como indicador complementar;
- disponibiliza o sinal para Monitoring/compare quando houver dado persistido;
- não converte esse score automaticamente em SARI-001 ou SCORE-GEO-004;
- mantém ausência do score como indisponibilidade de evidência, não como falha do website.

Referência primária do código Lighthouse:

https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js

## Compatibilidade histórica

Workspaces antigos podem não possuir `agentic_browsing_score`. A persistência faz migração aditiva do campo quando a camada Web Performance é aberta. Relatórios e Monitoring devem continuar funcionando quando o campo não existir ou não possuir valor.

A adição da categoria não altera auditorias históricas nem recalcula `audit.db` imutável sem uma nova execução.
