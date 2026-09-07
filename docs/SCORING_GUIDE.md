# SCORING_GUIDE.md

Guia operacional do **Search & AI Readiness Index `SARI-001`**.

## Método vigente

Novas auditorias usam por padrão:

```text
scoring_version = SCORE-GEO-004
```

O `SCORE-GEO-004` mantém as dimensões determinísticas e usa um Overall determinístico, transparente e reproduzível por auditoria. Ele não depende de um model artifact de calibração e não representa probabilidade de citação.

Consulte [`SCORE_GEO_004.md`](SCORE_GEO_004.md) para o contrato completo.

## Histórico de versões

```text
SCORE-GEO-002  baseline determinística histórica
SCORE-GEO-003  Overall calibrado empiricamente; exige model artifact VALIDATED
SCORE-GEO-004  padrão vigente; Overall determinístico e calibração empírica opcional
```

Auditorias históricas não são recalculadas silenciosamente entre versões.

## Dimensões

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

Desktop e Mobile permanecem separados. Apenas dispositivos realmente auditados devem ser apresentados como resultado válido.

## RuleResult

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

Somente `PASS`, `WARNING` e `FAIL` entram no denominador do score da dimensão.

`UNKNOWN` e `ERROR` reduzem Coverage/capacidade de conclusão; não são `FAIL`.

`NOT_APPLICABLE` sai do universo aplicável quando legítimo.

## Fórmula das dimensões

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00

Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

A semântica de grupos correlacionados (`MAX_IMPACT`), pré-requisitos, evidência e aplicabilidade permanece compatível com as versões anteriores.

## Coverage

```text
evaluated applicable weight / total applicable weight
```

Coverage mede completude da análise, não qualidade do site.

## Confidence da dimensão

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

Esses thresholds são governança interna versionada do RASAi.

## Consolidation da dimensão

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          demais estados avaliáveis com Coverage >= 50%
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Pré-requisito bloqueado não pode ser promovido a `NOT_APPLICABLE` benigno.

## Overall no SCORE-GEO-004

Contrato:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Com as dimensões aplicáveis materializadas:

```text
Overall = soma dos Dimension Scores aplicáveis / quantidade de dimensões aplicáveis
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero.

Uma dimensão aplicável sem valor ou em `NOT_CONSOLIDATED` bloqueia o Overall consolidado.

### Coverage do Overall

```text
média da Coverage das dimensões aplicáveis
```

### Confidence do Overall

```text
menor Confidence das dimensões aplicáveis
```

### Gate de consolidação do Overall

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Coverage média >= 80%
Confidence mínima = HIGH ou MEDIUM
```

Quando existe valor calculável, mas a força da medição fica abaixo desse gate, o Overall pode ser `PARTIAL`. Estados insuficientes nunca viram zero.

## Structured Data / NOT_APPLICABLE

JSON-LD não é requisito universal para cálculo.

Quando `STRUCTURED_DATA` é legitimamente `NOT_APPLICABLE`, a dimensão não recebe zero e sai do denominador do Overall.

## Sem IA

IA continua opcional para a auditoria base. Ausência de IA pode reduzir Coverage/Confidence das dimensões que dependem de análise semântica, sem transformar automaticamente ausência de análise em `FAIL`.

O `SCORE-GEO-004` não exige IA para a fórmula do Overall.

## Métricas externas fora do score

Não entram no SARI/SCORE-GEO:

- Lighthouse Performance;
- Core Web Vitals;
- Lighthouse Accessibility;
- Synthetic Navigation Apdex;
- métricas de tráfego/conversão;
- Observed Generative Visibility.

Indisponibilidade de PageSpeed/Lighthouse, por exemplo, não reduz o Overall RASAi.

## Calibração empírica

O pipeline `SCORE-GEO-003` é preservado como ferramenta histórica de calibração/validação empírica.

Comandos existentes:

```powershell
rasai scoring calibrate --dataset-version GEO-CAL-001
rasai scoring inspect
```

Artifact do `003`:

```text
.rasai/scoring/score-geo-003-model.json
```

Override:

```text
RASAI_SCORE_GEO_003_MODEL
```

Esse artifact **não é requisito nem input do SCORE-GEO-004**. Pode ser usado para pesquisa, benchmarking e avaliação de associação entre readiness e outcomes observados.

## Parametrização

Configuração de coleta é permitida. A matemática oficial do `004` não é variável por auditoria.

Configurável:

- URLs/domínios auditados;
- dispositivos;
- IA e contexto editorial;
- Web Performance e Synthetic Apdex, que continuam independentes do score;
- limites de coleta e execução.

Fixo/versionado no `004`:

- dimensões;
- pesos/regras já versionados pelo catálogo;
- fatores PASS/WARNING/FAIL;
- Overall de igual peso entre dimensões aplicáveis;
- thresholds de Coverage/Confidence/Consolidation.

## Reprodutibilidade

`BR-GEO-054` permite reconstrução a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- `SCORE-GEO-004`;
- evidências persistidas.

Nenhuma reexecução de website, IA ou calibração deve ser necessária.

## Relatórios e histórico

`readiness.html` é a página canônica do SARI.

`score-geo-004.html` expõe o contrato vigente, fórmula e gates de consolidação.

`SCORE_GEO_003.md` continua documentando a versão calibrada histórica.

Relatórios históricos/consolidados preservam `scoring_version` e não misturam versões em uma mesma série comparável sem indicação explícita.

## Limite de validade

O `004` é uma métrica proprietária, transparente e reproduzível. Não é certificação oficial de Google, OpenAI, Microsoft, Anthropic ou outro mantenedor.

O resultado mede readiness segundo o contrato RASAi; não prova causalidade nem garante ranking, tráfego, conversão ou citação futura.
