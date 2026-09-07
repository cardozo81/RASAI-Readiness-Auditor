# SCORING_VALIDATION.md

## Objetivo

Registrar como o `SCORE-GEO-003` é validado e separar claramente:

- evidência externa oficial;
- métricas externas definidas;
- heurísticas RASAI;
- calibração empírica do Overall.

## 1. Limite normativo

Não existe um score GEO/AEO 0–100 universal homologado por Google, OpenAI, Microsoft, Anthropic, NIST, W3C ou outro mantenedor equivalente.

`SCORE-GEO-003` continua sendo método proprietário do RASAI. A calibração melhora respaldo quantitativo, mas não converte o índice em padrão oficial.

## 2. O que é calibrado

As dez dimensões continuam determinísticas e evidence-backed.

A mudança do `003` está no `OVERALL_READINESS`:

```text
Overall = 100 × sigmoid(β0 + Σ βi × feature_i)
```

As features são as dimensões normalizadas.

Outcome inicial:

```text
CITED = 1
NOT_CITED = 0
```

Fonte inicial do outcome: `CONTROLLED_QUERY_RUNS` persistidos pelo domínio Observed Generative Visibility.

## 3. Promotion gate

O model artifact só recebe `VALIDATED` quando atende simultaneamente:

| Critério | Mínimo |
|---|---:|
| Domínios | 40 |
| Domínios no holdout | 12 |
| Engines | 2 |
| Queries/domínio | 10 |
| Repetições/query/engine | 3 |
| Dias distintos de observação por domínio | 3 |
| Observações válidas | 2400 |
| AUC holdout | 0,60 |
| Brier | menor que baseline por prevalência de treino |

O split é feito por domínio, aproximadamente 70/30, para evitar leakage entre queries do mesmo site.

A cobertura temporal também é obrigatória: cada domínio precisa ter query-runs elegíveis em pelo menos três datas civis distintas derivadas de `observed_at`. Isso reduz o risco de promover um modelo com falsa estabilidade baseada apenas em repetições concentradas em um único dia.

Artifact abaixo de qualquer gate permanece `EXPERIMENTAL` e não consolida o Overall.

## 4. Métricas de validação

### AUC

Mede capacidade discriminativa no holdout. O gate mínimo interno é `0,60`.

### Brier Score

Mede erro quadrático das probabilidades. O modelo precisa superar um baseline que prevê a prevalência observada no treino.

AUC/Brier são métricas estatísticas conhecidas; os gates usados para promover um model artifact são decisões internas versionadas do RASAI.

## 5. Hierarquia de evidência

### Requisito oficial

Exemplos: regras técnicas/indexação do Google, RFC 9110, RFC 9309.

Sustenta o fenômeno específico; não homologa o Overall.

### Métrica externa definida

Exemplos: Core Web Vitals, Lighthouse, métricas NIST/TREC.

Mantém metodologia própria e não entra automaticamente no `SCORE-GEO-003`.

### Heurística RASAI

Exemplos: fatores de RuleResult, thresholds de Coverage/Confidence/Consolidation e classificação visual.

Continuam explicitamente internos.

### Modelo RASAI calibrado

Coeficientes do Overall `003` são derivados de dataset observacional versionado e só são usados quando o artifact passa o promotion gate.

## 6. Observed Generative Visibility

Observed Generative Visibility permanece uma camada observacional separada do scoring operacional.

Ela fornece, quando importado:

- query;
- engine/surface;
- timestamp;
- `CITED/NOT_CITED`;
- cited URLs;
- rank quando sua semântica é explícita;
- Citation Presence Rate + Wilson 95%.

O calibrador reutiliza somente query-runs controlados elegíveis. Além de volume, engines, queries e repetições, o protocolo de calibração verifica distribuição temporal mínima dos timestamps. Não faz scraping de portal e não presume endpoint não documentado.

## 7. Não entram automaticamente no Overall

Sem evidência empírica específica, o `003` não injeta diretamente no Overall:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility/WCAG;
- Synthetic Apdex;
- E-E-A-T/YMYL;
- contagem de Structured Data;
- métricas Bing source-reported não equivalentes ao outcome binário.

Esses domínios continuam independentes ou influenciam apenas as regras/dimensões já documentadas.

## 8. Reprodutibilidade

O model artifact registra:

- `format_version`;
- `model_version`;
- `dataset_version`;
- data de treinamento;
- engines;
- intercept;
- coeficientes;
- médias de imputação;
- métricas de treino/validação;
- protocolo/gates, incluindo `min_distinct_days`;
- SHA-256.

`BR-GEO-054` deve permitir recálculo sem nova chamada a website/IA.

## 9. Histórico

`SCORE-GEO-002` não é removido dos AUDs históricos.

Relatórios consolidados devem segmentar `002` e `003` como versões metodologicamente diferentes.

## 10. Interpretação correta

O Overall `003` é uma saída calibrada contra outcomes observados no dataset de referência, mas:

- não prova causalidade;
- não garante citação futura;
- não garante ranking, tráfego ou conversão;
- pode degradar quando engines/modelos e comportamento de busca mudarem.

Recalibração deve produzir novo `dataset_version`/`model_version`; alteração incompatível do contrato exige nova versão de scoring.

Detalhes: `SCORE_GEO_003.md`.
