# SCORE-GEO-004

`SCORE-GEO-004` é o método de scoring vigente do RASAi e alimenta o índice público `SARI-001 - Search & AI Readiness Index`.

## Estado do contrato

O RASAi permanece em desenvolvimento/pré-produção. Esta recalibração substitui a implementação experimental anterior do mesmo identificador `SCORE-GEO-004`; não existe compatibilidade ativa com o antigo Overall de peso igual.

Auditorias de desenvolvimento produzidas pelo contrato antigo devem ser regeneradas quando precisarem ser comparadas. O histórico técnico permanece no Git.

Contrato vigente:

```text
SCORING_VERSION              SCORE-GEO-004
OVERALL_AGGREGATION_VERSION HIERARCHICAL_WEIGHTED_READINESS_V1
DIMENSION_WEIGHT_VERSION     SARI_DIMENSION_WEIGHTS_V1
GROUP_WEIGHT_VERSION         SARI_GROUP_WEIGHTS_V1
CRITICAL_GATE_VERSION        SARI_CRITICAL_GATES_V1
MEASUREMENT_CONFIDENCE       WEIGHTED_MEASUREMENT_CONFIDENCE_V1
```

## Objetivo

O método produz um índice operacional que pode ser calculado, auditado e reproduzido em uma auditoria individual sem depender de corpus externo ou artifact de calibração.

O contrato separa:

- qualidade medida do website no universo avaliado;
- Coverage, Confidence e Consolidation da medição;
- Critical Readiness Gates;
- métricas externas independentes;
- outcomes observados de Search e AI Search.

O Overall não é probabilidade de ranking, tráfego, resposta ou citação.

A apresentação pública também não deve transformar o número 0-100 em uma conclusão isolada: **readiness publicada = qualidade medida + força da medição + Critical Readiness Gates**.

## Hierarquia de agregação

```text
RuleExecution
→ page/global scope
→ scoring_group
→ dimension
→ weighted Overall (SARI)
```

O peso de um `scoring_group` é fixo dentro da dimensão. Para grupos executados em múltiplas páginas:

```text
Scope Weight = Group Weight / número de escopos aplicáveis
```

Consequência: o peso metodológico de `ROBOTS`, `SITEMAP` ou qualquer outro grupo não depende do número total de páginas auditadas.

## Dimensões e pesos

| Dimensão | Peso |
|---|---:|
| `DISCOVERY_ACCESS` | 0.15 |
| `INDEXABILITY` | 0.15 |
| `CONTENT_EXTRACTABILITY` | 0.15 |
| `SEMANTIC_STRUCTURE` | 0.07 |
| `ENTITY_CLARITY` | 0.08 |
| `STRUCTURED_DATA` | 0.05 |
| `ANSWERABILITY` | 0.07 |
| `CITATION_READINESS` | 0.07 |
| `EVIDENCE_TRUST` | 0.08 |
| `INTENT_COVERAGE` | 0.05 |
| `CONTENT_VALUE` | 0.08 |

Os pesos totalizam 1.0 e não são configuráveis pelo operador.

## Pesos dos scoring groups

### DISCOVERY_ACCESS

```text
PAGE_ACCESS      0.30
ROBOTS           0.15
SITEMAP          0.05
REDIRECT         0.10
SPA_ROUTE        0.10
SPA_NAVIGATION   0.10
INTERNAL_LINKS   0.20
```

### INDEXABILITY

```text
INDEX_DIRECTIVES 0.35
CANONICAL        0.30
SOFT_ERROR       0.35
```

### CONTENT_EXTRACTABILITY

```text
RENDER_ACCESS       0.30
JS_CONTENT          0.25
CONTENT_EXTRACTION  0.35
DUPLICATE_CONTENT   0.10
```

### SEMANTIC_STRUCTURE

```text
SEMANTIC_TITLE      0.30
SEMANTIC_HIERARCHY  0.30
SEMANTIC_TOPIC      0.40
```

### ENTITY_CLARITY

```text
ENTITY_PRIMARY      0.35
ENTITY_CONTEXT      0.40
ENTITY_AMBIGUITY    0.25
```

### STRUCTURED_DATA

```text
STRUCTURED_DATA_SYNTAX       0.40
STRUCTURED_DATA_CONSISTENCY  0.60
```

### ANSWERABILITY

```text
PRIMARY_INTENT   0.35
PRIMARY_ANSWERS  0.65
```

### CITATION_READINESS

```text
FACTUAL_CLAIMS   0.20
FACTUAL_CONTEXT  0.45
INFERENCE_LOAD   0.35
```

### EVIDENCE_TRUST

```text
ATTRIBUTION      0.40
RESPONSIBILITY   0.35
FRESHNESS        0.25
```

### INTENT_COVERAGE

```text
INTENT_SET       0.45
INTENT_GAPS      0.55
```

### CONTENT_VALUE

```text
CONTENT_USEFULNESS        0.40
CONTENT_DIFFERENTIATION   0.30
CONTENT_DEPTH             0.30
```

Cada conjunto de grupos de uma dimensão totaliza 1.0.

## RuleResult e fatores

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00
```

Fatores WARNING específicos permanecem estáticos/versionados quando necessários, por exemplo nos grupos de sitemap/robots.

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são tratados como zero.

## Dimension Score

```text
Dimension Score =
  sum(scope_weight × result_factor avaliados)
  / sum(scope_weight avaliados)
  × 100
```

```text
Dimension Coverage =
  evaluated applicable weight
  / total applicable weight
```

Uma execução `UNKNOWN`/`ERROR` mantém o peso no universo aplicável, mas não no universo avaliado, reduzindo Coverage.

## Overall

```text
Overall =
  sum(dimension_weight × dimension_score medido)
  / sum(dimension_weight medido e aplicável)
```

Dimensão legitimamente `NOT_APPLICABLE` sai do denominador. Uma dimensão não crítica insuficientemente medida reduz Coverage/Confidence; dimensões críticas insuficientemente medidas bloqueiam Consolidation.

### Leitura do valor numérico

O número 0-100 é a **qualidade ponderada do universo efetivamente medido**. Ele permanece matematicamente separado de Coverage/Confidence/Consolidation e dos Critical Gates para evitar que ausência de evidência ou falha operacional externa seja convertida em defeito fictício do website.

Consequentemente, um valor alto pode coexistir com medição parcial ou gate crítico. Isso é matematicamente válido, mas não pode ser apresentado como “readiness excelente” sem qualificação.

Contrato de apresentação:

```text
Overall 96 + CONSOLIDATED + READY
=> Readiness pronta | qualidade medida Excelente

Overall 96 + PARTIAL
=> Readiness com medição parcial | qualidade medida Excelente

Overall 96 + CONSOLIDATED + BLOCKED
=> Readiness bloqueada | qualidade medida Excelente
```

A interface deve usar o estado de readiness/medição como badge primária. A banda numérica fica como qualificação secundária e auditável.

## Overall Coverage

```text
Overall Coverage =
  sum(dimension_weight × dimension_coverage)
  / sum(dimension_weight aplicável)
```

## Confidence

Dimensão:

```text
HIGH        coverage >= 0.90, evidência completa, zero errors
MEDIUM      coverage >= 0.80, zero errors
LOW         avaliação abaixo dos critérios acima
UNAVAILABLE coverage <= 0
```

Overall usa `WEIGHTED_MEASUREMENT_CONFIDENCE_V1`:

- qualquer dimensão crítica `LOW`/`UNAVAILABLE` mantém Overall Confidence `LOW`;
- demais dimensões contribuem proporcionalmente aos próprios pesos;
- ausência de uma dimensão pequena não domina sozinha toda a Confidence.

## Consolidation

Dimensão:

```text
CONSOLIDATED     coverage >= 0.80 e confidence HIGH/MEDIUM
PARTIAL          coverage >= 0.50 abaixo do gate completo
NOT_CONSOLIDATED coverage < 0.50 ou confidence UNAVAILABLE
NOT_APPLICABLE   fora do universo aplicável
```

Overall:

- `CONSOLIDATED` quando Coverage >= 0.80, Confidence HIGH/MEDIUM e nenhuma dimensão crítica aplicável está sem medição suficiente;
- `PARTIAL` quando existe leitura útil com Coverage >= 0.50 mas o gate completo não foi atingido;
- `NOT_CONSOLIDATED` quando a medição não sustenta a conclusão.

Um score baixo pode ser `CONSOLIDATED`: isso significa que a baixa qualidade foi medida com força suficiente.

## Critical Readiness Gates

### DISCOVERY

```text
DISCOVERY_ACCESS:
PAGE_ACCESS
ROBOTS
REDIRECT
```

### INDEXABILITY

```text
INDEXABILITY:
INDEX_DIRECTIVES
CANONICAL
SOFT_ERROR
```

### EXTRACTION

```text
CONTENT_EXTRACTABILITY:
RENDER_ACCESS
JS_CONTENT
CONTENT_EXTRACTION
```

Estados:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

O estado geral é `READY`, `ATTENTION`, `BLOCKED` ou `UNKNOWN`.

Critical Gates qualificam readiness e **não truncam artificialmente o valor 0-100**. São persistidos em `limitations` do Overall para manter a rastreabilidade do contrato. Na apresentação pública, porém, `BLOCKED`, `UNKNOWN` e `ATTENTION` prevalecem sobre uma banda numérica positiva para evitar falso positivo executivo.

## Precedência de evidência

No mesmo page/global scope e `scoring_group`:

```text
DETERMINISTIC_PRIMARY > AI_CORROBORATIVE
```

Se existe PASS/WARNING/FAIL determinístico conclusivo, uma avaliação IA corroborativa não o substitui.

Se não existe resultado determinístico avaliado, uma execução IA evidence-bound contratada pode resolver o grupo quando aplicável.

A IA nunca define peso, fator, threshold ou Overall.

## Content Value

Regras:

```text
BR-GEO-057 CONTENT_USEFULNESS
BR-GEO-058 CONTENT_DIFFERENTIATION
BR-GEO-059 CONTENT_DEPTH
```

Baseline:

```text
CONTENT-VALUE-BASELINE-001
```

A baseline usa conteúdo principal persistido e só conclui dentro do que pode ser sustentado localmente. Diferenciação/originalidade não demonstrada permanece `UNKNOWN`, não `FAIL`.

## Structured Data

Structured Data representa 5% do SARI quando aplicável e não é requisito universal.

- ausência legitimamente não aplicável não deve receber zero;
- markup existente inválido/contraditório pode ser desfavorável;
- consistência pode usar avaliação evidence-bound quando há evidência suficiente;
- nenhum markup especial de GEO/AI é presumido obrigatório.

## Lighthouse e demais métricas externas

Não entram diretamente no Overall:

- Lighthouse Performance;
- Lighthouse Accessibility;
- Lighthouse Best Practices;
- Lighthouse SEO;
- Core Web Vitals / CrUX;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- Search Console;
- SERP e concorrentes;
- Observed Generative Visibility;
- tráfego/conversão;
- tokens/custos de IA.

Um audit individual do Lighthouse ou outro serviço externo pode ser classificado como `CORROBORATIVE_EVIDENCE` somente quando existir mapeamento explícito para a mesma condição técnica de uma BR-GEO. O category score nunca é input direto.

### Falhas operacionais de integrações

Timeout, quota, autenticação inválida, indisponibilidade do provider, erro HTTP do serviço externo ou falha de transporte são estados do **integrador/medição**, não resultados do website. Esses eventos podem:

- reduzir Coverage/Confidence;
- deixar uma regra `UNKNOWN`;
- aparecer em diagnóstico/observabilidade;
- gerar custo/telemetria quando aplicável.

Eles não podem gerar `FAIL` do website sem evidência técnica sobre o próprio target. Essa separação é obrigatória para evitar penalizar o domínio por erro de terceiros.

## IA e baseline semântico

Regras `BR-GEO-028..049` continuam podendo usar:

```text
SEMANTIC-BASELINE-001
```

ou provider semântico evidence-bound quando configurado.

Falha de provider não é falha do website. Quando a regra não pode ser concluída defensavelmente, o resultado permanece `UNKNOWN`.

## Reprodutibilidade

`BR-GEO-054` verifica que o resultado pode ser reconstruído a partir de:

- RuleExecutions e versões;
- evidências persistidas;
- manifesto rule → dimension → scoring_group;
- pesos fixos de grupo/dimensão;
- ScoreContributions;
- Coverage/Confidence/Consolidation;
- contrato dos Critical Gates.

Não é necessário reexecutar website, IA ou APIs externas para reproduzir o cálculo persistido.

## Relatórios

```text
report/readiness.html
report/scoring.html
```

`readiness.html` é a superfície analítica do SARI-001 e deve destacar separadamente:

- qualidade medida 0-100;
- Coverage/Confidence/Consolidation;
- estado de readiness e Critical Gates.

`scoring.html` expõe o contrato vigente, pesos, RuleExecutions representativas, contribuições, gates e rastreabilidade.

O filename é version-neutral; a versão pertence a `scoring_version` e ao conteúdo.

## Revisão de calibração de setembro de 2026

A revisão motivada por resultados frequentemente acima de 90 verificou a aritmética, pesos, tratamento de `WARNING/FAIL/UNKNOWN/ERROR`, gates críticos e relação com integrações externas.

Conclusão:

- não foi encontrada base empírica suficiente para alterar pesos de dimensão/grupo apenas para “forçar” maior dispersão das notas;
- `FAIL`/`WARNING` contratados já reduzem o score conforme o peso da condição;
- `UNKNOWN/ERROR` reduzem força da medição e não devem virar falha fictícia;
- erros de integrações independentes não devem reduzir o website score por si só;
- o problema comprovado era a apresentação de uma banda numérica alta como juízo positivo de readiness mesmo com `PARTIAL`, `NOT_CONSOLIDATED`, `BLOCKED` ou `UNKNOWN`.

Por isso, esta revisão preserva a aritmética `SCORE-GEO-004` e endurece a semântica de publicação nos HTMLs executivos.

## Limite de validade

`SCORE-GEO-004` é metodologia proprietária do RASAi, transparente e reproduzível. Os pesos são decisões metodológicas pré-produção, não coeficientes causais empiricamente provados.

Validação futura com outcomes externos poderá sustentar nova calibração. Após entrada em produção ou existência de série histórica contratual, uma mudança incompatível deverá receber versionamento explícito em vez de sobrescrever silenciosamente o método.