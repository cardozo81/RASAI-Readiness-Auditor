# SCORE-GEO-004

`SCORE-GEO-004` é o método de scoring vigente do RASAi.

O índice público é `SARI-001 - Search & AI Readiness Index`.

## Objetivo

O método fornece um índice operacional que pode ser calculado, auditado e reproduzido em uma auditoria individual sem depender de corpus externo, modelo estatístico ou artifact de calibração.

O contrato separa claramente:

- scoring de readiness do website;
- qualidade e completude da medição;
- métricas externas independentes;
- outcomes observados de Search e AI Search.

O Overall não representa probabilidade de ranking, resposta ou citação.

## Dimensões

O método possui dez dimensões:

1. `TECHNICAL_ACCESSIBILITY`
2. `INDEXABILITY`
3. `CONTENT_EXTRACTABILITY`
4. `SEMANTIC_STRUCTURE`
5. `ENTITY_CLARITY`
6. `STRUCTURED_DATA`
7. `ANSWERABILITY`
8. `CITATION_READINESS`
9. `EVIDENCE_TRUST`
10. `INTENT_COVERAGE`

Cada dimensão é calculada a partir de `RuleExecution` e evidências persistidas.

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00

Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos silenciosamente em `FAIL`.

## Overall

O contrato de agregação é:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Fórmula:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Regras:

- cada dimensão aplicável possui o mesmo peso no Overall;
- dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero;
- dimensão aplicável sem valor ou em `NOT_CONSOLIDATED` bloqueia a publicação de Overall consolidado;
- nenhuma métrica externa é usada como contribuição implícita;
- nenhuma calibração externa é requisito ou input do score.

## Coverage

Coverage mede completude da análise, não qualidade do site.

Na dimensão:

```text
Coverage = evaluated applicable weight / total applicable weight
```

No Overall:

```text
Overall Coverage = média da Coverage das dimensões aplicáveis
```

## Confidence

A Confidence de cada dimensão depende de Coverage, presença de evidência e erros de execução.

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas os critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

A Confidence do Overall é a menor Confidence entre as dimensões aplicáveis.

## Consolidation

Dimensão:

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          estado avaliável com Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Overall `CONSOLIDATED` exige simultaneamente:

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Overall Coverage >= 80%
Overall Confidence = HIGH ou MEDIUM
```

Se existe valor calculável, mas a medição não alcança o gate completo, o Overall pode ser `PARTIAL` quando a Coverage é de pelo menos 50% e a Confidence está disponível.

Estado insuficiente nunca é transformado em zero.

## Structured Data e aplicabilidade

Structured Data não é requisito universal.

Se `STRUCTURED_DATA` for legitimamente `NOT_APPLICABLE`, a dimensão sai do denominador do Overall e não recebe nota zero nem nota máxima.

Se a aplicabilidade estiver indefinida por pré-requisito bloqueado, o estado não pode ser promovido a `NOT_APPLICABLE` benigno.

## IA

IA é opcional para o pipeline base, mas determinadas regras semânticas podem precisar de análise suficiente para produzir resultado em vez de `UNKNOWN`.

Quando regras aplicáveis permanecem sem avaliação, Coverage e Confidence podem cair e impedir `CONSOLIDATED`.

A fórmula do Overall não chama IA e não depende de provider específico.

## Métricas externas independentes

Não entram no SARI-001/SCORE-GEO-004:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- tráfego, conversão e métricas de negócio;
- outcomes observados de AI visibility.

Essas medições possuem metodologias e páginas próprias. Indisponibilidade de PageSpeed/Lighthouse, por exemplo, não reduz o Overall do SARI-001.

## Reprodutibilidade

`BR-GEO-054` verifica que o scoring pode ser reconstruído a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- evidências persistidas;
- fórmula e thresholds versionados do `SCORE-GEO-004`.

Não é necessário reexecutar website, IA ou APIs externas para reproduzir o cálculo persistido.

## Relatório

Cada auditoria materializa, quando aplicável:

```text
report/readiness.html
report/score-geo-004.html
```

`readiness.html` é a página canônica do SARI-001.

`score-geo-004.html` expõe fórmula, Coverage, Confidence, Consolidation, rastreabilidade do Overall e critérios para interpretação.

## Limite de validade

`SCORE-GEO-004` é uma metodologia proprietária, transparente, versionada e reproduzível do RASAi.

Não é um standard oficial de Google, Microsoft, OpenAI, Anthropic ou outro mantenedor e não garante ranking, tráfego, conversão, resposta ou citação futura.
