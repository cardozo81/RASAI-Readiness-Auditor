# Métricas derivadas de Structured Data

## Objetivo

Este documento define as consolidações advisory de dados estruturados materializadas pelo RASAi a partir de evidências e `RuleExecutions` já persistidos.

Elas não criam requests adicionais, não chamam IA para inferir propriedades ausentes e não alteram automaticamente `SARI-001` ou `SCORE-GEO-004`.

## Structured Data Coverage

Mede a proporção de `DEVICE_SNAPSHOT` que possui Structured Data materializado.

```text
snapshots com structured_data_ref
---------------------------------- x 100
snapshots observados
```

A presença de Structured Data não implica validade, completude ou elegibilidade para rich result.

## Structured Data Validity Rate

Fonte determinística: `BR-GEO-034`.

```text
BR-GEO-034 = PASS
----------------------------- x 100
execuções determináveis aplicáveis
```

Mede interpretabilidade sintática quando Structured Data está presente.

## Structured Data Type/Property Identifiability Rate

Fonte determinística: `BR-GEO-035`.

Relação com RASAi: **5/5**.

```text
BR-GEO-035 = PASS
----------------------------- x 100
execuções determináveis aplicáveis
```

A métrica responde à pergunta: **os tipos e propriedades relevantes declarados são identificáveis na evidência observada?**

Estados `NOT_APPLICABLE` ou sem determinação suficiente ficam fora do denominador. `WARNING` não é convertido em `PASS`.

### Fronteira metodológica

Este indicador **não** deve ser chamado de `Schema.org Completeness`, `Required Property Completeness` ou `Recommended Property Completeness`.

`BR-GEO-035` não prova que todos os campos obrigatórios ou recomendados por cada tipo/schema/rich-result estejam presentes. Publicar essa conclusão exigiria um contrato adicional, versionado por vocabulário/tipo e por conjunto de requisitos aplicável.

Portanto o nome canônico é:

```text
Structured Data Type/Property Identifiability Rate
```

Metric id:

```text
structured_data_type_property_identifiability_rate
```

Escopo:

```text
DEVICE_SNAPSHOT
```

## Structured Data to Visible Content Consistency

Fonte determinística: `BR-GEO-036`.

Mede a proporção de execuções determináveis em que o Structured Data permanece coerente com o conteúdo visível observado.

## Structured Entity Consistency

Fonte determinística: `BR-GEO-037`.

Mede a proporção de execuções determináveis em que a representação de entidades estruturadas permanece coerente segundo o contrato da regra.

## Interpretação conjunta

Os indicadores devem permanecer separados porque respondem a perguntas distintas:

| Indicador | Pergunta |
|---|---|
| Coverage | existe Structured Data materializado? |
| Validity | a estrutura é sintaticamente interpretável? |
| Type/Property Identifiability | tipos e propriedades relevantes são identificáveis? |
| Visible Content Consistency | o markup é coerente com o conteúdo visível? |
| Entity Consistency | as entidades estruturadas permanecem coerentes? |

Nenhum deles, isoladamente, equivale a aprovação em Google Rich Results, Schema.org completeness ou elegibilidade universal de search feature.

## Custo e aquisição

Provider fee: **zero**.

Requests adicionais ao target: **zero**.

A consolidação reutiliza somente evidência já persistida no audit.
