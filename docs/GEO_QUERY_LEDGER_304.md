# #304 - Inventário GEO por consulta com atribuição física

O consumidor local `python -m rasai.geo_query_ledger_304 AUD-...` é
**consultivo, estritamente offline e read-only**. Não altera os snapshots
`RASAI-GEO-OBSERVATION-8`, não cria relatórios de auditoria nem modifica
M23/M25, SARI, SCORE-GEO, Search API, SERP runtime, orquestrador ou CONS.

## Contrato observacional

- Exige uma AUD física COMPLETE, sem links simbólicos, sem sidecars SQLite
  pendentes, e seleciona a última execução de Search API por cronologia
  com offset explícito. Um resultado anterior SUCCESS não encobre
  tentativa mais recente falha ou relógios inconclusivos.
- Aceita de 1 a 10 queries distintas realmente persistidas no `query_json`
  daquela execução, não inferidas a partir de snippets.
- Na **consulta única**, as URLs do run pertencem a essa query.
  Em **multi-query**, só calcula métricas se cada linha persistida
  `perplexity_search_sources` contiver a coluna `query`, com valor
  inequívoco dentro do conjunto solicitado. No schema legado, essa
  coluna não existe: o resultado é `MULTI_QUERY_SOURCE_MAPPING_MISSING`,
  e `common_urls/denominators/rates` ficam nulos.
- A observação SERP deve pertencer à mesma AUD, ser
  `OBSERVED_API/OBSERVED`, registrar a query textual equivalente e
  trazer os cinco campos de escopo `engine/country/region/language/device`,
  além de relógio UTC compatível em até 24h. Seleção pelo menor intervalo
  temporal, nunca por ordem textual do timestamp. Empates de mesma
  hora/gap ou `observation_id` repetido são rejeitados.
- Para cada query válida, os denominadores são conjuntos distintos de
  URLs válidas com identidade exata v8 (esquema, hostname, porta,
  path e query string). Reporta interseção, exclusivos e rates separados
  SERP/Perplexity, além de Jaccard, todos **descritivos**.
- Uma marcação opcional `--declared-branded-query "consulta"` é
  **declaração do operador**, nunca classificação detectada ou evidência
  de similaridade de intenção entre provedores. Query não presente no
  run causa erro, sem leitura externa.

A presença de mesma query textual e proximidade no tempo **não prova**
mesmo mercado, idioma, dispositivo, ranking, intenção ou citação em
resposta gerativa: todos esses atributos conservam flags de
comprovação `false`. Sem essas evidências, nenhum delta causal,
priorização automática ou tendência longitudinal é permitido.

Exemplo local, sem rede:

```powershell
python -m rasai.geo_query_ledger_304 `
  .\audits\AUD-EXEMPLO `
  --declared-branded-query "seguro bradesco"
```

Testes focados usam SQLite físico sintético, inclusive schema legada
multi-query sem per-source query, troca de identidade AUD, dados
parciais/fora da janela, clocks/serp duplicados e invariância dos bytes
do banco. Nenhuma consulta Perplexity, SERP ou IA real foi executada.
