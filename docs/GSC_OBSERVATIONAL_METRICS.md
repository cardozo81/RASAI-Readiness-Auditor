# Métricas observacionais do Google Search Console

## Objetivo

Esta camada transforma somente dados do Google Search Console já persistidos em `observability.db` em métricas advisory do RASAi.

Ela não cria chamadas adicionais ao Google, não grava credenciais e não altera `SARI-001` ou `SCORE-GEO-004`.

Relação com RASAi: **5/5**, porque os dados descrevem diretamente o estado conhecido pelo Google para URLs inspecionadas, Sitemaps da property autenticada e performance observada na busca.

## Fonte e seleção de dataset

Para cada família, o RASAi usa exclusivamente o dataset mais recente persistido:

```text
GOOGLE_SEARCH_CONSOLE_URL_INSPECTION
GOOGLE_SEARCH_CONSOLE_SITEMAPS
GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS
```

Datasets históricos anteriores não são somados ao snapshot atual.

## URL Inspection

### GSC URL Inspection Response Coverage

```text
URLs auditadas com resposta de inspeção não-erro
----------------------------------------------- x 100
URLs do conjunto auditado
```

A métrica mede quanto do conjunto auditado possui uma resposta de URL Inspection utilizável no dataset mais recente. Uma cobertura inferior a 100% pode ser intencional quando `RASAI_STANDARDS_MAX_URLS` limita a coleta. Linhas `ERROR` são excluídas do numerador porque representam tentativa sem resposta de inspeção utilizável.

Ela não mede cobertura do índice inteiro do Google nem cobertura de todas as URLs existentes no domínio.

### GSC URL Inspection Verdict PASS Rate

```text
URLs com verdict = PASS
------------------------------- x 100
URLs inspecionadas com verdict determinável e sem erro de coleta
```

A métrica preserva a semântica do `verdict` retornado pela URL Inspection API. Ela não substitui os checks determinísticos locais de crawlability/indexability.

### GSC Indexing Allowed Rate

```text
URLs com indexingState = INDEXING_ALLOWED
------------------------------------------ x 100
URLs inspecionadas com indexingState determinável
```

### GSC Robots Allowed Rate

```text
URLs com robotsTxtState = ALLOWED
--------------------------------- x 100
URLs inspecionadas com robotsTxtState determinável
```

### GSC Page Fetch Successful Rate

```text
URLs com pageFetchState = SUCCESSFUL
------------------------------------- x 100
URLs inspecionadas com pageFetchState determinável
```

### GSC Exact User/Google Canonical Agreement Rate

```text
URLs onde userCanonical == googleCanonical
------------------------------------------- x 100
URLs inspecionadas que expõem os dois canonicals
```

A comparação é exata após remoção de espaços nas extremidades. Ausência de um dos valores fica fora do denominador.

Isso não declara que divergência de canonical é sempre erro. O Google pode selecionar outro canonical por sinais próprios; a métrica torna essa divergência observável.

### GSC Sitemap Association Rate

```text
URLs inspecionadas associadas a pelo menos um sitemap
----------------------------------------------------- x 100
URLs inspecionadas com verdict determinável
```

Associação observada não prova completude nem correção do sitemap.

## Sitemaps

A coleta usa o endpoint oficial de listagem de Sitemaps da property e persiste um resumo bounded em `observability.db`.

### GSC Sitemap Count

Quantidade de entradas de sitemap presentes no dataset mais recente retornado pelo Search Console.

Dataset válido com lista vazia produz `0`; ausência de dataset não é convertida em zero.

### GSC Sitemap Error-free Rate

```text
Sitemaps com errors = 0
----------------------------- x 100
Sitemaps com errors determinável
```

O campo `errors` vem diretamente do recurso Sitemap do Search Console.

### GSC Sitemap Warning-free Rate

```text
Sitemaps com warnings = 0
------------------------------- x 100
Sitemaps com warnings determinável
```

Warnings são problemas reportados pela fonte Google e podem ser não críticos; o RASAi não os promove automaticamente a falha de readiness.

### GSC Sitemap Pending Rate

```text
Sitemaps com isPending = true
----------------------------- x 100
Sitemaps com isPending determinável
```

É uma métrica em que **menor é melhor**. Estado pendente pode ser transitório e não é tratado como falha permanente do website.

### GSC Sitemap Reported Submitted URLs

Soma de `contents[].submitted` reportada pelo Search Console para os tipos de conteúdo existentes nas entradas do dataset mais recente.

O RASAi **não usa** `contents[].indexed`, pois a própria documentação atual do Search Console marca esse campo como descontinuado. Portanto este indicador não é chamado de taxa de indexação e não estima URLs indexadas.

## Search Analytics

A Search Analytics API pode retornar apenas as linhas superiores conforme dimensões, período e limites da consulta. Portanto o RASAi **não** chama estes agregados de totais da property.

Os nomes usam deliberadamente `Returned-row`.

### GSC Returned Search Analytics Rows

Quantidade de linhas normalizadas persistidas no dataset mais recente.

Se o dataset foi coletado com sucesso e contém zero linhas, esta métrica é `0`. Isso é diferente de não existir dataset Search Analytics para a auditoria.

### GSC Returned-row Distinct Queries

Quantidade de valores `query_text` distintos e não vazios existentes nas linhas retornadas/persistidas do dataset mais recente.

Esta contagem **não** representa o universo completo de consultas da property. Ela descreve somente as queries visíveis no dataset bounded retornado pelo Search Analytics.

### GSC Returned-row Distinct URLs

Quantidade de URLs distintas e não vazias representadas nas linhas retornadas/persistidas.

Ela não deve ser interpretada como cobertura orgânica total das URLs auditadas ou da property, porque URLs ausentes podem apenas não ter aparecido entre as linhas retornadas.

### GSC Returned-row Distinct Query-URL Pairs

Quantidade de pares distintos `query_text + URL` existentes nas linhas retornadas/persistidas.

O indicador descreve diversidade observada de associação entre consulta e página dentro do dataset retornado. Não é Recall, nDCG, Share of Voice ou cobertura completa de busca.

### GSC Returned-row Clicks

Soma de `clicks` das linhas efetivamente retornadas/persistidas. Em um dataset válido com zero linhas, o valor é `0`.

### GSC Returned-row Impressions

Soma de `impressions` das linhas efetivamente retornadas/persistidas. Em um dataset válido com zero linhas, o valor é `0`.

### GSC Returned-row CTR

```text
soma(clicks)
----------------- x 100
soma(impressions)
```

Calculado somente sobre as linhas retornadas. Quando não há impressões, o estado permanece `NO_DATA`; zero impressões não é transformado em CTR 0%.

### GSC Returned-row Impression-weighted Position

```text
soma(position × impressions)
----------------------------
soma(impressions)
```

Também limitado às linhas retornadas/persistidas. Sem impressões elegíveis, permanece `NO_DATA`.

## Escopos

As métricas de URL Inspection usam:

```text
URL_SET
```

Os agregados de Sitemaps e as métricas/contagens do dataset Search Analytics usam:

```text
ORIGIN
```

O campo `details_json` preserva o `dataset_id` usado e a fronteira de interpretação.

## Persistência

Fonte bruta/normalizada:

```text
observability.db
```

Projeção advisory:

```text
audit.db -> standards_metric_observations
```

O `audit.db` não recebe token OAuth nem resposta bruta do Google nessa projeção.

## Relatórios

As métricas aparecem em:

- `standards.html`, com fonte, escopo e metodologia;
- `observability.html`, como resumo observacional do Search Console.

## Referências oficiais

- Search Console API Reference: https://developers.google.com/webmaster-tools/v1/api_reference_index
- URL Inspection `index.inspect`: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect
- Sitemaps `list`: https://developers.google.com/webmaster-tools/v1/sitemaps/list
- Sitemaps Resource: https://developers.google.com/webmaster-tools/v1/sitemaps
- Search Analytics `query`: https://developers.google.com/webmaster-tools/v1/searchanalytics/query

A documentação do recurso Sitemap informa que `contents[].indexed` está descontinuado; o RASAi respeita essa fronteira e não usa esse campo. A documentação de Search Analytics informa que a API não garante todas as linhas, justificando a nomenclatura `Returned-row`.

## Fronteiras metodológicas

- URL Inspection descreve o estado conhecido pelo índice do Google; não é live test universal;
- Search Analytics pode omitir linhas e não representa necessariamente o universo completo da property;
- contagens de queries, URLs e pares query-URL são somente do dataset retornado/persistido;
- Sitemaps `errors`, `warnings`, `isPending` e `submitted` são preservados como observações da fonte Google;
- `contents[].indexed` de Sitemaps não é usado por estar descontinuado;
- dataset inexistente não é convertido em zero;
- dataset Search Analytics válido com zero linhas materializa contagens/clicks/impressions como zero, enquanto CTR e posição permanecem `NO_DATA`;
- erro de coleta não vira falha do website;
- métricas GSC não duplicam peso no SARI;
- dados locais determinísticos e dados observacionais Google permanecem separados.
