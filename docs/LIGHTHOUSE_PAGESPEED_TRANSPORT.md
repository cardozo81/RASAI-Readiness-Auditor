# Lighthouse via PageSpeed Insights

O provider de Web Performance do RASAi usa PageSpeed Insights como transporte para o resultado Lighthouse. No contrato vigente deste adapter, as categorias solicitáveis são:

```text
performance,accessibility,best-practices,seo
```

Essas quatro categorias formam o default de `RASAI_LIGHTHOUSE_CATEGORIES` e de `--lighthouse-categories` quando Web Performance está habilitado.

`agentic-browsing` não integra o request ao PageSpeed Insights. O campo `agentic_browsing_score` permanece somente como compatibilidade/evolução para uma futura fonte Lighthouse direta. Na ausência dessa fonte, o relatório deve apresentar a métrica como não disponível via provider atual, nunca como score zero.

Essa distinção não altera `SARI-001`: as categorias Lighthouse/Web Performance permanecem evidência contextual externa segundo os contratos já definidos pelo RASAi.
