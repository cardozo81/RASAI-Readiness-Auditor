# SCORING_GUIDE.md

Guia operacional do **Search & AI Readiness Index `SARI-001`**.

## Método vigente

```text
scoring_version = SCORE-GEO-004
overall_aggregation = HIERARCHICAL_WEIGHTED_READINESS_V1
```

O método é determinístico sobre RuleExecutions/evidências persistidas e não representa probabilidade de ranking ou citação.

O produto ainda está em pré-produção. A implementação experimental anterior do mesmo `SCORE-GEO-004` não é contrato ativo; auditorias antigas com o antigo Overall devem ser regeneradas se precisarem ser comparadas.

Contrato completo: [`SCORE_GEO_004.md`](SCORE_GEO_004.md).

## Dimensões e pesos

| Dimensão | Peso |
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

Desktop e Mobile permanecem separados.

`DISCOVERY_ACCESS` é a denominação vigente da dimensão antes conhecida internamente como `TECHNICAL_ACCESSIBILITY`; o objetivo é evitar confusão com Accessibility/WCAG.

## Como o peso é aplicado

A hierarquia é:

```text
RuleExecution
→ página/escopo global
→ scoring_group
→ dimensão
→ Overall ponderado
```

O peso do grupo não é multiplicado pelo número de páginas.

Exemplo conceitual:

```text
ROBOTS = 15% de DISCOVERY_ACCESS
```

continua representando essa participação relativa em uma auditoria de 5, 50 ou 500 páginas. Quando o grupo existe em várias páginas, seu peso é dividido pelos escopos aplicáveis.

## RuleResult

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

Qualidade:

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00
```

`UNKNOWN`/`ERROR` reduzem Coverage; não viram FAIL.

`NOT_APPLICABLE` sai do universo aplicável quando legítimo.

## Dimension Score

```text
Scope Weight = Group Weight / escopos aplicáveis do grupo

Dimension Score =
  sum(Scope Weight × Result Factor avaliados)
  / sum(Scope Weight avaliados)
  × 100
```

## Coverage

```text
Dimension Coverage = evaluated applicable weight / total applicable weight

Overall Coverage =
  sum(Dimension Weight × Dimension Coverage)
  / sum(Dimension Weight aplicável)
```

Coverage mede completude da análise, não qualidade do site.

## Overall

```text
Overall =
  sum(Dimension Weight × Dimension Score medido)
  / sum(Dimension Weight medido e aplicável)
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador sem receber nota artificial.

Uma dimensão não crítica sem medição suficiente pode reduzir Coverage/Confidence sem apagar automaticamente a nota das dimensões efetivamente medidas. Uma dimensão crítica sem medição suficiente bloqueia Consolidation.

## Confidence

Dimensão:

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         medição abaixo desses critérios
UNAVAILABLE Coverage <= 0
```

Overall:

- `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY` são dimensões críticas;
- qualquer uma delas LOW/UNAVAILABLE mantém Overall Confidence LOW;
- as demais dimensões influenciam Confidence proporcionalmente aos próprios pesos.

Confidence é força da medição, não chance de outcome externo.

## Consolidation

Dimensão:

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   fora do universo aplicável
```

Overall `CONSOLIDATED` exige:

- Overall Coverage >= 80%;
- Overall Confidence HIGH/MEDIUM;
- nenhuma dimensão crítica aplicável sem medição suficiente.

Uma conclusão ruim pode ser `CONSOLIDATED`. Isso significa que o website foi medido com força suficiente e apresentou resultado ruim; Consolidation não é selo de qualidade.

## Critical Readiness Gates

Além do score existem três gates:

| Gate | Principais grupos |
|---|---|
| Discovery | `PAGE_ACCESS`, `ROBOTS`, `REDIRECT` |
| Indexability | `INDEX_DIRECTIVES`, `CANONICAL`, `SOFT_ERROR` |
| Extraction | `RENDER_ACCESS`, `JS_CONTENT`, `CONTENT_EXTRACTION` |

Estados:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

Readiness geral:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

Os gates **não truncam o SARI**. O relatório pode mostrar, por exemplo:

```text
SARI 82
Consolidation CONSOLIDATED
Readiness BLOCKED
Indexability Gate BLOCKED
```

## Precedência IA × determinístico

No mesmo `scoring_group` e escopo:

```text
DETERMINISTIC_PRIMARY > AI_CORROBORATIVE
```

Se existe fato determinístico conclusivo, uma avaliação IA corroborativa não o substitui.

BR-GEO-055/056 compartilham os grupos de sitemap/robots e nunca criam bônus duplicado. IA não escolhe pesos, fatores ou thresholds.

## Content Value

A dimensão `CONTENT_VALUE` usa:

```text
BR-GEO-057  utilidade/especificidade
BR-GEO-058  diferenciação/experiência/dado próprio explícito
BR-GEO-059  profundidade/contexto
```

Baseline:

```text
CONTENT-VALUE-BASELINE-001
```

A baseline é local e evidence-bound. Ela é deliberadamente conservadora: diferenciação não demonstrada fica `UNKNOWN`, não `FAIL`.

## Structured Data

Structured Data representa 5% do SARI quando aplicável e não é requisito universal.

- N/A legítimo sai do denominador;
- ausência não deve ser tratada como blocker universal;
- markup existente inválido/contraditório pode ser desfavorável;
- propriedades ou “GEO schema” inexistentes não devem ser inventados.

## Lighthouse / Core Web Vitals

Os category scores não entram diretamente no SARI:

```text
Lighthouse Performance
Lighthouse Accessibility
Lighthouse Best Practices
Lighthouse SEO
Core Web Vitals / CrUX
```

Um audit individual do Lighthouse só pode ser `CORROBORATIVE_EVIDENCE` quando existir mapeamento explícito para a mesma condição de uma BR-GEO. A nota da categoria nunca é usada como atalho.

Indisponibilidade de PageSpeed/Lighthouse não reduz o SARI por si só.

## Outcomes externos

Ficam fora do Overall:

- SERP/posição;
- concorrentes;
- Search Console;
- impressões/cliques/CTR;
- Observed Generative Visibility;
- tráfego e conversão.

Esses resultados servem à Observability e à futura validação empírica dos pesos.

## Parametrização

Configurável pelo operador:

- URLs/domínios;
- dispositivos;
- provider/modelo de IA;
- contexto editorial/YMYL quando aplicável;
- Web Performance;
- Synthetic Apdex;
- limites de coleta/execução.

Fixo no `SCORE-GEO-004`:

- dimensões e pesos;
- scoring groups e pesos;
- fatores RuleResult;
- manifesto regra → dimensão → grupo;
- thresholds de Coverage/Confidence/Consolidation;
- Critical Gates;
- precedência de evidência.

O usuário não pode alterar pesos para fabricar uma nota melhor.

## CLI

```powershell
rasai scoring inspect
```

O comando deve refletir o contrato vigente e não executar rede.

## Reprodutibilidade

`BR-GEO-054` verifica reconstrução a partir de:

- RuleExecutions/versões;
- evidências;
- ScoreContributions;
- manifesto e pesos estáticos;
- `SCORE-GEO-004`;
- `HIERARCHICAL_WEIGHTED_READINESS_V1`.

Não é necessário reexecutar website, IA ou APIs externas.

## Relatórios

```text
readiness.html  SARI, dimensões, macrocomponentes, Coverage/Confidence e Critical Gates
scoring.html    fórmula, pesos, grupos, RuleExecutions representativas e contribuições
references.html proveniência e função de cada indicador no SARI
```

Os filenames são version-neutral. A versão metodológica pertence ao banco, manifests, metadados e conteúdo.

## Comparabilidade pré-produção

A formulação experimental de peso igual anterior a esta recalibração não é uma versão suportada do produto. Seus resultados devem ser regenerados.

Após entrada em produção, qualquer mudança incompatível que altere pesos, dimensões ou gates deverá ser versionada explicitamente para preservar séries históricas de clientes.

## Limite de validade

SARI-001/SCORE-GEO-004 são metodologias proprietárias do RASAi. Os pesos vigentes são decisões metodológicas pré-produção e não coeficientes causais homologados por Google, Microsoft, OpenAI ou outro mantenedor.