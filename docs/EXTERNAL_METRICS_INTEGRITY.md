# Integridade de PageSpeed, Lighthouse, CrUX e Acessibilidade

## Objetivo

Evitar que disponibilidade de transporte/API seja confundida com disponibilidade ou validade da medição externa.

O RASAi mantém estes domínios separados do `SARI-001`. Nenhum erro, ausência, quota ou timeout de PageSpeed/Lighthouse/CrUX reduz automaticamente o Score GEO.

## Proveniência

A coleta Web Performance usa a PageSpeed Insights API v5 como meio oficial para obter o `lighthouseResult` remoto. Dados reais de campo podem vir do payload PageSpeed/CrUX ou, conforme configuração, da CrUX API direta.

Referências oficiais:

- PageSpeed Insights API v5 - `pagespeedapi.runpagespeed`: https://developers.google.com/speed/docs/insights/rest/v5/pagespeedapi/runpagespeed
- PageSpeed Insights - Get Started: https://developers.google.com/speed/docs/insights/v5/get-started
- Lighthouse Accessibility scoring: https://developer.chrome.com/docs/lighthouse/accessibility/scoring
- Lighthouse Performance scoring: https://developer.chrome.com/docs/lighthouse/performance/performance-scoring

## Regra central

`PageSpeed HTTP/API SUCCESS` **não equivale** a `Lighthouse válido`.

Uma tentativa PageSpeed com HTTP 200 permanece registrada como sucesso de transporte/API para telemetria de chamada e quota. Depois da coleta, o gate `EXTERNAL-METRICS-INTEGRITY-1` valida o conteúdo efetivamente retornado.

### Lighthouse válido

Para a execução ser considerada válida para uma categoria solicitada:

1. `lighthouseResult` deve existir;
2. não pode existir `lighthouseResult.runtimeError` fatal (`code` diferente de `NO_ERROR`);
3. a categoria solicitada deve existir em `lighthouseResult.categories`;
4. o score da categoria deve ser numérico e estar no intervalo 0..1 esperado pela API.

Quando a própria PageSpeed API retorna `runtimeError`, a documentação oficial classifica esse estado como problema sério o suficiente para que o resultado Lighthouse seja descartado. O RASAi, portanto, remove da observação persistida os valores Lighthouse derivados desse resultado, mantendo o artifact bruto imutável para rastreabilidade.

### Categorias parcialmente disponíveis

Se algumas categorias solicitadas forem válidas e outras estiverem ausentes/inválidas:

- as categorias válidas são preservadas;
- as ausentes/inválidas permanecem `NULL`/não obtidas;
- a observação passa a `PARTIAL`;
- ausência nunca vira zero;
- o report informa explicitamente a cobertura por contexto.

## Acessibilidade

O RASAi **não recalcula** o score de Acessibilidade do Lighthouse.

O valor 0-100 mostrado em `accessibility.html` é a projeção do score da categoria `lighthouseResult.categories.accessibility.score`, multiplicado por 100 na camada Web Performance externo. A metodologia de ponderação pertence ao Lighthouse; a documentação oficial descreve o score como média ponderada das auditorias automatizadas e informa que auditorias manuais não participam dessa pontuação.

Regras de integridade:

- categoria `accessibility` ausente => `NÃO OBTIDA`, nunca zero;
- score inválido/ausente => `NÃO OBTIDA`;
- `runtimeError` Lighthouse fatal => score descartado;
- média entre páginas/dispositivos é somente estatística descritiva dos contextos com score válido;
- número de contexts válidos e total selecionado devem ser apresentados juntos;
- “nenhuma falha automatizada persistida” não pode ser interpretado como ausência de falhas se a categoria Accessibility daquele contexto não estiver marcada como válida;
- Lighthouse automatizado não equivale a conformidade WCAG; validação manual continua necessária.

## Performance Lighthouse

O score de Performance também é fornecido pelo Lighthouse. RASAi não recalcula seus pesos/curvas.

Quando o gate invalida o Lighthouse:

- `performance_score`, FCP, Speed Index, LCP lab, TBT e CLS lab são removidos da observação interpretável;
- o artifact PageSpeed original permanece preservado;
- erro de medição externa não vira `Performance = 0`;
- se CrUX permanecer válido, a observação fica `PARTIAL`, preservando somente field data;
- se nenhum dado externo utilizável restar, fica `UNAVAILABLE`.

## CrUX

CrUX é tratado como fonte de experiência real/field data e permanece separado de Lighthouse/laboratório.

Assim, é possível existir legitimamente:

- PageSpeed API HTTP 200;
- Lighthouse inválido por `runtimeError`;
- CrUX válido;
- observação geral `PARTIAL`.

Nesse cenário o report pode apresentar LCP/INP/CLS p75 válidos, mas deve mostrar Lighthouse e Accessibility como não obtidos.

## Artefatos e auditoria

O gate gera:

`artifacts/external-metrics-integrity.json`

Ele registra por URL/dispositivo:

- HTTP da tentativa PageSpeed;
- estado de validade Lighthouse;
- `runtimeError` quando existente;
- categorias solicitadas;
- categorias válidas;
- categorias ausentes/inválidas;
- validade de Performance;
- validade de Accessibility;
- disponibilidade de field data;
- status final da observação após reconciliação.

O `audit.log` recebe `EXTERNAL_METRICS_INTEGRITY_RECONCILED`.

## Interpretação operacional

Os reports devem distinguir quatro perguntas:

1. **A API respondeu?** - telemetria PageSpeed/CrUX.
2. **O Lighthouse é válido?** - validação de `lighthouseResult`/`runtimeError`/categorias.
3. **A categoria necessária foi obtida?** - Performance, Accessibility, Best Practices, SEO.
4. **Há field data válido?** - CrUX e cobertura LCP/INP/CLS.

Somente dados que passam pelo gate correspondente podem alimentar médias e indicadores apresentados como efetivamente obtidos.
