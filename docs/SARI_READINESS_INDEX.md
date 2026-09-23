# Índice de Prontidão Search & IA

**Nome em inglês:** **Search & AI Readiness Index**  
**Tradução:** **Índice de Prontidão Search & IA**  
**Versão pública:** **001**  
**Identificador metodológico técnico:** `SARI-001`  
**Estado:** vigente.

## 1. Objetivo

O **Índice de Prontidão Search & IA** (`SARI-001`, identificador metodológico técnico) é o índice público da metodologia proprietária do RASAi para consolidar sinais de prontidão relacionados a descoberta, acesso por crawlers, indexabilidade, recuperação, interpretação, utilidade, resposta, confiança e uso do conteúdo como evidência em Search e AI Search.

O índice é auditável e reprodutível. Não é padrão oficial de GEO/AEO, não é nota de Google, Bing, OpenAI ou outro mantenedor e não representa probabilidade de ranking ou citação.

Para significado de siglas, IDs e termos como GEO, Coverage, Confidence, Consolidation, AUD, CONS e CAT, consulte [`GLOSSARY.md`](GLOSSARY.md).

A leitura pública do SARI **não deve ser reduzida ao número 0-100**. O resultado executivo combina três camadas independentes e complementares:

1. **qualidade do universo medido**: score 0-100;
2. **força/completude da medição**: Coverage, Confidence e Consolidation;
3. **readiness operacional crítica**: Critical Readiness Gates e estado `READY`, `ATTENTION`, `BLOCKED` ou `UNKNOWN`.

## 2. Método vigente

O índice usa o **Método de Pontuação de Prontidão**, versão pública **001**. O contrato técnico preservado é:

```text
SCORE-GEO-004
```

Contrato de agregação vigente:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

`scoring_version` e o contrato de agregação são persistidos para garantir reprodutibilidade e comparabilidade. Auditorias com contratos metodológicos incompatíveis não devem ser comparadas numericamente como se fossem equivalentes.

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

`DISCOVERY_ACCESS` é a dimensão canônica para descoberta, acesso por crawlers, controles de crawler, redirects, SPA/navigation e links internos. Ela é semanticamente distinta de Accessibility/WCAG.

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

### 7.1 Como ler a aritmética

Para uma dimensão:

```text
w_g = peso fixo do scoring_group
n_g = quantidade de escopos aplicáveis do grupo
w_s = w_g / n_g
f_s = fator do resultado representativo do escopo

Peso avaliado = sum(w_s dos escopos com fator calculável)
Numerador = sum(w_s x f_s dos escopos avaliados)

Dimension Score = Numerador / Peso avaliado x 100
Dimension Coverage = Peso avaliado / Peso aplicável
```

Os fatores calculáveis são `PASS = 1`, `FAIL = 0` e `WARNING = warning_factor` definido no contrato da regra. O valor padrão de `warning_factor` é 0,50, mas existem fatores específicos versionados; portanto, `WARNING` não significa “50%” universal. `UNKNOWN` e `ERROR` permanecem no universo aplicável, mas não entram no peso avaliado, reduzindo Coverage. `NOT_APPLICABLE` legitimamente determinado sai do denominador.

Exemplo simplificado: um grupo com peso 0,30 aplicável a dois escopos recebe `w_s = 0,15` por escopo. Se um escopo resulta em PASS e o outro em WARNING com fator 0,50:

```text
Numerador = 0,15 x 1,00 + 0,15 x 0,50
          = 0,225

Peso avaliado = 0,30

Score do universo avaliado do grupo =
  0,225 / 0,30 x 100
  = 75
```

O exemplo mostra a aritmética local; o score final da dimensão combina todos os grupos aplicáveis segundo os pesos versionados.


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

Essa regra evita falso positivo de apresentação sem inventar penalidade matemática para ausência de evidência ou erro operacional de integração.

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

No Overall, Confidence combina:

1. **rigor crítico** para `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY`;
2. **confiança ponderada** pelas participações das dimensões aplicáveis.

Uma dimensão crítica LOW/UNAVAILABLE mantém Overall Confidence LOW. Para as demais dimensões, a influência acompanha o peso metodológico e evita que uma dimensão pequena domine sozinha a conclusão de toda a auditoria.

A aritmética do Overall usa a codificação vigente:

```text
HIGH        = 1,00
MEDIUM      = 0,75
LOW         = 0,40
UNAVAILABLE = 0,00

Confidence ponderada =
  sum(Peso da dimensão x Valor de confiança)
  / sum(Peso das dimensões aplicáveis)
```

Depois da média ponderada:

```text
>= 0,90 -> HIGH
>= 0,70 -> MEDIUM
<  0,70 -> LOW
```

Antes dessa classificação, qualquer dimensão crítica aplicável em `LOW` ou `UNAVAILABLE` força Overall Confidence para `LOW`; a média não pode mascarar insuficiência crítica.

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

Esse estado **não altera artificialmente o SARI numérico**, mas é a qualificação primária da apresentação pública do Overall. Exemplo válido:

```text
SARI: 82
Measurement: CONSOLIDATED
Readiness status: BLOCKED
Gate: INDEXABILITY
```

Isso significa: a medição é conclusiva, a qualidade agregada é 82 no universo medido, mas existe uma condição crítica que impede interpretar 82 como prontidão operacional plena. O HTML deve destacar `Readiness bloqueada`, mantendo `82/100` como qualidade medida secundária.

## 13. Content Value

`CONTENT_VALUE` contém três regras proprietárias:

- `BR-GEO-057`: utilidade e especificidade não trivial;
- `BR-GEO-058`: diferenciação, experiência, análise ou dado próprio explicitamente sustentado quando alegado;
- `BR-GEO-059`: profundidade/contexto proporcionais ao propósito e à evidência disponível.

Classificação: `RASAI_HEURISTIC`.

Contrato técnico:

```text
CONTENT-VALUE-BASELINE-001
```

O identificador `BASELINE` faz parte do nome técnico versionado do contrato e não representa histórico público de produto. O cálculo usa somente conteúdo principal já persistido e é conservador. Em especial, **ausência de prova de diferenciação/originalidade fica `UNKNOWN`**, nunca `FAIL` inventado.

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
avaliação corroborativa
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

### 16.2 Common Crawl e BR-GEO-060

`BR-GEO-060` é uma exceção explicitamente score-eligible para corroboração externa de descoberta histórica observada no índice Common Crawl.

Contrato:

- dimensão `DISCOVERY_ACCESS`;
- grupo `EXTERNAL_CRAWL_CORROBORATION`;
- peso de 3% dentro da dimensão, equivalente a impacto máximo teórico de 0,45 ponto no Overall;
- evidência externa somente positiva: quando todos os requisitos forem satisfeitos, a regra pode produzir `PASS`;
- ausência de registro, erro, timeout, indisponibilidade, alvo privado ou resposta inconclusiva não produzem `FAIL`, zero, redução de Coverage ou redução de Confidence;
- a regra não participa dos Critical Readiness Gates;
- evidência e RuleExecution são persistidas antes do cálculo para manter reprodutibilidade.

Contrato detalhado: [SARI_EXTERNAL_CRAWL_CORROBORATION.md](SARI_EXTERNAL_CRAWL_CORROBORATION.md).

## 17. Resultados observados

Continuam fora do Overall operacional:

- posição SERP;
- concorrentes observados;
- impressões, cliques e CTR;
- Search Console;
- menções/citações em mecanismos generativos;
- Observed Generative Visibility.

Esses dados são resultados. Servem para observabilidade e podem sustentar pesquisa empírica separada, sem tornar o índice circular ou alterar silenciosamente o contrato de scoring.

## 18. Relatórios

Todas as superfícies canônicas são materializadas após uma auditoria concluída com sucesso. A presença do HTML não implica execução da capacidade correspondente; ausência de dado deve aparecer como estado neutro ou explicativo.

```text
report-catalog/index.html               -> síntese executiva com readiness qualificada
report-catalog/sari.html                -> SARI-001, qualidade medida, força da medição, dimensões e gates
report-catalog/methodology.html         -> fórmula, pesos, grupos, Coverage, Confidence e rastreabilidade
report-catalog/capture-context.html     -> contexto da auditoria e configuração materializada
report-catalog/execution-evidence.html  -> evidência da execução, fulfillment e integridade
report-catalog/ai-integrations.html     -> telemetria de IA e integrações externas
report-catalog/metrics.html             -> inventário transversal de índices e métricas
report-catalog/cat-01.html              -> fundamentos técnicos, descoberta e padrões web
report-catalog/cat-02.html              -> acessibilidade automatizada
report-catalog/cat-03.html              -> conteúdo, semântica e dados estruturados
report-catalog/cat-04.html              -> Web Performance e dados CrUX/Lighthouse
report-catalog/cat-05.html              -> Search & AI Intelligence e observabilidade aplicável
report-catalog/cat-06.html              -> Apdex de navegação
report-catalog/cat-07.html              -> Apdex de experiência
report-catalog/cat-08.html              -> análise profunda e melhorias
report-catalog/cat-09.html              -> remediações
report-catalog/cat-10.html              -> segurança passiva
report-catalog/directed-analysis.html   -> análise direcionada
```

`index.html` e `sari.html` devem usar o estado de readiness/medição como conclusão visual primária. A banda `Excelente/Alta/Moderada/Baixa/Crítica` permanece válida para a **qualidade numérica medida**, mas não pode mascarar `PARTIAL`, `NOT_CONSOLIDATED`, `BLOCKED` ou `UNKNOWN`.

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

O SARI-001 é uma metodologia proprietária, transparente e reproduzível do RASAi. Os pesos vigentes são decisões metodológicas internas fundamentadas na arquitetura do problema e **não são pesos estatisticamente provados como causais**.

Evidência empírica externa pode ser usada para avaliar associação entre readiness e resultados reais de Search/AI Search, desde que permaneça separada do cálculo operacional. Qualquer alteração de pesos, dimensões, grupos ou fórmulas que mude o significado do índice exige nova versão metodológica explícita e não pode reinterpretar silenciosamente auditorias persistidas.
