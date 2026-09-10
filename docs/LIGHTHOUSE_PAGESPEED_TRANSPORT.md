# Lighthouse via PageSpeed Insights

O provider de Web Performance do RASAi usa PageSpeed Insights como transporte para o resultado Lighthouse. No contrato vigente deste adapter, as categorias solicitáveis e usadas por default são:

```text
performance,accessibility,best-practices,seo,agentic-browsing
```

Essas cinco categorias formam o default de `RASAI_LIGHTHOUSE_CATEGORIES` e de `--lighthouse-categories` quando Web Performance está habilitado.

A API PageSpeed Insights v5 expõe atualmente `AGENTIC_BROWSING` como valor aceito do parâmetro repetível `category`. O RASAi solicita a categoria junto das demais na mesma chamada por contexto; isso não cria uma chamada PageSpeed adicional.

Agentic Browsing continua experimental no Lighthouse e sua composição pode mudar entre versões. Portanto, o campo `agentic_browsing_score` permanece semanticamente separado das categorias estáveis: se a resposta não materializar a categoria, o valor permanece indisponível/`NULL`, nunca é convertido em zero e não invalida Performance, Accessibility, Best Practices ou SEO recebidos na mesma coleta.

Essa evolução do transporte não altera `SARI-001`: todas as categorias Lighthouse/Web Performance permanecem evidência contextual externa e não entram automaticamente em `SCORE-GEO-004`.

Referências primárias:

- PageSpeed Insights API v5: <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- cliente Google API com enum `AGENTIC_BROWSING`: <https://googleapis.github.io/google-api-python-client/docs/dyn/pagespeedonline_v5.pagespeedapi.html>
- configuração Agentic do Lighthouse: <https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js>
