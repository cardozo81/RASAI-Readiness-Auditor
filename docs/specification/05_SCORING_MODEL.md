# Modelo de Pontuação de Prontidão

**Estado:** vigente  
**Versão pública do método:** **001**  
**Contrato técnico de pontuação:** `SCORE-GEO-004`  
**Índice público:** **Search & AI Readiness Index - Índice de Prontidão Search & IA**, versão pública **001**, ID técnico `SARI-001`  
**Agregação:** **Agregação Hierárquica Ponderada de Prontidão**, versão pública **001**, ID técnico `HIERARCHICAL_WEIGHTED_READINESS_V1`

## 0. Natureza metodológica

O **Método de Pontuação de Prontidão** é a metodologia proprietária e versionada do RASAi; `SCORE-GEO-004` é seu contrato técnico vigente.

O status vigente identifica um contrato metodológico interno do produto. Não significa homologação por Google, OpenAI, Microsoft, Anthropic, NIST, W3C, Schema.org ou outro mantenedor.

O método é determinístico, vinculado a evidências e reproduzível por auditoria. Overall não é probabilidade de ranking, tráfego, conversão, resposta ou citação.

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

Os nomes acima permanecem em inglês quando correspondem diretamente a campos técnicos persistidos. Em documentação e interfaces humanas, apresentar imediatamente a tradução em pt-BR quando o termo for necessário, mantendo a explicação metodológica em pt-BR.

`scoring_version` é parte do contrato de comparabilidade e deve permanecer persistido mesmo que a rota HTML seja neutra quanto à versão.

O runtime registra ainda identificadores metodológicos do contrato ativo, incluindo agregação, pesos de dimensão/grupo, Confidence e Critical Gates.

## 2. Dimensões e pesos

O contrato vigente possui onze dimensões:

| Dimensão | Valor vigente | Valores permitidos | Recomendado |
|---|---:|---|---|
| `DISCOVERY_ACCESS` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `INDEXABILITY` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CONTENT_EXTRACTABILITY` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `SEMANTIC_STRUCTURE` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `ENTITY_CLARITY` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `STRUCTURED_DATA` | 5% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `ANSWERABILITY` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CITATION_READINESS` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `EVIDENCE_TRUST` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `INTENT_COVERAGE` | 5% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CONTENT_VALUE` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| **Total** | **100%** | contrato fixo | preservar |

`DISCOVERY_ACCESS` é a dimensão canônica para descoberta e acesso de crawlers e deve permanecer semanticamente distinta de Accessibility/WCAG.

Desktop e Mobile permanecem separados. Um dispositivo não auditado não pode ser projetado como resultado válido.

Os pesos são fixos no contrato e não configuráveis por auditoria.

## 3. RuleResult

Valores permitidos:

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são `FAIL`.

Fatores vigentes de qualidade:

| Resultado | Valor vigente | Valores permitidos | Recomendado |
|---|---:|---|---|
| `PASS` | `1.00` | fixo pelo contrato do scoring | preservar |
| `WARNING` | `0.50` | default do contrato; alguns grupos podem possuir `warning_factor` específico e versionado | usar somente o valor versionado do grupo |
| `FAIL` | `0.00` | fixo pelo contrato do scoring | preservar |

Esses fatores não são parâmetros livres do usuário.

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

Quando execuções determinísticas e execuções corroborativas externas ou de IA coexistem no mesmo escopo/grupo:

1. uma execução determinística avaliada (`PASS`, `WARNING`, `FAIL`) tem precedência;
2. evidência corroborativa não pode sobrescrever fato determinístico já avaliado;
3. uma contribuição corroborativa só participa quando o contrato explícito do grupo permitir;
4. ausência de uma fonte corroborativa nunca é convertida silenciosamente em `FAIL`.

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

Resultados considerados avaliados:

```text
PASS
WARNING
FAIL
```

Resultados pertencentes ao universo aplicável:

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
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

### Todas legitimamente `NOT_APPLICABLE`

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

| Estado | Critério vigente | Valores permitidos | Recomendado |
|---|---|---|---|
| `HIGH` | Coverage >= 90%, evidência completa e zero errors | fixo no contrato | preservar |
| `MEDIUM` | Coverage >= 80% e zero errors | fixo no contrato | preservar |
| `LOW` | existe avaliação, mas os critérios anteriores não foram satisfeitos | fixo no contrato | interpretar como força limitada da medição, não como qualidade baixa automática |
| `UNAVAILABLE` | Coverage <= 0 | fixo no contrato | preservar ausência |

Os thresholds são governança interna versionada e não configuráveis por auditoria.

`Confidence LOW` isoladamente não gera finding nem ordem de reescrita.

## 10. Consolidation da dimensão

| Estado | Critério vigente | Valores permitidos | Recomendado |
|---|---|---|---|
| `CONSOLIDATED` | Coverage >= 80% e Confidence `HIGH`/`MEDIUM` | fixo no contrato | preservar |
| `PARTIAL` | avaliação disponível com Coverage >= 50% abaixo do gate completo | fixo no contrato | preservar |
| `NOT_CONSOLIDATED` | Coverage < 50% ou Confidence `UNAVAILABLE` | fixo no contrato | preservar |
| `NOT_APPLICABLE` | dimensão legitimamente fora do universo aplicável | fixo no contrato | não imputar score |

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

Uma dimensão aplicável sem valor não recebe imputação numérica. Seu peso ausente reduz a qualidade da medição por meio de Coverage/Confidence e dos gates de consolidação.

## 12. Coverage do Overall

```text
Overall Coverage =
  sum(Dimension Weight × Dimension Coverage)
  / sum(Dimension Weight aplicável)
```

Uma dimensão aplicável sem medição possui Coverage zero e, portanto, reduz a Coverage ponderada do Overall.

Uma dimensão não crítica incompleta não apaga automaticamente o valor numérico calculado sobre o universo efetivamente medido. A publicação analítica ainda depende do gate de Consolidation.

## 13. Confidence do Overall

Overall combina:

1. rigor crítico para `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY`;
2. Confidence ponderada pelos pesos das dimensões aplicáveis.

Se uma dimensão crítica aplicável estiver `LOW` ou `UNAVAILABLE`, Overall Confidence permanece `LOW`.

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
  existe bloqueador de medição crítica,
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

Estados permitidos de gate:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

Estados agregados permitidos de readiness:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

Um `FAIL` em condição crítica pode produzir `BLOCKED` sem alterar artificialmente o valor de outras dimensões. Qualidade ruim pode estar perfeitamente medida e, portanto, ser `CONSOLIDATED`.

## 16. Content Value

`CONTENT_VALUE` possui peso vigente de 8% e é uma família `RASAI_HEURISTIC`.

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

Defaults e valores permitidos de parâmetros operacionais pertencem às referências canônicas `../ENVIRONMENT_VARIABLES.md`, `../CONFIGURATION.md` e `../CLI_REFERENCE.md`; esta especificação não redefine valores operacionais livres.

Mudança metodológica incompatível deve criar nova versão explícita de scoring, em vez de reinterpretar dados persistidos.

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

## 21. Persistência e comparabilidade

Nenhum `AUD-*` persistido é recalculado automaticamente por geração de relatório ou por alteração metodológica.

Comparação longitudinal exige compatibilidade metodológica. Auditorias persistidas com `scoring_version` ou contrato de agregação incompatível não devem ser comparadas numericamente como se fossem equivalentes; a superfície consumidora deve declarar não comparabilidade/limitação correspondente.

## 22. Evidência externa

O RASAi separa:

1. requisito/sinal oficial externo;
2. métrica externa definida/calibrada por terceiros;
3. regra/heurística RASAi;
4. outcomes externos observados.

Core Web Vitals, Lighthouse, WCAG, Apdex, E-E-A-T/YMYL e Observed Generative Visibility não entram automaticamente no Overall `SCORE-GEO-004`.

A exceção explicitamente score-eligible desta família é `BR-GEO-060`, que usa Common Crawl somente como corroboração externa positiva de `DISCOVERY_ACCESS`:

- grupo `EXTERNAL_CRAWL_CORROBORATION`;
- peso de 3% dentro de `DISCOVERY_ACCESS`;
- impacto máximo teórico de 0,45 ponto no Overall;
- somente `PASS` pode ser materializado pela evidência externa qualificada;
- ausência, erro, timeout, indisponibilidade, alvo privado ou ausência de registro não geram `FAIL`, zero, redução de Coverage ou redução de Confidence;
- não participa dos Critical Readiness Gates;
- a evidência e a RuleExecution são persistidas antes do cálculo para preservar reprodutibilidade.

O contrato específico está em `../SARI_EXTERNAL_CRAWL_CORROBORATION.md`.

## 23. Relatório

`sari.html` é a página canônica do SARI.

`methodology.html` é a página canônica estável do **Método de Pontuação de Prontidão** e expõe:

- `scoring_version` efetiva;
- contrato de agregação;
- pesos de dimensão/grupo;
- fórmula da dimensão e Overall;
- Coverage;
- Confidence;
- Consolidation;
- Critical Readiness Gates;
- limitações;
- compatibilidade metodológica dos dados persistidos.

Detalhes operacionais: `docs/SCORE_GEO_004.md`, `docs/SCORING_GUIDE.md` e `docs/SARI_READINESS_INDEX.md`.
