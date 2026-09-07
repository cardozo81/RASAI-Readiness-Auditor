# SCORING_MODEL.md

**Status:** APPROVED
**Scoring baseline:** `SCORE-GEO-003`

## 0. Natureza metodológica

`SCORE-GEO-003` é o método proprietário e versionado de scoring do RASAi.

`APPROVED` significa aprovado como baseline normativa interna. Não significa homologação por Google, OpenAI, Microsoft, Anthropic, NIST, W3C, schema.org ou outro mantenedor.

O `SCORE-GEO-003` aplica calibração empírica somente no `OVERALL_READINESS`. As dimensões permanecem determinísticas, evidence-backed e reprodutíveis.

O resultado calibrado mede associação observacional no dataset utilizado. Não prova causalidade e não garante ranking, tráfego, conversão ou citação futura.

## 1. Estrutura persistida

Todo Score possui:

- Value;
- Coverage;
- Confidence;
- Consolidation Status;
- Contributions;
- Limitations;
- Scoring Version.

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

As regras de `scoring_group`, `MAX_IMPACT`, pré-requisitos, site-level rules e prevenção de cascading failure fazem parte do contrato determinístico das dimensões.

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

Reason contendo `PREREQUISITE_BLOCKED` mantém:

```text
Value = null
Consolidation = NOT_CONSOLIDATED
limitation = APPLICABILITY_UNRESOLVED:PREREQUISITE_BLOCKED
```

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

## 9. Overall — mudança do SCORE-GEO-003

Existem separadamente:

- Overall Readiness — Desktop;
- Overall Readiness — Mobile.

Pré-condições:

1. materializar as dez dimensões;
2. permitir `NOT_APPLICABLE` legítimo;
3. exigir Value para toda dimensão aplicável;
4. bloquear se qualquer dimensão aplicável estiver `NOT_CONSOLIDATED`;
5. exigir model artifact `VALIDATED`.

Com as pré-condições satisfeitas:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

Cada feature é uma dimensão normalizada em `0..1`.

Dimensão legitimamente `NOT_APPLICABLE` usa a média de imputação persistida no model artifact. Ela não recebe zero.

### Sem model artifact validado

```text
Overall.value = null
Overall.confidence = UNAVAILABLE
Overall.consolidation_status = NOT_CONSOLIDATED
limitation = CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003
```

Não existe fallback silencioso para outro cálculo de Overall.

## 10. Calibração

Contrato inicial:

```text
format_version = SG003-MODEL-001
model_version = GEO-LR-001
outcome = CITED_BINARY
model = L2_REGULARIZED_LOGISTIC_REGRESSION
split = DOMAIN_HOLDOUT_70_30_V1
```

Outcome:

```text
CITED = 1
NOT_CITED = 0
```

Fonte inicial: `CONTROLLED_QUERY_RUNS` persistidos no domínio Observed Generative Visibility.

### Promotion gate mínimo

| Critério | Mínimo |
|---|---:|
| Domínios | 40 |
| Domínios de validação | 12 |
| Engines | 2 |
| Queries por domínio | 10 |
| Repetições por query/engine | 3 |
| Observações válidas | 2400 |
| AUC holdout | 0,60 |
| Brier | menor que baseline por prevalência de treino |

O split deve ser por domínio para reduzir leakage entre queries do mesmo site.

Artifact abaixo do gate recebe `EXPERIMENTAL` e não pode consolidar Overall.

## 11. Confidence do Overall

A Confidence final é o mínimo entre:

- menor Confidence das dimensões aplicáveis;
- `calibration_confidence` do artifact.

Artifact validado recebe `MEDIUM` por padrão. `HIGH` exige amostra/desempenho superiores definidos e persistidos no protocolo.

## 12. Parametrização

Pode variar por operação/coleta:

- AUDs usados na calibração;
- dataset version;
- engines/query-runs coletados;
- volume de observações;
- localização do artifact.

Não varia por auditoria:

- fórmula;
- feature set;
- promotion gate;
- split por domínio;
- regularização;
- coeficientes de um artifact validado;
- regras de Coverage/Confidence/Consolidation.

Mudança incompatível exige nova versão de scoring/model contract.

## 13. Sem IA

A auditoria base continua podendo executar sem LLM. Ausência de IA pode reduzir Coverage/Confidence de dimensões sem converter regras semânticas em `FAIL`.

O cálculo normal do `003` usa artifact local e não gera chamada externa adicional.

## 14. Structured Data

JSON-LD não é requisito universal.

`STRUCTURED_DATA = NOT_APPLICABLE` legítimo não recebe penalização direta. Se markup existir, a dimensão torna-se aplicável normalmente.

## 15. Reprodutibilidade

`BR-GEO-054` deve registrar/reabrir:

- RuleExecutions e versões;
- ScoreContributions;
- scoring version `SCORE-GEO-003`;
- model version;
- dataset version;
- SHA-256 do artifact;
- limitações e estados de aplicabilidade.

A reprodução não pode exigir nova execução do website nem nova chamada de IA.

## 16. Histórico

Nenhum AUD persistido é recalculado automaticamente por mudança de model artifact ou geração de relatório.

Relatórios históricos/consolidados devem segmentar pontos por `scoring_version`. A transição `002 → 003` é quebra metodológica e não deve ser apresentada como série contínua sem ressalva explícita.

## 17. Evidência externa

O RASAi continua separando:

1. requisito/sinal oficial externo;
2. métrica externa definida/calibrada por terceiros;
3. regra/heurística RASAi;
4. modelo RASAi empiricamente calibrado.

A calibração do Overall não transforma Core Web Vitals, Lighthouse, WCAG, E-E-A-T ou qualquer outra referência externa em homologação do índice completo.

## 18. Relatório

`readiness.html` continua sendo a página canônica do SARI.

`score-geo-003.html` expõe:

- model version;
- dataset version;
- status de calibração;
- AUC/Brier;
- promotion gate;
- Overall por device;
- compatibilidade histórica.

Detalhes operacionais: `docs/SCORE_GEO_003.md`.
