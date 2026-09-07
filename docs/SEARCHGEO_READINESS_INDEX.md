# SearchGEO Readiness Index — SGRI-001

## 1. Objetivo

O **SearchGEO Readiness Index (`SGRI-001`)** é a identidade pública da metodologia proprietária do SearchGEO para consolidar sinais de prontidão relacionados a descoberta, interpretação, recuperação, resposta e uso do conteúdo como evidência em Search e AI Search.

O índice é versionado, auditável e reprodutível. Ele não é padrão oficial de GEO/AEO nem nota de Google, Bing, OpenAI ou outro mantenedor.

## 2. Motor vigente

Novas auditorias usam:

```text
SCORE-GEO-003
```

`SCORE-GEO-002` permanece histórico e não é recalculado.

A transição é uma quebra metodológica real: o cálculo das dimensões permanece determinístico, mas o Overall deixa de ser média simples e passa a exigir modelo calibrado.

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

## 5. Overall no SCORE-GEO-003

Com dimensões aplicáveis suficientemente consolidadas e model artifact `VALIDATED`:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

As features são as dez dimensões normalizadas.

Sem model artifact validado, o Overall fica `NOT_CONSOLIDATED`; nenhum número é fabricado e não existe fallback silencioso para o `002`.

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

O split é por domínio para reduzir leakage.

Detalhes: `SCORE_GEO_003.md` e `SCORING_VALIDATION.md`.

## 7. Coverage, Confidence e Consolidation

Coverage mede completude do universo aplicável avaliado; não mede qualidade do site.

Confidence das dimensões continua baseada em cobertura/evidência/erros. No Overall, a Confidence é limitada também pela `calibration_confidence` do artifact.

Consolidation informa se existe base suficiente para publicar conclusão agregada.

## 8. Groundability

Groundability continua exposta como conjunto de sinais, não como novo subscore:

- `ANSWERABILITY`;
- `CITATION_READINESS`;
- `EVIDENCE_TRUST`.

Não é criada uma segunda agregação sem contrato próprio.

## 9. YMYL e E-E-A-T

YMYL/E-E-A-T permanecem contexto de rigor da análise e remediação, não score oficial.

O SearchGEO não apresenta “E-E-A-T Score” nem “YMYL Score” como métricas oficiais do Google.

## 10. Métricas externas

Não entram automaticamente no Overall `003`:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility/WCAG;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- métricas Bing source-reported.

Elas permanecem em seus domínios próprios, salvo se futura calibração demonstrar relação válida e o contrato for versionado.

## 11. Readiness versus visibilidade observada

```text
Readiness
= sinais medidos no site

Observed Generative Visibility
= resultado efetivamente observado em engine/query/período
```

O `003` usa outcomes observados para calibrar o Overall, mas isso não torna cada auditoria uma garantia de citação futura.

## 12. Relatórios

```text
index.html             -> síntese executiva
searchgeo.html         -> SGRI-001
score-geo-003.html     -> modelo/dataset/gates do SCORE-GEO-003
ai-visibility.html     -> outcomes observados
web-performance.html   -> CWV + Lighthouse
accessibility.html     -> acessibilidade automatizada
apdex.html             -> Synthetic Navigation Apdex
apdex-experience.html  -> Synthetic User Experience Apdex
```

O dashboard não cria agregação transversal entre metodologias.

## 13. Histórico e comparabilidade

Auditorias `SCORE-GEO-002` e `SCORE-GEO-003` não devem ser tratadas como a mesma série sem segmentação por versão.

Alterações de model/dataset dentro do `003` permanecem rastreáveis por `model_version`, `dataset_version` e SHA-256 do artifact.

Alteração incompatível de fórmula/features/gates exige nova versão de scoring.

## 14. Estado de validação

```text
Fundamentação conceitual: evidence-based
Dimensões determinísticas: sim
Overall empiricamente calibrável: sim
Holdout por domínio: sim
Artifact versionado/reprodutível: sim
Homologação externa do índice composto: não
Garantia causal de citação: não
```
