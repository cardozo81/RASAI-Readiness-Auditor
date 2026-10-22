# #304 - Inventário GEO por consulta com atribuição física

O consumidor local `python -m rasai.geo_query_ledger AUD-...` é
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
python -m rasai.geo_query_ledger `
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
python -m rasai.geo_query_ledger .\audits\AUD-EXEMPLO --format html > geo-por-consulta.html
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
`geo_query_ledger`. A comparação por consulta continua
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


## Integridade do streaming SHA-256 físico (12/10/2026)

A prévia GEO por consulta recusa uma verificação física quando a quantidade
de bytes realmente lida para SHA-256 diverge do tamanho do `audit.db`
medido imediatamente antes, ou quando o tamanho físico mudou após a
leitura. Duas leituras que obtenham o **mesmo hash parcial** não atestam a
população física completa da AUD. O consumidor retorna
`SOURCE_SCHEMA_OR_READ_FAILURE`, sem métricas de consulta, scores,
requisições ou escrita. Testes offline com stream truncado e crescimento
simulado demonstram o fail-closed, com bytes do SQLite original intactos.
Este controle não prova autenticidade de provedores nem modifica os
coletores, o ledger persistido, o GEO v8 ou sua normalização.


## Abstenção em falha de integridade tardia (12/10/2026)

Uma falha no segundo SHA-256 ou na leitura SQLite pode ocorrer
**depois** de o comparador calcular taxas por consulta, mas **antes** de
comprovar que a origem física permaneceu íntegra. O tratamento de erros
agora aplica uma abstenção integral: `status=NOT_COMPARABLE`,
`queries=[]`, atribuição `NOT_VERIFIED`, identidade do alvo `N/D`
e fingerprint físico `UNVERIFIED`. Nenhuma taxa, presença de URL
auditada ou percentual previamente projetado é mantido em um caminho
de exceção.

Três regressões SQLite offline forçam falhas tardias de leitura/validação
(`ValueError`, `OSError` e `sqlite3.OperationalError`), conservam o
banco AUD byte a byte e demonstram ausência de publicação de métricas.
O controle não altera a evidência persistida, os produtores SERP/Perplexity,
o relatório GEO canônico ou pontuações.


## Consistencia da proveniencia apos falhas fisicas explicitas (12/10/2026)

A verificacao final SERP × Search API podia detectar um SQLite WAL/SHM/journal
novo ou SHA-256 diferente e descartar as taxas, mantendo entretanto a
afirmacao de atribuicao `PHYSICALLY_ATTRIBUTABLE` calculada antes da falha.
Agora ambos os caminhos aplicam a mesma abstencao integral dos erros de
leitura tardios, preservando apenas o motivo especifico da falha.
O resultado e `NOT_COMPARABLE`, `queries=[]`, atribuicao `NOT_VERIFIED`,
identidade do alvo N/D e fingerprint `UNVERIFIED`. Duas regressoes
offline exercitam source drift e sidecar surgido no intervalo, sem alterar
motores, custos ou fatos persistidos.

## Proteção adicional de provenance SERP (#304, 13/10/2026)

Se duas amostras SERP observadas da mesma query aparecem na janela de 24h,
mas uma delas não fornece o escopo completo de engine, país, região, idioma
ou dispositivo, o comparativo daquela query retorna
`SERP_SCOPE_INCOMPLETE_ALONGSIDE_VERIFIED_SAMPLE` e nenhum valor numérico.
A amostra íntegra mais próxima não pode ocultar a existência de outra amostra
real incompleta e mudar silenciosamente a população analisada.

Essa contenção não contamina consultas independentes e não considera amostras
fora da janela temporal. Os testes físicos usam SQLite somente leitura,
conferem os bytes do `audit.db` e não invocam SERP/Perplexity nem GEO live.
Ela não prova equivalência de mercado, idioma, device ou intenção dos resultados
externos Perplexity: os critérios metodológicos remanescentes da issue ficam abertos.

## Relógio SERP com proveniência incompleta (#304, 13/10/2026)

Um comparativo por consulta não pode selecionar apenas observações SERP
com timestamp verificável e ocultar uma observação física da **mesma
query** cujo `collected_at` seja nulo, inválido ou sem offset UTC.
Sem esse relógio, não se pode comprovar se o registro estava fora da
janela de 24 horas. O contrato read-only devolve
`SERP_CHRONOLOGY_UNVERIFIABLE_FOR_QUERY` sem calcular interseções ou
denominadores para a consulta atingida. Outras queries com clocks íntegros
continuam descritivas; observações com relógios válidos e fora da janela
não afetam a seleção.

A contenção é restrita ao leitor GEO observacional, com fixtures
SQLite imutáveis, nenhum novo request e nenhuma alteração de score,
coleta, SERP ou Search API. Não comprova equivalência de mercado/idioma
do provedor externo e não conclui a issue #304.

## JSON físico estrito nos metadados por fonte (#304)

Para uma execução Search API com múltiplas consultas, o vínculo de
cada fonte com sua consulta depende de um campo explícito `query`
persistido em `source_metadata_json` (ou da coluna física própria).
O leitor recusa **qualquer chave JSON duplicada** na estrutura,
inclusive aninhada, e as extensões numéricas inválidas `NaN`,
`Infinity`, `-Infinity` aceitas por alguns decoders permissivos.
Não se escolhe arbitrariamente a última das chaves duplicadas nem
se utiliza um objeto fora da especificação JSON para afirmar a origem
de um resultado.

Se houver metadado inválido em uma fonte do run multiquery, o status
de atribuição permanece `MULTI_QUERY_SOURCE_MAPPING_MISSING` e
as métricas de sobreposição ficam N/D. O arquivo `audit.db` original
é examinado em modo read-only com dupla verificação SHA-256 e
nenhuma chamada adicional aos provedores. Testes físicos reproduzem
as três constantes não JSON e duplicações tanto na raiz quanto
em objetos aninhados. O guard **não** comprova mercado, dispositivo,
idioma, intenção nem ranking da fonte externa.


## Contrato v6 - interseção de hostnames observados, por consulta (13/10/2026)

O contrato consultivo `RASAI-GEO-PER-QUERY-304-ADVISORY-006` acrescenta
`host_overlap` a cada linha `DESCRIPTIVE_ONLY`, **somente após**
vínculo físico por query, validação de todas as URLs HTTP(S) das duas
fontes, escopo SERP elegível na janela e selo local do SQLite em duas
leituras. O objeto contém `serp_distinct_hosts`,
`external_distinct_hosts`, `common_hosts`, `serp_only_hosts`,
`external_only_hosts`, taxas relativas de interseção de hosts por
fonte e Jaccard de hosts distintos. O HTML apresenta o resultado como
**interseção de hostnames exatos**, separado da interseção de URLs.

A normalização de identidade de URLs permanece v8 e **não mudou**.
Hostnames são derivados somente das URLs já verificadas: `www.example.org`
e `example.org` são hosts diferentes; portas e esquemas diferentes
podem pertencer ao mesmo hostname. Não há normalização eTLD+1,
agrupamento corporativo de concorrentes nem inferência de citação,
posição, menção, intenção, demanda, representatividade de amostra,
idioma, localização ou dispositivo externos. URL repetida no mesmo
host não cria host adicional.

Se a fonte por query não for atribuível, a URL de qualquer amostra
pertinente for inválida, o escopo SERP não for comprovável ou a
integridade física falhar, `host_overlap=null` (N/D). A tabela HTML
exige o mesmo gate global de fonte e linha usado pelas taxas por URL;
não apresenta números remanescentes após falha de selo. A visualização
mantém suporte a objetos v5 anteriores, sem inventar esse campo
retroativamente.

Testes SQLite físicos incluem multiquery, hosts exatos versus www,
portas distintas, rejeição de URL inválida, ausência de mapeamento e
abstenção após falha de proveniência. Sem novas chamadas externas,
captura de concorrente, escrita em AUD, alteração do produtor GEO,
SARI/SCORE-GEO, CONS, relatório canônico ou motores homologados.


## Gate fisico do descriptor no ledger SERP x Perplexity (#304)

O ledger offline dependia de dois hashes SHA-256 de
`audit.db`, com verificacao de comprimento. O tamanho,
porem, nao detecta uma substituicao atomica do caminho
entre `stat` e `open` quando ambos os arquivos
possuem o mesmo comprimento; dois arquivos diferentes
tambem podem ter exatamente os mesmos bytes, sem que
isso garanta continuidade de identidade fisica.

Cada leitura do selo agora confere `st_dev`, `st_ino`,
`st_size` e `st_mtime_ns` para: o caminho **antes**
de abrir, o descritor fisicamente aberto (via
`os.fstat`) e o caminho **apos** terminar a leitura.
Em POSIX, `st_ctime_ns` adiciona uma verificacao de
mudanca de metadados durante a leitura; em Windows,
o campo corresponde a creation time e nao e comparado
entre as duas APIs para evitar falso positivo
conhecido. Symlink, leitura parcial e crescimento acima
de 256 MiB continuam rejeitados.

As falhas continuam usando a politica fail-closed do
ledger: nenhuma taxa ou host-overlap pode ser emitida
se o selo fisico nao for integro. As fixtures POSIX trocam
um banco SQLite sintetico por arquivo de mesmo tamanho
antes da abertura; em Windows a substituicao fisica
de um SQLite pode ser negada pelo bloqueio de handles,
portanto uma fixture deterministica em ambas as plataformas
simula uma mudanca de inode entre descritor e stat final.
Outra fixture altera somente o mtime durante o hash.
Cada divergencia invalida o selo, mesmo que as strings
persistidas tenham permanecido identicas.

Nao modifica schema nem produtores de resultados,
SERP/Perplexity, motores homologados, report canonico,
SARI/SCORE-GEO ou auditorias existentes. Como antes,
o hash local verifica reproducibilidade de bytes, nao
autenticidade de provedor, consentimento ou
mesmo universo de observacao temporal.


## Escopo consultivo 007 - recorrência entre consultas da mesma execução

A projeção 007 acrescenta métricas de recorrência determinísticas **apenas
entre duas ou mais consultas pertencentes ao mesmo run Search API**.
Cada consulta precisa ter mapeamento físico inequívoco por fonte, denominadores
SERP e Search API completos, URL HTTP(S) canônica, relógio verificável e
escopo SERP idêntico (engine/country/region/language/device). Se qualquer
consulta do conjunto faltar, a recorrência inteira é **N/D**; o overlap
pontual de outra query íntegra continua disponível sem ser extrapolado.

São contabilizadas URLs exatas e hostnames exatos presentes em pelo menos
duas queries distintas por fonte; interseções recorrentes exigem a mesma
identidade nos dois conjuntos. Hostname www e apex permanecem distintos.
Sem uma URL-alvo única da AUD, a quantidade de hostnames recorrentes
externos ao alvo é **N/D**, nunca concorrentes supostos. Uma query única
produz **NOT_APPLICABLE_SINGLE_QUERY**, não 0%.

O resultado é estritamente descritivo, limitado a um run e a um escopo SERP
uniforme; a equivalência de mercado, idioma, dispositivo e intenção
externos permanece não comprovada. Não representa tendência histórica,
frequência de inclusão em respostas generativas, ranking, share de mercado
ou causalidade. O novo painel HTML recusa métricas numéricas se o selo
físico SQLite ou as consultas não forem integralmente admissíveis.
A versão 006 permanece somente para leitura compatível de projeções
previamente materializadas; o produtor publica 007.


## Contrato consultivo 008  -  coerência temporal e classes explícitas (19/10/2026)

O contrato `RASAI-GEO-PER-QUERY-304-ADVISORY-008` preserva a comparação
individual e as versões anteriores do renderer 005/006/007. Há um defeito de comparabilidade
em recorrência multiquery: duas observações SERP podem estar ambas até 24h
da mesma execução Search API e, ainda assim, quase 48h separadas entre si.
Agora a recorrência exige, além dos denominadores e cinco campos de escopo
já verificados, **relógio de cada SERP** e amplitude máxima de **24 horas**
entre todas as observações selecionadas. Sem relógio comprovado,
`SERP_INTER_QUERY_CLOCK_UNVERIFIABLE`; acima de 24h,
`SERP_INTER_QUERY_SPAN_EXCEEDS_24H`. Ambas são `NOT_COMPARABLE` e têm
contagens nulas (N/D). Os resultados de cada consulta íntegra continuam
descritivos e independentes. Uma coorte válida expõe
`serp_inter_query_span_seconds`, além de `serp_collected_at` e
`external_run_started_at` por linha.

A opção `--declared-nonbranded-query "seguro de vida"` permite
classificação editorial `NONBRANDED_DECLARED`, mas não trata ausência de
marca `BRANDED_DECLARED` como prova de non-branded. A mesma query
não pode receber ambas as classes; consultas não persistidas, duplicatas,
espaços periféricos e controles são recusados. O campo
`query_class_source=EXPLICIT_OPERATOR_DECLARATION` atesta somente
origem editorial, **não intenção/mercado equivalentes entre provedores**.

Tudo permanece offline e read-only; nenhuma fonte comercial foi chamada,
nenhuma AUD ou score foi alterado e não há hipótese de participação de
mercado ou citação gerativa. Novos testes sintéticos exigem execução
direcionada no HEAD final; teste adicionado não constitui teste aprovado.

## Distribuição dos grupos de URLs por fonte (#304, observacional)

O ledger atual acrescenta `serp_target_url_distribution` e
`external_target_url_distribution` exclusivamente quando já existem
**dois conjuntos de URLs fisicamente atribuídos à mesma consulta** e
**uma única URL-alvo física e canônica da AUD**. Dentro de cada fonte,
o denominador é o conjunto de **URLs distintas retornadas**, nunca
número de posições solicitadas, impressões ou volume de buscas.

A partição disjunta informa: (1) presença da URL exata da AUD (0 ou 1),
(2) outras URLs do hostname exato, (3) URLs de outros hostnames.
Há contagens e proporções de cada grupo, arredondadas a quatro casas.
A soma das contagens precisa coincidir com o denominador. `www` e
domínio raiz não são equivalentes; sem fonte, alvo ou selo físico o
relatório publica **N/D**, não percentuais falsos.

Os percentuais são uma **distribuição descritiva dos resultados recebidos**.
Não são ranking, probabilidade de citação generativa, participação de
mercado, tráfego, indexação ou equivalência de país/idioma/device/intent
entre SERP e Perplexity. O contrato de coleta e o score não mudam;
o acréscimo é compatível com o formato consultivo 008 existente.


## Integração canônica de relatório - #304 / GEO por consulta

O consumidor `src/rasai/geo_query_ledger_report.py` expõe em `geo.html`,
na mesma seção de interpretação GEO da AUD, uma matriz limitada a 10 consultas
com SERP escopo/horário, denominadores físicos SERP e Search API, URLs em comum,
taxas descritivas e presença exata da URL auditada. A projeção chama o
`inspect_geo_per_query` existente **somente sobre a AUD local correspondente**
(`AUD-ID/audit.db`), preservando selo duplo SHA256 e regras de abstenção.
Há também rótulos declarativos branded/non-branded, quando efetivamente
presentes no contrato do ledger. O HTML escapa dados não confiáveis.

Não altera a comparação histórica já apresentada em `geo.html`: a tabela
adicional mostra uma população **observacional por consulta**, não prova
equivalência de mercado/região/idioma/dispositivo/intenção entre provedores,
citação generativa, frequência de consultas, score ou rank. Se o SQLite,
identidade da AUD, per-result query ou amostra não estiver verificável,
apresenta N/D explícito, sem zeros fabricados. A integração não cria
atividade de rede, não persistente novos resultados, não muda schema nem
reprocessa histórico. Em AUD física grande, o selo atual faz duas leituras
locais completas do SQLite, exigência que deliberadamente prioriza
integridade à inferência baseada em snapshot mutável.

Regressões direcionadas: `tests/test_geo_query_ledger_report.py` cobrem
renderização efetiva por `geo_body`, escape, denominadores, multi-query
sem atribuição, AUD divergente e supressão de taxas com selo inválido.
**Testes novos não executados neste ciclo pelo agente**; validar somente
se o gate de conclusão deste lote exigir.


## Hostnames das fontes físicas por consulta (#304)

A projeção passou a expor quais **hostnames exatos** são efetivamente
observados nos resultados SERP e Search API de cada consulta, não somente
as contagens agregadas de hostnames. O inventário opcional
host_source_inventory identifica hostname, URLs distintas por fonte e URLs
exatamente comuns, preservando www distinto de apex, sem associação
semântica a competidores de mercado. O algoritmo usa os conjuntos de URLs
já canonizados e atribuídos fisicamente por query, relógio e scope SERP.

Apenas 12 hostnames são exibidos por consulta, em ordem determinística
de contagem agregada decrescente e hostname; o denominador e o total de
hostnames continuam completos. O inventário é exibido como detalhe
expansível tanto no relatório GEO canônico quanto no HTML consultivo.
Amostras não atribuídas, sem selo SHA duplo ou de origem ambígua dão N/D
sem promover resultados. Hostnames externos não comprovam concorrência
comercial, ranking, share de mercado ou presença em respostas generativas.
Sem nova coleta, alteração de SQLite/AUD, API, SARI/SCORE ou workflows.
