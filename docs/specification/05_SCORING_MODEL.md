# SCORING_MODEL.md

**Estado no baseline de desenvolvimento:** APPROVED / CURRENT  
**Scoring baseline:** `SCORE-GEO-004`  
**Public index:** `SARI-001`  
**Aggregation contract:** `HIERARCHICAL_WEIGHTED_READINESS_V1`

## 0. Natureza metodológica

`SCORE-GEO-004` é o método proprietário e versionado de scoring vigente do RASAi.

`APPROVED` significa aprovado como baseline normativa interna. Não significa homologação por Google, OpenAI, Microsoft, Anthropic, NIST, W3C, schema.org ou outro mantenedor.

O método é determinístico, evidence-bound e reproduzível por auditoria. O Overall não é probabilidade de ranking, tráfego, conversão, resposta ou citação futura.

Validação empírica externa pode existir como pesquisa independente, mas não é input obrigatório do runtime e não altera silenciosamente o score.

Score, Coverage, Confidence, Consolidation e Critical Readiness Gates são conceitos distintos. Qualidade medida não pode ser confundida com completude da medição.

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

O runtime registra ainda identificadores metodológicos do contrato ativo, incluindo agregação, pesos de dimensão/grupo, Confidence e Critical Gates.

## 2. Dimensões e pesos

O contrato vigente possui onze dimensões:

| Dimensão | Peso no Overall |
|---|---:|
| `DISCOVERY_ACCESS` | 15% |
| `INDEXABILITY` | 15% |
| `CONTENT_EXTRACTABILITY` | 15% |
| `SEMANTIC_STRUCTURE` | 7% |
| `ENTITY_CLARITY` | 8% |
| `STRUCTURED_DATA` | 5% |
| `ANSWERABILITY` | 7% |
| `CITATION_READINESS` | 7% |
| `EVIDENCE_TRUST` | 8% |
| `INTENT_COVERAGE` | 5% |
| `CONTENT_VALUE` | 8% |
| **Total** | **100%** |

`DISCOVERY_ACCESS` substitui a antiga denominação interna `TECHNICAL_ACCESSIBILITY`, evitando confusão com Accessibility/WCAG.

Desktop e Mobile permanecem separados. Um dispositivo não auditado não pode ser projetado como resultado válido.

Os pesos são fixos no contrato e não configuráveis por auditoria.

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

Fatores default de qualidade:

```text
PASS    = 1.00
WARNING = 0.50
FAIL    = 0.00
```

Alguns grupos possuem `warning_factor` específico e versionado.

## 4. Hierarquia de cálculo

O SARI não soma RuleExecutions diretamente. A hierarquia canônica é:

```text
RuleExecution
   ↓
página/escopo global
   ↓
Scoring Group
   ↓
Dimension Score
   ↓
SARI Overall
```

Cada `scoring_group` possui peso fixo dentro de sua dimensão. Quando um grupo é aplicável em múltiplas páginas/escopos:

```text
Scope Weight = Group Weight / quantidade de escopos aplicáveis do grupo
```

Assim, quantidade de páginas não multiplica a importância metodológica do grupo nem reduz artificialmente o peso de sinais globais.

A tabela de rule-to-dimension/group é explícita no contrato de scoring; não é inferida por faixa numérica de `BR-GEO-*`.

## 5. Precedência de evidência no grupo

Quando execuções determinísticas e execuções AI-correlative/corroborativas coexistem no mesmo escopo/grupo:

1. uma execução determinística avaliada (`PASS`, `WARNING`, `FAIL`) tem precedência;
2. IA corroborativa não pode sobrescrever fato determinístico já avaliado;
3. IA pode contribuir apenas quando o contrato permitir e a evidência determinística equivalente não estiver avaliada;
4. ausência de IA nunca é convertida silenciosamente em `FAIL`.

## 6. Score da dimensão

Para cada grupo aplicável, seu peso é dividido entre os escopos aplicáveis.

Fórmula:

```text
Dimension Score =
  sum(Scope Weight × Result Factor avaliados)
  / sum(Scope Weight avaliados)
  × 100
```

Somente `PASS`, `WARNING` e `FAIL` participam do denominador do **valor** da dimensão.

Isso é intencional: `UNKNOWN` e `ERROR` reduzem Coverage/Confidence, mas não são imputados como qualidade zero.

## 7. Coverage da dimensão

```text
Dimension Coverage =
  evaluated applicable weight / total applicable weight
```

Evaluated:

```text
PASS, WARNING, FAIL
```

Applicable:

```text
PASS, WARNING, FAIL, UNKNOWN, ERROR
```

`NOT_APPLICABLE` legítimo fica fora do universo aplicável.

Coverage mede completude da análise, não qualidade do website.

Um grupo contratualmente aplicável deve ser representado por RuleExecution no pipeline. Falha de aquisição/pré-requisito deve materializar estado explícito (`UNKNOWN`, `ERROR` ou `NOT_APPLICABLE` bloqueado conforme o contrato), e não desaparecer silenciosamente do universo medido.

## 8. Aplicabilidade da dimensão

### Sem RuleExecution para a dimensão

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_CONSOLIDATED
limitation = NO_RULE_EXECUTIONS
```

Ausência total de execução não é `NOT_APPLICABLE`.

### Todas legitimamente NOT_APPLICABLE

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_APPLICABLE
limitation = NO_APPLICABLE_RULES
```

### Pré-requisito bloqueado

Reason contendo `PREREQUISITE_BLOCKED` mantém o universo afetado não consolidado; não pode ser promovido a `NOT_APPLICABLE` benigno para elevar score ou Coverage.

## 9. Confidence da dimensão

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas os critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

Os thresholds são governança interna versionada.

`Confidence LOW` isoladamente não gera finding nem ordem de reescrita.

## 10. Consolidation da dimensão

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          avaliação disponível com Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

## 11. Overall - SCORE-GEO-004

Existem separadamente:

- Overall Readiness - Desktop;
- Overall Readiness - Mobile.

Contrato de agregação vigente:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Fórmula do valor:

```text
SARI =
  sum(Dimension Weight × Dimension Score medido)
  / sum(Dimension Weight medido e aplicável)
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero nem 100.

Uma dimensão aplicável sem valor não recebe imputação numérica. Seu peso ausente reduz a qualidade da medição através de Coverage/Confidence e dos gates de consolidação.

## 12. Coverage do Overall

```text
Overall Coverage =
  sum(Dimension Weight × Dimension Coverage)
  / sum(Dimension Weight aplicável)
```

Uma dimensão aplicável sem medição possui Coverage zero e, portanto, reduz a Coverage ponderada do Overall.

Uma dimensão não crítica incompleta não apaga automaticamente o valor numérico calculado sobre o universo efetivamente medido. A publicação analítica ainda depende do gate de Consolidation.

## 13. Confidence do Overall

O Overall combina:

1. rigor crítico para `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY`;
2. Confidence ponderada pelos pesos das dimensões aplicáveis.

Se uma dimensão crítica aplicável estiver `LOW` ou `UNAVAILABLE`, o Overall Confidence permanece `LOW`.

Para dimensões não críticas, a influência acompanha o peso metodológico, evitando que uma dimensão pequena domine isoladamente a confiança global.

Não existe `calibration_confidence` externa obrigatória no runtime 004.

## 14. Consolidation do Overall

```text
CONSOLIDATED
  se existe valor mensurável
  e nenhuma dimensão crítica aplicável está sem medição suficiente
  e Overall Coverage >= 80%
  e Overall Confidence = HIGH ou MEDIUM

PARTIAL
  se existe valor mensurável
  e Coverage >= 50%
  e Confidence está disponível
  mas o gate completo não foi atingido

NOT_CONSOLIDATED
  quando não existe valor mensurável,
  existe blocker de medição crítica,
  ou Coverage/Confidence ficam abaixo do mínimo
```

Uma dimensão **não crítica** sem medição suficiente pode coexistir com Overall consolidado somente quando a Coverage ponderada e a Confidence ainda satisfazem o contrato. A limitação deve permanecer explícita (`DIMENSION_MEASUREMENT_LIMITED:*`).

Estado insuficiente nunca é convertido em zero.

## 15. Critical Readiness Gates

O valor do SARI e o estado operacional de prontidão são separados.

Gates vigentes:

- `DISCOVERY`: grupos `PAGE_ACCESS`, `ROBOTS`, `REDIRECT`;
- `INDEXABILITY`: grupos `INDEX_DIRECTIVES`, `CANONICAL`, `SOFT_ERROR`;
- `EXTRACTION`: grupos `RENDER_ACCESS`, `JS_CONTENT`, `CONTENT_EXTRACTION`.

Estados de gate:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

Estado agregado de readiness:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

Um `FAIL` em condição crítica pode produzir `BLOCKED` sem alterar artificialmente o valor de outras dimensões. Qualidade ruim pode estar perfeitamente medida e, portanto, ser `CONSOLIDATED`.

## 16. Content Value

`CONTENT_VALUE` possui peso de 8% e é uma família `RASAI_HEURISTIC`.

Regras atuais:

- `BR-GEO-057`: utilidade/especificidade não trivial;
- `BR-GEO-058`: diferenciação, experiência, análise ou dado próprio explicitamente sustentado quando alegado;
- `BR-GEO-059`: profundidade/contexto proporcionais ao conteúdo e à evidência disponível.

Ausência de prova de diferenciação/originalidade não vira `FAIL`; deve permanecer `UNKNOWN` quando não houver base suficiente para conclusão.

## 17. Structured Data

JSON-LD não é requisito universal.

`STRUCTURED_DATA = NOT_APPLICABLE` legítimo não recebe penalização direta. Se markup existir ou a regra se tornar aplicável, a dimensão é avaliada normalmente.

## 18. Parametrização

Pode variar por operação/coleta:

- URLs/domínios;
- dispositivo;
- IA/provider/modelo;
- Web Performance;
- Synthetic Apdex;
- limites de coleta e execução.

Não varia arbitrariamente por auditoria:

- conjunto de dimensões;
- pesos de dimensão/grupo;
- fatores versionados;
- fórmula do Overall;
- gates de Coverage/Confidence/Consolidation;
- Critical Readiness Gates.

O RASAi está em desenvolvimento/pré-produção. A recalibração corrente permanece sob `SCORE-GEO-004` e é distinguida pelo contrato de agregação `HIERARCHICAL_WEIGHTED_READINESS_V1`; dados de desenvolvimento gerados pelo contrato anterior de agregação são não comparáveis e devem ser regenerados quando reutilizados.

Após existência de série histórica/contrato externo estável, mudança metodológica incompatível deve criar nova versão de scoring em vez de reinterpretar dados persistidos.

## 19. Sem IA

A auditoria base continua podendo executar sem LLM. Ausência de IA pode reduzir Coverage/Confidence de dimensões sem converter regras semânticas em `FAIL`.

O cálculo do Overall não chama IA e não depende de provider específico.

## 20. Reprodutibilidade

`BR-GEO-054` deve permitir reconstrução a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- `scoring_version = SCORE-GEO-004`;
- evidências persistidas;
- limitações e estados de aplicabilidade;
- `HIERARCHICAL_WEIGHTED_READINESS_V1`;
- versões persistidas/identificáveis de pesos, Confidence e Critical Gates.

A reprodução não pode exigir nova execução do website nem nova chamada de IA.

## 21. Histórico e comparabilidade

Nenhum AUD persistido é recalculado automaticamente por geração de relatório ou mudança metodológica.

Comparação longitudinal deve exigir compatibilidade metodológica. Durante a fase pré-produção, auditorias 004 produzidas sob o contrato experimental anterior de agregação não devem ser comparadas numericamente com `HIERARCHICAL_WEIGHTED_READINESS_V1` sem regeneração explícita.

## 22. Evidência externa

O RASAi separa:

1. requisito/sinal oficial externo;
2. métrica externa definida/calibrada por terceiros;
3. regra/heurística RASAi;
4. outcomes externos observados.

Core Web Vitals, Lighthouse, WCAG, Apdex, E-E-A-T/YMYL e Observed Generative Visibility não entram automaticamente no Overall `SCORE-GEO-004`.

## 23. Relatório

`readiness.html` é a página canônica do SARI.

`scoring.html` é a página canônica estável da metodologia de scoring e expõe:

- `scoring_version` efetiva;
- contrato de agregação;
- pesos de dimensão/grupo;
- fórmula da dimensão e Overall;
- Coverage;
- Confidence;
- Consolidation;
- Critical Readiness Gates;
- limitações;
- compatibilidade entre dados de desenvolvimento.

Detalhes operacionais: `docs/SCORE_GEO_004.md`, `docs/SCORING_GUIDE.md` e `docs/SARI_READINESS_INDEX.md`.
