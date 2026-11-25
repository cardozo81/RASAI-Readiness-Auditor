# Categorias Lighthouse no RASAi

Web Performance usa o resultado Lighthouse transportado pelo PageSpeed Insights e mantém a metodologia externa separada do SARI-001.

## Categorias solicitadas por default

Quando Web Performance está habilitado e nenhuma lista explícita é fornecida, o adapter PageSpeed do RASAi solicita:

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
| Performance | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar |
| Accessibility | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar; não equivale a certificação WCAG |
| Best Practices | Google Chrome Lighthouse via PageSpeed Insights | métrica externa complementar |
| SEO | Google Chrome Lighthouse via PageSpeed Insights | SEO técnico automatizável; não equivale a SEO total ou ranking |
| Agentic Browsing | Google Chrome Lighthouse via PageSpeed Insights | categoria experimental complementar; composição pode mudar entre versões |

O RASAi persiste os category scores recebidos em escala 0-100 e pode projetar os audit-level diagnostics disponíveis no artifact. Ele não recalcula a metodologia Lighthouse.

O catálogo técnico `report-catalog/cat-04.html` detalha as categorias de laboratório. A apresentação executiva `report-presentation/performance.html` contextualiza as fontes de desempenho disponíveis. A cobertura de cada categoria deve ser verificada no registro da coleta. Veja o [guia dos relatórios](REPORT_GUIDE.md).

## Agentic Browsing

O [esquema oficial da API PageSpeed Insights v5](https://www.googleapis.com/discovery/v1/apis/pagespeedonline/v5/rest) lista `AGENTIC_BROWSING` entre os valores de `category`. O RASAi usa o identificador HTTP normalizado `agentic-browsing` e mantém o sinal estritamente fora do índice `SARI-001`.

Como a categoria continua experimental no Lighthouse:

- sua composição deve ser tratada como sujeita a mudança entre versões;
- ausência da categoria na resposta não é convertida em score zero ou falha do website;
- Performance, Accessibility, Best Practices e SEO válidos da mesma coleta permanecem utilizáveis;
- Monitoring/compare só usa o sinal quando houver valor persistido e contexto comparável;
- o score não é convertido em contribuição automática ao índice `SARI-001`.

Referências primárias:

- PageSpeed Insights API v5 / `runpagespeed`: <https://developers.google.com/speed/docs/insights/v5/reference/pagespeedapi/runpagespeed>
- cliente Google API para PageSpeed v5, enum `AGENTIC_BROWSING`: <https://googleapis.github.io/google-api-python-client/docs/dyn/pagespeedonline_v5.pagespeedapi.html>
- configuração Agentic no Lighthouse: <https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js>

## Persistência

`web_performance_observations` mantém `agentic_browsing_score` separado. O valor é persistido quando a resposta PageSpeed/Lighthouse o fornece. Se a categoria estiver ausente na resposta, permanece indisponível/`NULL`; isso não invalida outras categorias válidas da mesma execução.

A categoria Agentic Browsing não altera o índice `SARI-001`.

Consulte também [`LIGHTHOUSE_PAGESPEED_TRANSPORT.md`](LIGHTHOUSE_PAGESPEED_TRANSPORT.md).
