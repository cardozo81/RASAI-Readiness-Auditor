# Search & AI Readiness Index - SARI-001

## 1. Objetivo

O **Search & AI Readiness Index (`SARI-001`)** é a identidade pública da metodologia proprietária do RASAi para consolidar sinais de prontidão relacionados a descoberta, interpretação, recuperação, resposta e uso do conteúdo como evidência em Search e AI Search.

O índice é auditável e reprodutível. Ele não é padrão oficial de GEO/AEO nem nota de Google, Bing, OpenAI ou outro mantenedor.

## 2. Método de scoring vigente

Novas auditorias usam:

```text
SCORE-GEO-004
```

As dez dimensões e o Overall são calculados deterministicamente a partir de regras e evidências persistidas. Uma auditoria individual pode produzir Overall consolidado quando a própria medição alcança os gates de Coverage e Confidence.

`SCORE-GEO-003` permanece preservado como método histórico calibrado empiricamente. Seu model artifact não é requisito para o runtime `004`.

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

Contrato vigente:

```text
EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1
```

Com dimensões aplicáveis materializadas:

```text
Overall = soma dos scores das dimensões aplicáveis / quantidade de dimensões aplicáveis
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero.

Uma dimensão aplicável sem valor ou `NOT_CONSOLIDATED` bloqueia a publicação de Overall consolidado.

O Overall do `004` é um índice de readiness determinístico. Não é probabilidade de ranking ou citação.

## 6. Coverage, Confidence e Consolidation

Coverage mede completude do universo aplicável avaliado; não mede qualidade do site.

Confidence das dimensões é baseada em cobertura, evidência e erros.

No Overall `004`:

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

Consolidation informa se existe base suficiente para publicar a conclusão agregada. Resultado calculável abaixo desse gate pode ser `PARTIAL`; ausência de evidência nunca vira zero.

## 7. Calibração empírica

A calibração multi-domínio introduzida em `SCORE-GEO-003` permanece disponível como processo separado para pesquisa e validação empírica.

Ela pode avaliar associação entre dimensões de readiness e outcomes observados de citação, mas:

- não é executada a cada auditoria;
- não é requisito do `SCORE-GEO-004`;
- não altera silenciosamente o score `004`;
- não transforma readiness em garantia de citação futura.

Detalhes históricos: `SCORE_GEO_003.md`.

## 8. Groundability

Groundability é exposta como conjunto de sinais, não como novo subscore:

- `ANSWERABILITY`;
- `CITATION_READINESS`;
- `EVIDENCE_TRUST`.

Não é criada uma segunda agregação sem contrato próprio.

## 9. YMYL e E-E-A-T

YMYL/E-E-A-T são contexto de rigor da análise e remediação, não scores oficiais.

O RASAi não apresenta "E-E-A-T Score" nem "YMYL Score" como métricas oficiais do Google.

## 10. Métricas externas

Não entram no Overall:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility/WCAG;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- métricas de tráfego/conversão;
- métricas Bing source-reported.

Elas permanecem em seus domínios próprios. Indisponibilidade PageSpeed/Lighthouse não reduz o SARI-001.

## 11. Readiness versus visibilidade observada

```text
Readiness
= sinais medidos no site

Observed Generative Visibility
= resultado efetivamente observado em engine/query/período
```

Outcomes observados podem ser usados em validação empírica futura, mas não são input do Overall `004`.

## 12. Relatórios

```text
index.html             -> síntese executiva
readiness.html         -> SARI-001
score-geo-004.html     -> fórmula/gates do SCORE-GEO-004
ai-visibility.html     -> outcomes observados
web-performance.html   -> CWV + Lighthouse
accessibility.html     -> acessibilidade automatizada
apdex.html             -> Synthetic Navigation Apdex
apdex-experience.html  -> Synthetic User Experience Apdex, quando materializado
```

O dashboard não cria agregação transversal entre metodologias.

## 13. Rastreabilidade e comparabilidade

Resultados preservam `scoring_version` e demais metadados necessários para reconstrução e comparação válida.

Mudança incompatível de fórmula, features ou gates exige identificador metodológico distinto. Por isso a mudança do contrato calibrado `003` para o contrato determinístico atual foi versionada como `004`.

## 14. Estado de validação

```text
Fundamentação conceitual: evidence-based
Dimensões determinísticas: sim
Overall operacional determinístico: sim
Reprodutível por auditoria: sim
Calibração empírica opcional/histórica: sim
Homologação externa do índice composto: não
Garantia causal de citação: não
```
