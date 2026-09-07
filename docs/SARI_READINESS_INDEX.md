# Search & AI Readiness Index — SARI-001

## 1. Objetivo

O **Search & AI Readiness Index (`SARI-001`)** é a identidade pública da metodologia proprietária do RASAi para consolidar sinais de prontidão relacionados a descoberta, interpretação, recuperação, resposta e uso do conteúdo como evidência em Search e AI Search.

O índice é auditável e reprodutível. Ele não é padrão oficial de GEO/AEO nem nota de Google, Bing, OpenAI ou outro mantenedor.

## 2. Método de scoring

As auditorias usam:

```text
SCORE-GEO-003
```

As dez dimensões são calculadas deterministicamente a partir de regras e evidências persistidas. O Overall exige model artifact calibrado com estado `VALIDATED`.

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
Dimension Score = Σ(weight × result_factor) / Σ(weight evaluated) × 100
```

Fatores padrão:

```text
PASS    = 1.00
WARNING = 0.50
FAIL    = 0.00
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos automaticamente em `FAIL`.

## 5. Overall

Com dimensões aplicáveis suficientemente consolidadas e model artifact `VALIDATED`:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

As features são as dez dimensões normalizadas. Sem model artifact validado, o Overall fica `NOT_CONSOLIDATED`; nenhum número substituto é fabricado.

## 6. Calibração

Outcome inicial:

```text
CITED / NOT_CITED
```

Fonte: query-runs controlados do domínio Observed Generative Visibility.

Promotion gate mínimo:

- 40 domínios;
- 12 domínios no holdout;
- 2 engines;
- 10 queries por domínio;
- 3 repetições por query/engine;
- 2400 observações válidas;
- AUC holdout >= 0,60;
- Brier menor que baseline por prevalência de treino.

O split é por domínio para reduzir leakage. Detalhes: `SCORE_GEO_003.md` e `SCORING_VALIDATION.md`.

## 7. Coverage, Confidence e Consolidation

Coverage mede completude do universo aplicável avaliado; não mede qualidade do site.

Confidence das dimensões é baseada em cobertura, evidência e erros. No Overall, a Confidence também é limitada pela `calibration_confidence` do artifact.

Consolidation informa se existe base suficiente para publicar uma conclusão agregada.

## 8. Groundability

Groundability é exposta como conjunto de sinais, não como novo subscore:

- `ANSWERABILITY`;
- `CITATION_READINESS`;
- `EVIDENCE_TRUST`.

Não é criada uma segunda agregação sem contrato próprio.

## 9. YMYL e E-E-A-T

YMYL/E-E-A-T são contexto de rigor da análise e remediação, não scores oficiais.

O RASAi não apresenta “E-E-A-T Score” nem “YMYL Score” como métricas oficiais do Google.

## 10. Métricas externas

Não entram automaticamente no Overall:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility/WCAG;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- métricas Bing source-reported.

Elas permanecem em seus domínios próprios, salvo se uma calibração formal demonstrar relação válida e o contrato metodológico for atualizado.

## 11. Readiness versus visibilidade observada

```text
Readiness
= sinais medidos no site

Observed Generative Visibility
= resultado efetivamente observado em engine/query/período
```

Outcomes observados podem alimentar a calibração do Overall, mas isso não torna cada auditoria uma garantia de citação futura.

## 12. Relatórios

```text
index.html             -> síntese executiva
readiness.html         -> SARI-001
score-geo-003.html     -> modelo/dataset/gates do SCORE-GEO-003
ai-visibility.html     -> outcomes observados
web-performance.html   -> CWV + Lighthouse
accessibility.html     -> acessibilidade automatizada
apdex.html             -> Synthetic Navigation Apdex
apdex-experience.html  -> Synthetic User Experience Apdex
```

O dashboard não cria agregação transversal entre metodologias.

## 13. Rastreabilidade e comparabilidade

Resultados preservam `scoring_version`, `model_version`, `dataset_version`, SHA-256 dos artifacts e demais metadados necessários para reconstrução e comparação válida.

Mudança incompatível de fórmula, features ou gates exige um identificador metodológico distinto.

## 14. Estado de validação

```text
Fundamentação conceitual: evidence-based
Dimensões determinísticas: sim
Overall empiricamente calibrável: sim
Holdout por domínio: sim
Artifact reprodutível: sim
Homologação externa do índice composto: não
Garantia causal de citação: não
```
