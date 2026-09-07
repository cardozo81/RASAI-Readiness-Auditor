# SCORING_GUIDE.md

Guia operacional do **Search & AI Readiness Index `SARI-001`**.

## Versão vigente

Novas auditorias usam por padrão:

```text
scoring_version = SCORE-GEO-003
```

`SCORE-GEO-002` permanece histórico e não é recalculado.

A mudança `002 → 003` é metodológica: as dimensões continuam determinísticas, mas o `OVERALL_READINESS` deixa de ser média simples e passa a depender de modelo empiricamente calibrado.

Consulte `SCORE_GEO_003.md` para o contrato completo.

## Dimensões

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

Desktop e Mobile permanecem separados. Apenas dispositivos realmente auditados devem ser apresentados como resultado válido.

## RuleResult

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

Somente `PASS`, `WARNING` e `FAIL` entram no denominador do score da dimensão.

`UNKNOWN` e `ERROR` reduzem Coverage/capacidade de conclusão; não são `FAIL`.

`NOT_APPLICABLE` sai do universo aplicável quando legítimo.

## Fórmula das dimensões

```text
PASS    = 1,00
WARNING = 0,50 por padrão
FAIL    = 0,00

Dimension Score = Σ(weight × result_factor) / Σ(weight evaluated) × 100
```

A semântica de grupos correlacionados (`MAX_IMPACT`), pré-requisitos, evidência e aplicabilidade permanece compatível com a baseline `002`.

## Coverage

```text
evaluated applicable weight / total applicable weight
```

Coverage mede completude da análise, não qualidade do site.

## Confidence da dimensão

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

Esses thresholds continuam sendo governança interna versionada do RASAI.

## Consolidation da dimensão

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          demais estados avaliáveis com Coverage >= 50%
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Pré-requisito bloqueado não pode ser promovido a `NOT_APPLICABLE` benigno.

## Overall no SCORE-GEO-003

Com todas as dimensões aplicáveis suficientemente consolidadas e um artifact `VALIDATED`:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

As dez dimensões normalizadas em `0..1` são as features.

Os coeficientes não são editáveis por auditoria; pertencem ao artifact de calibração versionado.

### Sem modelo validado

```text
Overall.value = null
Overall.confidence = UNAVAILABLE
Overall.consolidation_status = NOT_CONSOLIDATED
limitation = CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003
```

O RASAI não inventa coeficientes e não faz fallback silencioso para o Overall `002`.

As dimensões continuam sendo calculadas e persistidas como `SCORE-GEO-003`.

## Calibração mínima

O outcome inicial é binário:

```text
CITED / NOT_CITED
```

O dataset usa query-runs controlados já persistidos em Observed Generative Visibility.

Promotion gate:

| Requisito | Mínimo |
|---|---:|
| Domínios | 40 |
| Domínios de validação | 12 |
| Engines | 2 |
| Queries/domínio | 10 |
| Repetições/query/engine | 3 |
| Dias distintos de observação por domínio | 3 |
| Observações válidas | 2400 |
| AUC holdout | 0,60 |
| Brier | menor que baseline por prevalência |

O split é feito por domínio, não por query, para reduzir leakage. A cobertura temporal mínima impede que um artifact seja promovido quando as observações de um domínio estão concentradas em menos de três datas distintas.

## Confidence do Overall

A Confidence final é limitada por:

- menor Confidence das dimensões aplicáveis;
- `calibration_confidence` do artifact.

Um modelo validado recebe pelo menos `MEDIUM`; `HIGH` exige amostra e desempenho superiores definidos no protocolo.

Confidence continua significando força da medição, não garantia de citação futura.

## Structured Data / NOT_APPLICABLE

JSON-LD não é requisito universal para cálculo.

Quando `STRUCTURED_DATA` é legitimamente `NOT_APPLICABLE`, a dimensão não recebe zero. Na inferência do `003`, usa-se a média de imputação persistida para essa feature no artifact.

Uma dimensão aplicável `NOT_CONSOLIDATED` bloqueia o Overall.

## Sem IA

IA continua opcional para a auditoria base. Ausência de IA pode reduzir Coverage/Confidence das dimensões sem transformar regras semânticas em `FAIL`.

A calibração do `003` é processo separado e consome outcomes observados persistidos; não cria chamadas externas durante o cálculo normal do score.

## Parametrização

Configuração de coleta é permitida. Matemática oficial não é variável por auditoria.

Configurável:

- URLs/domínios auditados;
- engines/query-runs observados;
- volume, repetições e distribuição temporal das observações;
- diretório de AUDs para calibração;
- `dataset_version`;
- caminho do model artifact.

Fixo/versionado:

- features;
- fórmula;
- promoção `VALIDATED`;
- split por domínio;
- regularização;
- coeficientes do artifact;
- thresholds de Coverage/Confidence/Consolidation.

## Comandos

```powershell
rasai scoring calibrate --dataset-version GEO-CAL-001
rasai scoring inspect
```

Artifact padrão:

```text
.searchgeo/scoring/score-geo-003-model.json
```

Override de localização:

```text
SEARCHGEO_SCORE_GEO_003_MODEL
```

## Reprodutibilidade

`BR-GEO-054` deve permitir reconstrução a partir de:

- RuleExecutions e versões;
- ScoreContributions;
- `SCORE-GEO-003`;
- model version;
- dataset version;
- SHA-256 do artifact de calibração.

Nenhuma reexecução de website ou IA deve ser necessária para reproduzir o cálculo.

## Relatórios e histórico

`readiness.html` é a página canônica do SARI.

`score-geo-003.html` expõe o contrato e o estado de calibração da auditoria, inclusive o gate temporal vigente.

Relatórios consolidados devem segmentar séries por `scoring_version`. `SCORE-GEO-002` e `SCORE-GEO-003` não devem ser tratados como a mesma série sem ressalva explícita.

## Limite de validade

O `003` é uma métrica proprietária calibrada contra outcomes observados. Não é certificação oficial de Google, OpenAI, Microsoft, Anthropic ou outro mantenedor.

O resultado mede associação observacional no dataset utilizado; não prova causalidade nem garante ranking, tráfego, conversão ou citação futura.
