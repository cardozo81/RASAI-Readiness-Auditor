# SCORE-GEO-003

`SCORE-GEO-003` é o método padrão de scoring do SearchGEO.

## O que muda

As dez dimensões continuam determinísticas, evidence-backed e calculadas com a mesma semântica consolidada no `SCORE-GEO-002`:

```text
Dimension Score = Σ(weight × result_factor) / Σ(weight evaluated) × 100
```

`PASS=1`, `WARNING=0,5` por padrão e `FAIL=0`. `UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos em `FAIL`.

O `OVERALL_READINESS` deixa de ser média simples das dimensões e passa a exigir um modelo calibrado:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

As features são as dez dimensões normalizadas em `0..1`.

## Regra de segurança

Sem artifact de calibração com `status=VALIDATED`:

```text
scoring_version = SCORE-GEO-003
Overall.value = null
Overall.confidence = UNAVAILABLE
Overall.consolidation_status = NOT_CONSOLIDATED
limitation = CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003
```

O programa não inventa coeficientes e não faz fallback silencioso para o Overall do `SCORE-GEO-002`.

As dimensões continuam disponíveis para diagnóstico.

## Outcome inicial

A calibração usa somente outcome binário observado:

```text
CITED = 1
NOT_CITED = 0
```

Fonte inicial: `CONTROLLED_QUERY_RUNS` já persistido pelo domínio Observed Generative Visibility.

## Promotion gate mínimo

Um artifact só recebe `VALIDATED` quando atende simultaneamente:

| Requisito | Mínimo |
|---|---:|
| Domínios | 40 |
| Domínios no holdout | 12 |
| Engines | 2 |
| Queries por domínio | 10 |
| Repetições por query/engine | 3 |
| Observações válidas | 2400 |
| AUC no holdout | 0,60 |
| Brier Score | menor que baseline por prevalência de treino |

O split é determinístico por **domínio**, aproximadamente 70/30. Queries do mesmo domínio não atravessam treino e validação.

Os números acima são gates internos versionados do SearchGEO; não são thresholds oficiais de GEO definidos por plataforma externa.

## Modelo

Versão inicial:

```text
format_version = SG003-MODEL-001
model_version = GEO-LR-001
model = L2_REGULARIZED_LOGISTIC_REGRESSION
```

A implementação usa regressão logística regularizada e determinística, sem modelo black-box.

O artifact persiste:

- dataset version;
- data de treinamento;
- engines;
- intercept;
- coeficientes;
- médias de imputação;
- métricas de treino/validação;
- protocolo/gates;
- SHA-256 do artifact.

## NOT_APPLICABLE

Dimensão legitimamente `NOT_APPLICABLE` não recebe zero. Para inferência do modelo, usa-se a média de imputação daquela feature persistida no próprio artifact.

Dimensão aplicável `NOT_CONSOLIDATED` continua bloqueando o Overall.

## Confidence

A Confidence do Overall é o menor nível entre:

1. Confidence das dimensões aplicáveis;
2. Confidence do artifact de calibração.

O artifact validado recebe `MEDIUM` por padrão; `HIGH` exige amostra e desempenho superiores definidos no protocolo. Isso qualifica robustez da medição, não garante citação futura.

## Parametrização

O usuário pode alterar coleta e universo de calibração:

- diretório de AUDs;
- `dataset_version`;
- engines e queries que compõem os query-runs;
- volume/repetições de coleta;
- caminho do artifact via `SEARCHGEO_SCORE_GEO_003_MODEL`.

O usuário **não** altera por auditoria:

- fórmula;
- features;
- coeficientes de um artifact validado;
- promotion gate;
- split por domínio;
- regularização;
- regras de Coverage/Confidence/Consolidation.

Alteração incompatível exige novo contrato/versionamento.

## Comandos

Calibrar:

```powershell
searchgeo scoring calibrate --dataset-version GEO-CAL-001
```

Com caminho explícito:

```powershell
searchgeo scoring calibrate `
  --audits-root audits `
  --dataset-version GEO-CAL-001 `
  --output .searchgeo\scoring\score-geo-003-model.json
```

Inspecionar:

```powershell
searchgeo scoring inspect
```

Por padrão, auditorias procuram:

```text
.searchgeo/scoring/score-geo-003-model.json
```

ou o caminho definido em:

```text
SEARCHGEO_SCORE_GEO_003_MODEL
```

## Compatibilidade histórica

`SCORE-GEO-002` permanece como versão histórica. Auditorias antigas não são recalculadas.

Relatórios consolidados devem segmentar séries por `scoring_version`; uma mudança `002 → 003` é quebra metodológica e não deve ser apresentada como evolução contínua sem ressalva.

## Relatório HTML

Cada auditoria gera `report/score-geo-003.html` com:

- versão do método;
- estado/modelo/dataset da calibração;
- AUC/Brier quando disponíveis;
- Overall por device;
- promotion gate;
- regras de parametrização e compatibilidade histórica.

`searchgeo.html` continua sendo a página canônica do SGRI e é reconciliada para explicar que o Overall do `003` é calibrado.

## Limite de interpretação

O modelo mede **associação observacional** entre sinais SearchGEO e presença observada de citação no dataset utilizado. Ele não prova causalidade e não garante ranking, tráfego, conversão ou citação futura em qualquer engine.
