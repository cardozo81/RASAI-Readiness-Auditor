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
  inequívoco dentro do conjunto solicitado. No schema anterior, essa
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

Testes focados usam SQLite físico sintético, inclusive schema anterior
multi-query sem per-source query, troca de identidade AUD, dados
parciais/fora da janela, clocks/serp duplicados e invariância dos bytes
do banco. Nenhuma consulta Perplexity, SERP ou IA real foi executada.


## Contrato v2: presença exata da URL da própria AUD

O ledger `RASAI-GEO-PER-QUERY-304-ADVISORY-002` apresenta
`aud_target_scope` e, somente se existir **uma** linha
`audit_targets` pertencente à AUD com URL exata válida,
`aud_target_exact_url`. Para cada query com dois denominadores
fisicamente atribuíveis e escopo SERP observado, os campos
`target_url_exact_in_serp` e
`target_url_exact_in_perplexity` indicam presença da mesma URL
nos respectivos conjuntos de fontes.

`target_url_overlap_status` pode ser
`BOTH_SOURCE_SETS`, `SERP_SOURCE_SET_ONLY`,
`EXTERNAL_SOURCE_SET_ONLY` ou
`NEITHER_RETURNED_SOURCE_SET`. Sem alvo único comprovado,
sem per-source query em multi-query ou sem observação comparável,
o estado é `N/D`, e os dois indicadores são **nulos**, não
`false`. Alvos de outra AUD ou com URL malformada nunca
entram na conclusão.

A identidade exata das URLs segue o contrato GEO v8: não
presume redirecionamento, equivalência entre `/path` e
`/path/`, www/apex nem entre esquemas/portas.
Os indicadores descrevem unicamente fontes URL retornadas,
**não** ranqueamento, menção/citação em texto gerado,
participação GEO, causalidade, intenção ou visibilidade.
O runtime Perplexity, SERP, relatórios homologados,
SARI/SCORE-GEO e bancos persistidos continuam inalterados.

## Contrato v3 - selo local de origem SQLite

O contrato `RASAI-GEO-PER-QUERY-304-ADVISORY-003` protege as
métricas descritivas contra alteração concorrente da AUD entre
consultas SQLite em `immutable=1`. A rotina calcula SHA-256 dos bytes
físicos antes de iniciar as leituras e novamente antes de retornar
qualquer interseção ou denominador numérico. Limite: **256 MiB** para
leitura local; maior volume falha com N/D em vez de consulta ilimitada.

Mudança do hash/tamanho, symlink inseguro ou surgimento de arquivos
`audit.db-wal`, `audit.db-shm` ou `audit.db-journal` durante a
projeção bloqueiam a publicação de resultados numéricos, com
`AUD_SOURCE_CHANGED_DURING_READ` ou
`AUD_SQLITE_SIDECAR_APPEARED_DURING_READ`. O objeto deixa
`queries=[]` e `status=NOT_COMPARABLE`, sem conservar interseções
calculadas contra origem possivelmente mista.

Somente com duas leituras físicas coerentes aparecem
`source_audit_db_sha256`, `source_audit_db_bytes_verified` e
`source_audit_db_integrity_guard=DOUBLE_SHA256_MATCH`. Esse selo
comprova identidade dos bytes locais da AUD nos momentos medidos,
não assinatura de fornecedor, atualidade de dados SERP/Perplexity,
prova de ranking/citação gerativa nem causalidade.
`source_package_freshness_verified=false` continua preservado.

Não há alteração de GEO v8, coleta, AUD, snapshot, report writer,
SARI/SCORE-GEO, M23/M25, nem chamadas externas.

## v4: alternativas do mesmo host e hosts externos observados

O contrato consultivo `RASAI-GEO-PER-QUERY-304-ADVISORY-004`
incorpora, por consulta e somente quando a atribuição física
é comprovada, `serp_target_host_group` e
`external_target_host_group`. Cada conjunto apresenta:

- `same_host_alternative_urls`: URLs distintas da URL exata da AUD
  cujo hostname **exato** é igual ao da URL auditada.
- `other_host_distinct_urls`: URLs retornadas em hosts diferentes.
- `other_distinct_hosts`: quantidade de hostnames externos distintos.

A contagem é observacional, de URLs canônicas v8, nunca um indicador
de competidores comerciais conhecidos, ranqueamento, autoridade,
sucesso em busca generativa, intenção ou taxa de participação.
`www.example.com` não é igual a `example.com` sem prova física de
redirecionamento. Não há inferência de eTLD+1, nem agrupamento
por organização econômica. Um alvo físico ausente/ambíguo ou
query não atribuível gera N/D, sem números fabricados.

Também há proteção nova para consultas únicas: se existir coluna
`perplexity_search_sources.query` preenchida com uma consulta
**contraditória** à única consulta declarada do run, a associação
é recusada. Fontes sem coluna (ou com NULL explícito) em execução
de query única mantêm a compatibilidade histórica.

Nenhuma alteração em SERP, Perplexity Search, coletores,
SARI/SCORE-GEO, scoring, AUD ou snapshot GEO histórico;
o consumidor permanece estritamente offline e read-only.

## Contrato v5: proveniência por resultado do adaptador Perplexity

O adaptador canônico `search_intelligence.perplexity` conserva
os atributos adicionais de cada elemento `results[]` do fornecedor
em `perplexity_search_sources.source_metadata_json`. O consumidor
offline `RASAI-GEO-PER-QUERY-304-ADVISORY-005` passou a aceitar
uma **chave literal `query` dentro desse JSON por fonte** para
atribuição das URLs à consulta correta, sem criar coluna, migrar AUD,
invocar API ou alterar o motor homologado.

O cálculo multi-query só fica disponível quando **todas** as fontes
do run possuírem `query` explícita e válida, presente em
`perplexity_search_runs.query_json`; metadados sem query, JSON
malformado, tamanho excessivo ou divergência entre
`source_metadata_json.query` e eventual coluna `query`
invalidam a atribuição, com N/D em todos os denominadores.
Metadados por fonte com mais de 4 KiB também são recusados por
segurança. Em execução de consulta única, ausência do atributo
ainda admite o vínculo pelo run único, mas qualquer declaração
explícita contraditória invalida a associação.

**Limite fundamental:** não há contrato oficial assumido de que a
Perplexity Search API sempre retorna `results[].query`; quando
o fornecedor não fornece esse atributo, esta mudança não o
inventa por ordem, ranking, snippets, título ou posição. O atributo
é a informação persistida pelo cliente a partir da resposta externa,
não atestação independente de autenticidade, escopo de mercado,
idioma, dispositivo, intenção ou citação em uma resposta de IA.
Nenhum score, histórico GEO v8, SERP, SARI ou CONS é modificado.


## Prévia HTML consultiva por consulta (#304)

O contrato observacional existente `RASAI-GEO-PER-QUERY-304-ADVISORY-005`
agora pode ser apresentado diretamente no console como HTML independente,
com `--format html`. A opção padrão continua sendo `--format json`;
nenhuma resposta do provedor ou tabela da AUD é modificada.

```powershell
python -m rasai.geo_query_ledger_304 .\audits\AUD-EXEMPLO --format html > geo-por-consulta.html
```

A visualização separa explicitamente denominadores, interseção,
URLs exclusivas, taxas relativas e presença exata da URL auditada
nos dois conjuntos observados, mantendo classificação branded
somente quando declarada pelo operador. A indicação `N/D` não
é convertida em zero, ausência de citação ou ausência de visibilidade.
HTML externo é escapado; consultas e URLs de origem não são
interpretadas como elementos, scripts ou links executáveis.

Layout responsivo e impressão são suportados sem JavaScript. O
artefato é uma **prévia consultiva externa**, não injeta GEO em
`report.html`, `directed-analysis.html`, SARI/SCORE-GEO ou CONS,
nem compara automaticamente intenção, idioma, dispositivo, ranking
e menções em texto gerativo. A gravação opcional por redirecionamento
é decisão explícita do operador, fora da AUD.


## Entrada pública read-only pelo comando `rasai` (12/10/2026)

O mesmo inventário offline pode ser consultado sem importar o runtime
de auditoria, coletores ou credenciais dos providers:

```powershell
rasai geo-query-ledger .\audits\AUD-EXEMPLO --format html
rasai geo-query-report .\audits\AUD-EXEMPLO --format json
```

A saída HTML é um documento acessível e independente para leitura humana,
**não** uma escrita em `report-catalog/geo.html`, nem uma mutação de
relatório já homologado. O roteador apenas delega ao consumer físico
`geo_query_ledger_304`. A comparação por consulta continua
`DESCRIPTIVE_ONLY`/N/D e não prova mesma população de mercado, idioma,
device, intenção, nem citação generativa. Não dispara Search API/IA.


## Gate de consistência do escopo SERP por consulta (12/10/2026)

Quando a AUD contém mais de uma observação `OBSERVED_API/OBSERVED`
para a mesma consulta dentro da janela física de 24 horas da busca
externa, o ledger #304 exige que **todas as observações elegíveis**
concordem exatamente em `engine`, `country`, `region`,
`language` e `device`. Se algum campo diferir, a escolha da
observação mais próxima no tempo seria uma seleção arbitrária de
universos diferentes; a consulta afetada agora retorna
`AMBIGUOUS_SERP_MARKET_LANGUAGE_DEVICE_SCOPE` com taxas,
denominadores e presença da URL em N/D.

Outras consultas independentes permanecem elegíveis quando seus
respectivos escopos físicos forem coerentes. Duas observações
com o **mesmo** escopo e timestamps válidos ainda usam a
seleção cronológica determinística existente; empates continuam
rejeitados. Isso não prova equivalência do mercado, idioma,
dispositivo ou intenção **externa** da Perplexity, cujas flags
permanecem `false`; não altera scores, SERP runtime, coleta,
persistência ou proveniência de nenhuma AUD.


## Integridade dos denominadores por consulta (12/10/2026)

O comparador consultivo não pode descartar silenciosamente uma URL de origem
inválida e calcular taxas sobre as URLs restantes como se a amostra física
estivesse completa. Se pelo menos uma URL persistida da Perplexity ou da
observação SERP selecionada não possuir identidade HTTP(S) canônica válida,
a consulta afetada retorna `NOT_COMPARABLE`, respectivamente
`EXTERNAL_SOURCE_URL_IDENTITY_UNVERIFIABLE` ou
`SERP_SOURCE_URL_IDENTITY_UNVERIFIABLE`. Denominadores, taxas e presença
do alvo permanecem N/D; nenhuma URL é corrigida por heurística.

A proteção é estritamente por consulta, depois da atribuição explícita das
fontes; consultas independentes com URLs íntegros conservam apenas métricas
`DESCRIPTIVE_ONLY`. Amostras inteiramente sem URL válida mantêm a
classificação `NO_VALID_*_URL_DENOMINATOR` existente. Testes de regressão
SQLite offline demonstram mistura de URLs válidas/inválidas, ausência de
escritas, dupla checagem SHA-256 e preservação de consultas saudáveis.
Não altera motor SERP, Search API, proveniência, coleta, GEO v8, score ou IA.
