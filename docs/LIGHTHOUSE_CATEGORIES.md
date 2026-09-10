# Categorias Lighthouse no RASAi

Web Performance usa o resultado Lighthouse transportado pelo PageSpeed Insights e mantém a metodologia externa separada do SARI-001.

## Categorias solicitadas por default

Quando Web Performance está habilitado e nenhuma lista explícita é fornecida, o adapter PageSpeed do RASAi solicita:

```text
performance
accessibility
best-practices
seo
```

A configuração equivalente é:

```text
--lighthouse-categories performance,accessibility,best-practices,seo
RASAI_LIGHTHOUSE_CATEGORIES=performance,accessibility,best-practices,seo
```

As quatro categorias são solicitadas na mesma chamada PageSpeed por contexto. Isso não cria uma chamada adicional por categoria.

## Proveniência

| Categoria | Proveniência | Papel no RASAi |
|---|---|---|
| Performance | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar |
| Accessibility | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar; não equivale a certificação WCAG |
| Best Practices | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar |
| SEO | Google Chrome Lighthouse via PageSpeed Insights | SEO técnico automatizável; não equivale a SEO total ou ranking |
| Agentic Browsing | Google Chrome Lighthouse, fonte separada/futura | métrica externa experimental e complementar quando houver fonte compatível |

O RASAi persiste os category scores recebidos em escala 0-100 e pode projetar os audit-level diagnostics disponíveis no artifact. Ele não recalcula a metodologia Lighthouse.

## Agentic Browsing

`agentic-browsing` não é enviado pelo adapter PageSpeed vigente. Por isso o RASAi:

- não inclui a categoria no default nem na lista aceita do transporte PageSpeed;
- mantém `agentic_browsing_score` como campo de compatibilidade/evolução para uma fonte Lighthouse direta separada;
- identifica explicitamente a natureza experimental quando a métrica existir;
- disponibiliza o sinal para Monitoring/compare somente quando houver dado persistido por uma fonte compatível;
- não converte esse score automaticamente em SARI-001 ou SCORE-GEO-004;
- trata ausência do score como indisponibilidade de evidência, nunca como score zero ou falha do website.

Referência primária do código Lighthouse para a configuração experimental:

https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js

## Persistência

`web_performance_observations` mantém `agentic_browsing_score` como campo separado por compatibilidade. Na execução atual via PageSpeed, o valor permanece indisponível/`NULL`; isso não invalida Performance, Accessibility, Best Practices ou SEO válidos da mesma execução.

A categoria Agentic Browsing não altera `SARI-001` nem `SCORE-GEO-004`.

Consulte também [`LIGHTHOUSE_PAGESPEED_TRANSPORT.md`](LIGHTHOUSE_PAGESPEED_TRANSPORT.md).
