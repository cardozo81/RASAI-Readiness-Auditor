# Search & AI Readiness Index - SARI-001

## 1. Objetivo

O **Search & AI Readiness Index (`SARI-001`)** é a identidade pública da metodologia proprietária do RASAi para consolidar sinais de prontidão relacionados a descoberta, interpretação, recuperação, resposta e uso do conteúdo como evidência em Search e AI Search.

O índice é auditável e reprodutível. Não é padrão oficial de GEO/AEO nem nota de Google, Bing, OpenAI ou outro mantenedor.

## 2. Método de scoring

O SARI-001 usa:

```text
SCORE-GEO-004
```

As dez dimensões e o Overall são calculados deterministicamente a partir de regras e evidências persistidas. Uma auditoria individual pode produzir Overall consolidado quando sua própria medição alcança os gates de Coverage e Confidence.

## 3. Dimensões

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

Desktop e Mobile permanecem separados.

## 4. Score das dimensões

```text
Dimension Score = sum(weight x result_factor) / sum(weight evaluated) x 100
```

Fatores padrão:

```text
PASS    = 1.00
WARNING = 0.50
FAIL    = 0.00
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos automaticamente em `FAIL`.

## 5. Overall

Contrato:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Fórmula:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero.

Uma dimensão aplicável sem valor ou em `NOT_CONSOLIDATED` bloqueia a publicação de Overall consolidado.

O Overall é um índice determinístico de readiness. Não é probabilidade de ranking, resposta ou citação.

## 6. Coverage, Confidence e Consolidation

Coverage mede completude do universo aplicável avaliado e não qualidade do site.

Confidence das dimensões é baseada em cobertura, evidência e erros.

No Overall:

```text
Coverage = média da Coverage das dimensões aplicáveis
Confidence = menor Confidence das dimensões aplicáveis
```

O Overall recebe `CONSOLIDATED` quando:

```text
todas as dimensões aplicáveis possuem valor
nenhuma dimensão aplicável = NOT_CONSOLIDATED
Coverage média >= 80%
Confidence mínima = HIGH ou MEDIUM
```

Resultado calculável abaixo desse gate pode ser `PARTIAL` quando existe evidência suficiente para uma leitura limitada. Ausência de evidência nunca vira zero.

## 7. Validação empírica

Validação empírica é uma atividade separada do scoring operacional.

Datasets externos podem ser usados para estudar associação entre readiness e outcomes observados, mas não são input automático do SCORE-GEO-004 e não alteram silenciosamente a fórmula publicada.

Qualquer mudança de fórmula ou gates decorrente de evidência futura exige alteração explícita e versionada do contrato metodológico.

## 8. Groundability

Groundability é exposta como conjunto de sinais, não como novo subscore:

- `ANSWERABILITY`;
- `CITATION_READINESS`;
- `EVIDENCE_TRUST`.

Não é criada uma segunda agregação sem contrato próprio.

## 9. YMYL e E-E-A-T

YMYL e E-E-A-T são contexto de rigor da análise e remediação, não scores oficiais.

O RASAi não apresenta "E-E-A-T Score" nem "YMYL Score" como métricas oficiais do Google.

## 10. Métricas externas

Não entram no Overall:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility/WCAG;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- métricas de tráfego/conversão;
- métricas source-reported de mecanismos externos.

Elas permanecem em seus domínios próprios. Indisponibilidade de PageSpeed/Lighthouse não reduz o SARI-001.

## 11. Readiness versus visibilidade observada

```text
Readiness
= sinais medidos no site

Observed Generative Visibility
= resultado efetivamente observado em engine/query/período
```

Outcomes observados podem apoiar pesquisas e validações separadas, mas não são input do Overall do SARI-001.

## 12. Relatórios

```text
index.html             -> síntese executiva
readiness.html         -> SARI-001
scoring.html           -> versão vigente, fórmula e gates do scoring
ai-visibility.html     -> outcomes observados
web-performance.html   -> CWV + Lighthouse
accessibility.html     -> acessibilidade automatizada
apdex.html             -> Synthetic Navigation Apdex
apdex-experience.html  -> Synthetic User Experience Apdex, quando materializado
```

`scoring.html` é um path estável. O identificador metodológico permanece versionado em `scoring_version` e no conteúdo da página. O alias `score-geo-004.html` existe somente para compatibilidade com links antigos e não deve ser adotado como contrato novo.

O dashboard não cria agregação transversal entre metodologias.

## 13. Rastreabilidade e comparabilidade

Resultados preservam `scoring_version`, evidências, RuleExecutions e ScoreContributions necessários para reconstrução e comparação válida.

Mudança incompatível de fórmula, dimensões ou gates exige identificador metodológico distinto. Comparações entre versões diferentes devem declarar a diferença metodológica em vez de normalizá-la silenciosamente.

## 14. Estado de validação

```text
Fundamentação conceitual: evidence-based
Dimensões determinísticas: sim
Overall operacional determinístico: sim
Reprodutível por auditoria: sim
Validação empírica externa: separada do score
Homologação externa do índice composto: não
Garantia causal de citação: não
```
