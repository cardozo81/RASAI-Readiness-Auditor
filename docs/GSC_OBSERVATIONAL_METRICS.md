# Métricas observacionais do Google Search Console

## Objetivo

Esta camada transforma somente dados do Google Search Console já persistidos em `observability.db` em métricas advisory do RASAi.

Ela não cria chamadas adicionais ao Google, não grava credenciais e não altera `SARI-001` ou `SCORE-GEO-004`.

Relação com RASAi: **5/5**, porque os dados descrevem diretamente o estado conhecido pelo Google para URLs inspecionadas e a performance observada na busca para a property autenticada.

## Fonte e seleção de dataset

Para cada família, o RASAi usa exclusivamente o dataset mais recente persistido:

```text
GOOGLE_SEARCH_CONSOLE_URL_INSPECTION
GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS
```

Datasets históricos anteriores não são somados ao snapshot atual.

## URL Inspection

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

## Search Analytics

A Search Analytics API pode retornar apenas as linhas superiores conforme dimensões, período e limites da consulta. Portanto o RASAi **não** chama estes agregados de totais da property.

Os nomes usam deliberadamente `Returned-row`.

### GSC Returned Search Analytics Rows

Quantidade de linhas normalizadas persistidas no dataset mais recente.

### GSC Returned-row Clicks

Soma de `clicks` das linhas efetivamente retornadas/persistidas.

### GSC Returned-row Impressions

Soma de `impressions` das linhas efetivamente retornadas/persistidas.

### GSC Returned-row CTR

```text
soma(clicks)
----------------- x 100
soma(impressions)
```

Calculado somente sobre as linhas retornadas.

### GSC Returned-row Impression-weighted Position

```text
soma(position × impressions)
----------------------------
soma(impressions)
```

Também limitado às linhas retornadas/persistidas.

## Escopos

As métricas de URL Inspection usam:

```text
URL_SET
```

Os agregados do dataset Search Analytics usam:

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

## Fronteiras metodológicas

- URL Inspection descreve o estado conhecido pelo índice do Google; não é live test universal;
- Search Analytics pode omitir linhas e não representa necessariamente o universo completo da property;
- ausência de dados não vira zero;
- erro de coleta não vira falha do website;
- métricas GSC não duplicam peso no SARI;
- dados locais determinísticos e dados observacionais Google permanecem separados.
