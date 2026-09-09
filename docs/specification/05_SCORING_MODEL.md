# SCORING_MODEL.md

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT
**Scoring baseline:** `SCORE-GEO-004`
**Public index:** `SARI-001`

## 0. Natureza metodológica

`SCORE-GEO-004` é o método proprietário e versionado de scoring vigente do RASAi.

`APPROVED` significa aprovado como baseline normativa interna. Não significa homologação por Google, OpenAI, Microsoft, Anthropic, NIST, W3C, schema.org ou outro mantenedor.

O método é determinístico, evidence-bound e reproduzível por auditoria. O Overall não é probabilidade de ranking, tráfego, conversão, resposta ou citação futura.

Validação empírica externa pode existir como pesquisa independente, mas não é input obrigatório do runtime e não altera silenciosamente o score.

## 1. Estrutura persistida

Todo Score possui:

- Value;
- Coverage;
- Confidence;
- Consolidation Status;
- Contributions;
- Limitations;
- Scoring Version.

`scoring_version` é parte do contrato de comparabilidade e deve permanecer persistido mesmo que a rota HTML seja version-neutral.

## 2. Dimensões

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

Desktop e Mobile permanecem separados. Um dispositivo não auditado não pode ser projetado como resultado válido.

## 3. RuleResult

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são `FAIL`.

## 4. Score da dimensão

Fatores default:

```text
PASS    = 1.00
WARNING = 0.50
FAIL    = 0.00
```

Fórmula:

```text
Σ(weight × result_factor)
------------------------- × 100
Σ(weight evaluated)
```

Somente `PASS`, `WARNING` e `FAIL` participam do denominador do score.

As regras de `scoring_group`, pré-requisitos, site-level rules e prevenção de cascading failure fazem parte do contrato determinístico das dimensões.

## 5. Coverage

```text
evaluated applicable weight / total applicable weight
```

Evaluated: `PASS`, `WARNING`, `FAIL`.

Applicable: `PASS`, `WARNING`, `FAIL`, `UNKNOWN`, `ERROR`.

`NOT_APPLICABLE` fica fora.

Coverage mede completude da análise, não qualidade do website.

## 6. Aplicabilidade

### Sem RuleExecution

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_CONSOLIDATED
limitation = NO_RULE_EXECUTIONS
```

### Todas legitimamente NOT_APPLICABLE

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_APPLICABLE
limitation = NO_APPLICABLE_RULES
```

### Pré-requisito bloqueado

Reason contendo `PREREQUISITE_BLOCKED` mantém estado não consolidado; não pode ser promovido a `NOT_APPLICABLE` benigno apenas para elevar o score.

## 7. Confidence da dimensão

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         Coverage > 0 sem atender HIGH/MEDIUM
UNAVAILABLE Coverage <= 0
```

Os thresholds são governança interna versionada.

`Confidence LOW` isoladamente não gera finding nem ordem de reescrita.

## 8. Consolidation da dimensão

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          demais estados avaliáveis com Coverage >= 50%
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   universo legitimamente não aplicável
```

## 9. Overall - SCORE-GEO-004

Existem separadamente:

- Overall Readiness - Desktop;
- Overall Readiness - Mobile.

Contrato de agregação:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Pré-condições:

1. materializar as dez dimensões;
2. permitir `NOT_APPLICABLE` legítimo;
3. exigir Value para toda dimensão aplicável;
4. bloquear consolidação se qualquer dimensão aplicável estiver `NOT_CONSOLIDATED`.

Fórmula:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Cada dimensão aplicável possui o mesmo peso no Overall.

Dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero nem imputação artificial.

## 10. Gate do Overall

```text
CONSOLIDATED
  se todas as dimensões aplicáveis possuem valor
  e nenhuma está NOT_CONSOLIDATED
  e Overall Coverage >= 80%
  e Overall Confidence = HIGH ou MEDIUM

PARTIAL
  se o Overall é calculável
  e Coverage >= 50%
  e Confidence está disponível
  mas o gate completo não foi atingido

NOT_CONSOLIDATED
  quando o contrato aplicável está incompleto ou abaixo do mínimo
```

Estado insuficiente nunca é convertido em zero.

## 11. Coverage e Confidence do Overall

```text
Overall Coverage = média da Coverage das dimensões aplicáveis
Overall Confidence = menor Confidence das dimensões aplicáveis
```

Não existe `calibration_confidence` obrigatória no runtime 004.

## 12. Parametrização

Pode variar por operação/coleta:

- URLs/domínios;
- dispositivo;
- IA/provider/modelo;
- Web Performance;
- Synthetic Apdex;
- limites de coleta e execução.

Não varia arbitrariamente por auditoria:

- conjunto de dimensões;
- pesos/fatores versionados;
- fórmula do Overall;
- gates de Coverage/Confidence/Consolidation.

Mudança incompatível exige nova `scoring_version`.

## 13. Sem IA

A auditoria base continua podendo executar sem LLM. Ausência de IA pode reduzir Coverage/Confidence de dimensões sem converter regras semânticas em `FAIL`.

O cálculo do Overall não chama IA e não depende de provider específico.

## 14. Structured Data

JSON-LD não é requisito universal.

`STRUCTURED_DATA = NOT_APPLICABLE` legítimo não recebe penalização direta. Se markup existir ou a regra se tornar aplicável, a dimensão é avaliada normalmente.

## 15. Reprodutibilidade

`BR-GEO-054` deve permitir reconstrução a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- scoring version `SCORE-GEO-004`;
- evidências persistidas;
- limitações e estados de aplicabilidade;
- contrato de agregação `EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1`.

A reprodução não pode exigir nova execução do website nem nova chamada de IA.

## 16. Histórico e comparabilidade

Nenhum AUD persistido é recalculado automaticamente por geração de relatório ou mudança de versão metodológica.

Relatórios históricos/consolidados devem segmentar pontos por `scoring_version`.

## 17. Evidência externa

O RASAi separa:

1. requisito/sinal oficial externo;
2. métrica externa definida/calibrada por terceiros;
3. regra/heurística RASAi;
4. outcomes externos observados.

Core Web Vitals, Lighthouse, WCAG, Apdex, E-E-A-T/YMYL e Observed Generative Visibility não entram automaticamente no Overall `SCORE-GEO-004`.

## 18. Relatório

`readiness.html` é a página canônica do SARI.

`scoring.html` é a página canônica estável da metodologia de scoring e expõe:

- `scoring_version` efetiva;
- fórmula da dimensão;
- contrato do Overall;
- Coverage;
- Confidence;
- Consolidation;
- limitações;
- compatibilidade entre dados de desenvolvimento.

Detalhes operacionais: `docs/SCORE_GEO_004.md` e `docs/SCORING_GUIDE.md`.
