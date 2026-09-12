# Search & AI Readiness Index - SARI-001

## 1. Objetivo

O **Search & AI Readiness Index (`SARI-001`)** é a identidade pública da metodologia proprietária do RASAi para consolidar sinais de prontidão relacionados a descoberta, acesso por crawlers, indexabilidade, recuperação, interpretação, utilidade, resposta, confiança e uso do conteúdo como evidência em Search e AI Search.

O índice é auditável e reprodutível. Não é padrão oficial de GEO/AEO, não é nota de Google, Bing, OpenAI ou outro mantenedor e não representa probabilidade de ranking ou citação futura.

A leitura pública do SARI **não deve ser reduzida ao número 0-100**. O resultado executivo combina três camadas independentes e complementares:

1. **qualidade do universo medido**: score 0-100;
2. **força/completude da medição**: Coverage, Confidence e Consolidation;
3. **readiness operacional crítica**: Critical Readiness Gates e estado `READY`, `ATTENTION`, `BLOCKED` ou `UNKNOWN`.

## 2. Método vigente

O SARI-001 usa:

```text
SCORE-GEO-004
```

O RASAi ainda está em fase de desenvolvimento/pré-produção. A recalibração descrita neste documento substitui a formulação experimental anterior do mesmo `SCORE-GEO-004`; não foi criada uma versão comercial adicional porque não existe série histórica de produção ou contrato externo que precise ser preservado.

Auditorias de desenvolvimento produzidas antes desta recalibração, identificadas pelo contrato antigo de agregação, devem ser consideradas **não comparáveis** e regeneradas quando precisarem ser reutilizadas. O histórico de engenharia permanece no Git, não como metodologia ativa do produto.

Contrato de agregação vigente:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

## 3. Princípio de cálculo

O SARI não soma RuleExecutions diretamente. A hierarquia é:

```text
RuleExecution
   ↓
página/escopo global
   ↓
Scoring Group
   ↓
Dimension Score
   ↓
Macrocomponente
   ↓
SARI Overall
```

Um `scoring_group` possui peso fixo dentro de sua dimensão. Quando o mesmo grupo é avaliado em várias páginas, seu peso é distribuído entre os escopos aplicáveis. Portanto, aumentar uma auditoria de 10 para 500 páginas **não reduz artificialmente a importância de sinais globais**, como `robots.txt` ou sitemap, nem multiplica o peso de uma regra apenas porque ela executou mais vezes.

## 4. Dimensões e pesos

Os pesos são parte fixa do contrato. Não são configuráveis por auditoria.

| Dimensão | Peso no SARI |
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
| **Total** | **100%** |

`DISCOVERY_ACCESS` substitui a denominação interna anterior `TECHNICAL_ACCESSIBILITY`. O novo nome evita confusão com Accessibility/WCAG e representa melhor o conteúdo real da dimensão: acesso, crawler controls, redirects, SPA/navigation e internal links.

## 5. Macrocomponentes

Para leitura executiva, as dimensões são agrupadas em macrocomponentes:

| Macrocomponente | Peso | Composição |
|---|---:|---|
| Discovery & Crawler Access | 15% | `DISCOVERY_ACCESS` |
| Indexability & Canonicalization | 15% | `INDEXABILITY` |
| Rendering & Extractability | 15% | `CONTENT_EXTRACTABILITY` |
| Semantic Understandability | 15% | `SEMANTIC_STRUCTURE` 7% + `ENTITY_CLARITY` 8% |
| Content Utility & Intent | 20% | `ANSWERABILITY` 7% + `INTENT_COVERAGE` 5% + `CONTENT_VALUE` 8% |
| Evidence, Trust & Citation | 15% | `CITATION_READINESS` 7% + `EVIDENCE_TRUST` 8% |
| Structured Data | 5% | `STRUCTURED_DATA` |

Os macrocomponentes são uma projeção explicativa; não criam uma segunda aritmética paralela.

## 6. Resultados das regras

Estados possíveis:

```text
PASS
WARNING
FAIL
UNKNOWN
ERROR
NOT_APPLICABLE
```

Fatores de qualidade:

```text
PASS    = 1.00
WARNING = 0.50 por padrão
FAIL    = 0.00
```

Alguns grupos possuem `warning_factor` específico e versionado.

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` nunca são convertidos silenciosamente em `FAIL`.

## 7. Score de uma dimensão

Dentro de cada dimensão:

```text
Group Weight = peso fixo do scoring_group
Scope Weight = Group Weight / quantidade de escopos aplicáveis do grupo

Dimension Score =
  sum(Scope Weight × Result Factor avaliados)
  / sum(Scope Weight avaliados)
  × 100
```

A Coverage da dimensão mede quanto do peso aplicável foi efetivamente avaliado:

```text
Dimension Coverage = evaluated applicable weight / total applicable weight
```

## 8. Overall

O Overall usa os pesos fixos das dimensões:

```text
SARI =
  sum(Dimension Weight × Dimension Score medido)
  / sum(Dimension Weight medido e aplicável)
```

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe zero nem 100.

Uma dimensão não crítica sem medição suficiente pode reduzir Coverage/Confidence sem apagar automaticamente o valor numérico das demais dimensões. Já as dimensões críticas possuem gates adicionais de suficiência da medição.

### 8.1 Regra de apresentação pública do Overall

O valor numérico continua sendo preservado sem truncamento artificial para manter a aritmética reproduzível. Porém, o relatório não deve apresentar a banda numérica como se fosse, isoladamente, a conclusão de readiness.

Exemplos:

```text
96/100 + CONSOLIDATED + READY
=> Readiness pronta; qualidade medida Excelente

96/100 + PARTIAL
=> Readiness com medição parcial; qualidade medida Excelente

96/100 + CONSOLIDATED + BLOCKED
=> Readiness bloqueada; qualidade medida Excelente
```

Nos dois últimos casos, a interface **não pode usar “Excelente” como badge primária de readiness**. A nota permanece visível como qualidade do universo medido, enquanto o estado de medição/gate ocupa a posição de conclusão executiva.

Essa regra corrige um falso positivo de apresentação sem inventar penalidade matemática para ausência de evidência ou erro operacional de integração.

## 9. Coverage

Coverage mede **completude**, não qualidade do website.

No Overall:

```text
Overall Coverage =
  sum(Dimension Weight × Dimension Coverage)
  / sum(Dimension Weight aplicável)
```

A quantidade de páginas não cria peso extra por si só.

## 10. Confidence

Na dimensão:

```text
HIGH        Coverage >= 90%, evidência completa, zero errors
MEDIUM      Coverage >= 80%, zero errors
LOW         existe avaliação, mas os critérios acima não foram satisfeitos
UNAVAILABLE Coverage <= 0
```

No Overall, Confidence deixa de ser simplesmente a pior Confidence de qualquer dimensão. O contrato vigente combina:

1. **rigor crítico** para `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY`;
2. **confiança ponderada** pelas participações das dimensões aplicáveis.

Uma dimensão crítica LOW/UNAVAILABLE mantém Overall Confidence LOW. Para as demais dimensões, a influência acompanha o peso metodológico e evita que uma dimensão pequena domine sozinha a conclusão de toda a auditoria.

## 11. Consolidation

Consolidation responde se a **medição é forte o suficiente para publicação analítica**, não se o website está bom.

Dimensão:

```text
CONSOLIDATED     Coverage >= 80% e Confidence HIGH/MEDIUM
PARTIAL          avaliação disponível com Coverage >= 50% abaixo do gate completo
NOT_CONSOLIDATED Coverage < 50% ou Confidence UNAVAILABLE
NOT_APPLICABLE   dimensão legitimamente fora do universo aplicável
```

Overall:

- Coverage >= 80%;
- Confidence HIGH/MEDIUM;
- nenhuma dimensão crítica aplicável sem medição suficiente.

A qualidade do website e a qualidade da medição permanecem separadas. Um website pode ter score baixo e `CONSOLIDATED`, pois uma conclusão ruim pode estar fortemente medida.

## 12. Critical Readiness Gates

Além do número SARI existem três gates operacionais:

### Discovery Gate

Grupos principais:

- `PAGE_ACCESS`;
- `ROBOTS`;
- `REDIRECT`.

### Indexability Gate

- `INDEX_DIRECTIVES`;
- `CANONICAL`;
- `SOFT_ERROR`.

### Extraction Gate

- `RENDER_ACCESS`;
- `JS_CONTENT`;
- `CONTENT_EXTRACTION`.

Estados:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

O resultado geral de readiness é projetado como:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

Esse estado **não altera artificialmente o SARI numérico**, mas passa a ser a qualificação primária da apresentação pública do Overall. Exemplo válido:

```text
SARI: 82
Measurement: CONSOLIDATED
Readiness status: BLOCKED
Gate: INDEXABILITY
```

Isso significa: a medição é conclusiva, a qualidade agregada é 82 no universo medido, mas existe uma condição crítica que impede interpretar 82 como prontidão operacional plena. O HTML deve destacar `Readiness bloqueada`, mantendo `82/100` como qualidade medida secundária.

## 13. Content Value

`CONTENT_VALUE` acrescenta três regras proprietárias:

- `BR-GEO-057`: utilidade e especificidade não trivial;
- `BR-GEO-058`: diferenciação, experiência, análise ou dado próprio explicitamente sustentado quando alegado;
- `BR-GEO-059`: profundidade/contexto proporcionais ao propósito e à evidência disponível.

Classificação: `RASAI_HEURISTIC`.

A baseline vigente é:

```text
CONTENT-VALUE-BASELINE-001
```

Ela usa somente conteúdo principal já persistido e é conservadora. Em especial, **ausência de prova de diferenciação/originalidade fica `UNKNOWN`**, nunca `FAIL` inventado.

## 14. Structured Data

Structured Data possui peso máximo de **5% quando aplicável**.

Não existe requisito universal de JSON-LD para Search ou recursos generativos. Portanto:

- dimensão legitimamente não aplicável sai do denominador;
- markup existente e válido pode ser avaliado favoravelmente;
- markup inválido ou contraditório pode ser desfavorável;
- ausência não deve ser tratada como bloqueio universal de readiness.

## 15. Precedência de evidência e IA

O scoring final permanece determinístico sobre RuleExecutions persistidas.

Contrato:

```text
fato determinístico conclusivo
    >
avaliação IA corroborativa
```

BR-GEO-055/056, por exemplo, podem aprofundar sitemap/robots quando IA técnica evidence-bound está habilitada, mas compartilham os mesmos `scoring_group` das regras determinísticas e não criam bônus duplicado. Uma avaliação IA não pode sobrescrever arbitrariamente um hard fact determinístico PASS/WARNING/FAIL da mesma condição.

O provider nunca escolhe pesos, thresholds, fatores ou o Overall.

## 16. Lighthouse, Core Web Vitals, Accessibility, Apdex e outras integrações

Os **scores de categoria** permanecem independentes do SARI:

- Lighthouse Performance;
- Lighthouse Accessibility;
- Lighthouse Best Practices;
- Lighthouse SEO;
- Core Web Vitals / CrUX;
- Synthetic Navigation Apdex;
- Synthetic User Experience Apdex;
- validadores/serviços externos de padrões quando não existe regra SARI equivalente contratada.

Nenhum desses scores é multiplicado por um peso SARI.

Um **audit individual do Lighthouse** ou outro finding técnico externo pode corroborar uma BR-GEO que avalie exatamente a mesma condição técnica, desde que exista mapeamento explícito e sem dupla pontuação. O category score nunca é usado como atalho para o SARI.

### 16.1 Erro de integração não é erro do website

Estados como timeout, quota, autenticação inválida, indisponibilidade de provider, erro de API ou falha de transporte descrevem a **medição/integrador**. Eles podem reduzir Coverage/Confidence, deixar regras `UNKNOWN` ou produzir diagnóstico operacional, mas não são convertidos em `FAIL` do website.

Quando uma integração obtém evidência conclusiva sobre o website e existe regra contratada equivalente, essa evidência pode participar do score pelo caminho normal de RuleExecution. Essa distinção evita tanto falso positivo quanto penalidade indevida por falha externa.

## 17. Outcomes observados

Continuam fora do Overall operacional:

- posição SERP;
- concorrentes observados;
- impressões, cliques e CTR;
- Search Console;
- menções/citações em mecanismos generativos;
- Observed Generative Visibility.

Esses dados são outcomes. Servem para observabilidade e para futura validação/calibração empírica do SARI, sem tornar o índice circular.

## 18. Relatórios

```text
index.html             -> síntese executiva com readiness qualificada
readiness.html         -> SARI-001, qualidade medida, força da medição, macrocomponentes, dimensões e gates
scoring.html           -> fórmula, pesos, grupos, Coverage, Confidence e rastreabilidade
web-performance.html   -> Lighthouse + Core Web Vitals/CrUX
accessibility.html     -> acessibilidade automatizada
apdex.html             -> Synthetic Navigation Apdex
ai-visibility.html     -> outcomes observados de AI Search
search-intelligence.html -> SERP/Search Intelligence quando materializado
references.html        -> proveniência e função de cada indicador no SARI
```

`index.html` e `readiness.html` devem usar o estado de readiness/medição como conclusão visual primária. A banda `Excelente/Alta/Moderada/Baixa/Crítica` permanece válida para a **qualidade numérica medida**, mas não pode mascarar `PARTIAL`, `NOT_CONSOLIDATED`, `BLOCKED` ou `UNKNOWN`.

## 19. Rastreabilidade

Resultados preservam:

- `scoring_version = SCORE-GEO-004`;
- `OVERALL_AGGREGATION:HIERARCHICAL_WEIGHTED_READINESS_V1`;
- versão dos pesos de dimensão/grupo;
- versão de Critical Gates e Confidence;
- RuleExecutions;
- evidências;
- ScoreContributions;
- limitações de Coverage/Confidence;
- estado dos Critical Gates.

A mesma entrada persistida deve produzir o mesmo resultado sem reexecutar website, IA ou APIs externas.

## 20. Limite de validade e calibração

O SARI-001 é uma metodologia proprietária, transparente e reproduzível do RASAi. Os pesos atuais são decisões metodológicas pré-produção fundamentadas na arquitetura do problema; **não são pesos estatisticamente provados como causais**.

A revisão de calibração de setembro de 2026 não encontrou base empírica suficiente para alterar pesos de dimensão/grupo apenas porque integrações independentes reportaram erros. A distorção comprovada estava na **apresentação pública de um score alto sem qualificação suficiente de Coverage/Confidence/Consolidation/Critical Gates**. Por isso a aritmética foi preservada e a semântica de publicação foi endurecida.

A validação empírica futura deve estudar associação entre readiness e outcomes reais de Search/AI Search. Qualquer recalibração após existência de contrato público ou série histórica de produção deverá ser versionada explicitamente.