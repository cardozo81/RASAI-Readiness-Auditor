# Aplicabilidade de dimensões e premissas mínimas - SARI-001 / SCORE-GEO-004

**Estado no baseline de desenvolvimento:** aprovado / vigente  
**Scoring vigente em runtime:** `SCORE-GEO-004`  
**Contrato de agregação:** `HIERARCHICAL_WEIGHTED_READINESS_V1`

## 1. Princípio

`NOT_APPLICABLE` não significa falha, evidência ausente nem score zero.

Uma dimensão fica:

- `APPLICABLE` quando existe pelo menos uma `RuleExecution` aplicável;
- `NOT_APPLICABLE` quando existem execuções e o universo observado da dimensão está legitimamente fora de aplicabilidade;
- `NOT_CONSOLIDATED` quando a dimensão não possui medição utilizável, a aplicabilidade está bloqueada ou Coverage/Confidence é insuficiente;
- `PARTIAL` quando existe medição útil, mas a dimensão não satisfaz o gate completo de consolidação.

A ausência completa de `RuleExecutions` de uma dimensão nunca se torna um `NOT_APPLICABLE` benigno.

Overall ainda pode possuir valor numérico quando uma dimensão aplicável **não crítica** não foi suficientemente medida. Nesse caso, a dimensão ausente contribui com Coverage zero, seu peso numérico não é imputado como score 0 nem 100 e Overall só pode ser `CONSOLIDATED` se Coverage/Confidence ponderadas remanescentes satisfizerem o gate publicado.

## 2. Execução ausente versus execução explícita não resolvida

O pipeline de scoring deve preservar a diferença entre:

```text
não aplicável
não resolvido/desconhecido
erro de execução
nenhuma execução materializada
```

Para regra/grupo aplicável, falha de aquisição ou pré-requisito deve materializar estado explícito de `RuleExecution`, como `UNKNOWN`, `ERROR` ou `NOT_APPLICABLE` bloqueado por pré-requisito, conforme definido pela família da regra. Um grupo aplicável obrigatório não pode desaparecer silenciosamente apenas para reduzir o denominador de Coverage.

Em nível de dimensão, ausência completa de execuções resulta em:

```text
Value = null
Coverage = 0
Confidence = UNAVAILABLE
Consolidation = NOT_CONSOLIDATED
limitation = NO_RULE_EXECUTIONS
```

Essa dimensão permanece no universo aplicável de Overall, salvo quando a não aplicabilidade tiver sido positivamente estabelecida como `NOT_APPLICABLE`.

## 3. Pré-requisito bloqueado

`PREREQUISITE_BLOCKED` não é não aplicabilidade benigna.

Reason codes como:

```text
SEMANTIC_PREREQUISITE_BLOCKED
CONTENT_EXTRACTION_PREREQUISITE_BLOCKED
```

mantêm a medição afetada sem resolução. Eles não podem ser promovidos a `NOT_APPLICABLE` apenas para elevar score, Coverage ou Consolidation.

Para dimensões críticas, medição insuficiente também bloqueia consolidação de Overall por meio do critical measurement gate.

## 4. Dimensões e Overall

Para cada dispositivo auditado:

1. materializar as onze dimensões SARI;
2. separar dimensões legitimamente `NOT_APPLICABLE`;
3. preservar estados explícitos não resolvidos/de erro;
4. calcular Value, Coverage, Confidence e Consolidation por dimensão de forma independente;
5. calcular Overall ponderado apenas sobre valores numéricos de dimensões medidas/aplicáveis;
6. calcular Overall Coverage sobre o universo ponderado aplicável completo;
7. aplicar gates de Confidence e medição crítica;
8. persistir limitações, dimensões excluídas e estados de Critical Readiness Gate.

Contrato Overall:

```text
HIERARCHICAL_WEIGHTED_READINESS_V1
```

Pesos das dimensões, confirmados pelo contrato vigente:

| Dimensão | Valor vigente | Valores permitidos | Recomendado |
|---|---:|---|---|
| `DISCOVERY_ACCESS` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `INDEXABILITY` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CONTENT_EXTRACTABILITY` | 15% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `SEMANTIC_STRUCTURE` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `ENTITY_CLARITY` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `STRUCTURED_DATA` | 5% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `ANSWERABILITY` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CITATION_READINESS` | 7% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `EVIDENCE_TRUST` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `INTENT_COVERAGE` | 5% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |
| `CONTENT_VALUE` | 8% | fixo em `SARI_DIMENSION_WEIGHTS_V1` | não customizar sem nova versão metodológica |

Esses pesos não são variáveis de usuário. Alterá-los sem nova versão de contrato quebraria reprodutibilidade/comparabilidade.

Uma dimensão legitimamente `NOT_APPLICABLE` sai do denominador e não recebe 0 nem 100.

Uma dimensão aplicável não crítica sem valor **não** recebe score numérico fabricado. Ela reduz Overall Coverage e Confidence conforme seu peso publicado. A consolidação de Overall só é permitida se a medição ponderada ainda satisfizer Coverage mínima de 80% e Confidence `HIGH`/`MEDIUM`.

Dimensões críticas são mais rígidas: `DISCOVERY_ACCESS`, `INDEXABILITY` e `CONTENT_EXTRACTABILITY` não podem permanecer insuficientemente medidas em um Overall consolidado.

## 5. Score, Coverage, Confidence e Consolidation são conceitos separados

O contrato separa deliberadamente:

```text
Score         qualidade do universo avaliado
Coverage      completude ponderada da medição aplicável
Confidence    força da medição
Consolidation suficiência para publicação analítica
Critical Gate estado operacional de readiness
```

Portanto:

- `UNKNOWN`/`ERROR` não viram qualidade zero;
- medição não crítica ausente não vira qualidade zero nem 100;
- Score numérico alto com medição incompleta deve expor Coverage/Confidence reduzidas;
- Score numérico baixo pode ser `CONSOLIDATED` quando a baixa qualidade foi medida com força suficiente;
- SARI numericamente alto pode coexistir com estado operacional `BLOCKED` quando uma condição crítica observada falhou.

## 6. Gates de medição crítica e readiness

Dimensões críticas:

```text
DISCOVERY_ACCESS
INDEXABILITY
CONTENT_EXTRACTABILITY
```

Uma dimensão crítica aplicável sem medição suficiente bloqueia Overall `CONSOLIDATED`, independentemente da Coverage agregada.

Separadamente, Critical Readiness Gates resumem condições operacionais observadas:

- Discovery Gate: `PAGE_ACCESS`, `ROBOTS`, `REDIRECT`;
- Indexability Gate: `INDEX_DIRECTIVES`, `CANONICAL`, `SOFT_ERROR`;
- Extraction Gate: `RENDER_ACCESS`, `JS_CONTENT`, `CONTENT_EXTRACTION`.

Estados permitidos do gate:

```text
PASS
WARNING
BLOCKED
UNKNOWN
```

Estados de readiness:

```text
READY
ATTENTION
BLOCKED
UNKNOWN
```

Esses estados não reescrevem o SARI numérico.

## 7. Structured Data / JSON-LD

JSON-LD é opcional/contextual no baseline geral. Ausência isolada não é falha universal de readiness.

Se `BR-GEO-034..037` estiverem legitimamente `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- a ausência isolada não cria penalidade automática;
- a dimensão não é imputada como zero;
- seu peso de 5% sai do denominador Overall aplicável.

Se JSON-LD estiver presente, sintaxe, tipos/propriedades e coerência factual passam a ser avaliáveis.

Structured Data pode normalizar fatos observados, mas não deve inventar preço, rating/review, autoria, datas, fatos de produto/serviço, claims ou entidades.

O parser vigente é orientado a JSON-LD em `script[type="application/ld+json"]`; Microdata/RDFa não deve ser descrito como totalmente coberto sem implementação/testes equivalentes.

## 8. Content Value

`CONTENT_VALUE` possui peso vigente de 8% e natureza `RASAI_HEURISTIC`.

As regras baseline medem somente evidência defensável a partir do conteúdo preservado:

- conteúdo útil/específico e não trivial;
- diferenciação, experiência, análise ou dados first-party explícitos quando evidenciados;
- profundidade/contexto proporcionais.

Ausência de prova de diferenciação ou originalidade permanece `UNKNOWN`, não `FAIL`. Esse peso não resolvido reduz Coverage em vez de penalizar qualidade sem evidência.

## 9. Premissas mínimas/contextuais

| Tema | Classe | Efeito no RASAi |
|---|---|---|
| URL tecnicamente recuperável | `MINIMUM` | Falha material compromete readiness técnica. |
| Documento/conteúdo analisável | `MINIMUM` | Dimensões dependentes não podem consolidar sem base utilizável. |
| Conteúdo essencial após renderização | `MINIMUM` quando JS se aplica | Informação principal deve continuar recuperável. |
| Conteúdo principal identificável | `MINIMUM` | Base para análise semântica, answerability e content value. |
| Informação importante em texto recuperável | `MINIMUM` | Informação exclusivamente visual/oculta limita extração. |
| Indexabilidade coerente com intenção pública | `CONTEXTUAL/MINIMUM` para Search público | Bloqueios intencionais podem tornar uma URL inelegível à busca pública. |
| Tema/intenção identificável | `SEMANTIC MINIMUM` | Necessário para avaliar o que a URL responde. |
| Claims/valores coerentes | `FACTUAL MINIMUM` | Contradições reduzem readiness de evidência/citação. |
| JSON-LD | `OPTIONAL / REINFORCEMENT` | Quando presente, deve ser válido/coerente. |
| Sitemap | `OPTIONAL / DISCOVERY` | Útil; ausência isolada não é `FAIL`. |
| Canonical | `CONTEXTUAL` | Importante para duplicação/preferência; não é bloqueador universal isolado. |
| `robots.txt` | `OPTIONAL AS FILE` | Ausência não significa bloqueio; regras presentes são interpretadas. |
| Autor/publicador | `CONTEXTUAL` | Depende do tipo de página/claim. |
| Data de publicação/atualização | `CONTEXTUAL` | Relevante a conteúdo temporal/editorial. |
| `llms.txt` | `NOT REQUIRED` | Não é requisito universal de Search & AI. |
| GPTBot permitido | `NOT REQUIRED` para Search readiness | GPTBot e crawlers de Search têm finalidades distintas. |
| markup especial GEO/AEO | `NOT REQUIRED` | Não se presume requisito oficial universal. |
| chunking artificial para IA | `NOT REQUIRED` | Não é introduzido como regra artificial de scoring. |

## 10. Confidence

Confidence representa a força da conclusão do auditor, não qualidade textual.

Limiares vigentes em nível de dimensão:

| Estado | Valor vigente/critério | Valores permitidos | Recomendado |
|---|---|---|---|
| `HIGH` | Coverage >= 90%, evidência completa e zero erros | fixo no contrato vigente | não customizar sem nova versão metodológica |
| `MEDIUM` | Coverage >= 80% e zero erros | fixo no contrato vigente | não customizar sem nova versão metodológica |
| `LOW` | mensurável, mas abaixo dos requisitos `HIGH`/`MEDIUM` | fixo no contrato vigente | interpretar como limitação de força, não como falha do conteúdo |
| `UNAVAILABLE` | nenhum peso aplicável avaliado | fixo no contrato vigente | preservar ausência; não converter em zero |

Overall Confidence combina confiança ponderada com tratamento estrito das dimensões críticas. Uma dimensão crítica `LOW`/`UNAVAILABLE` mantém Overall Confidence `LOW`.

`LOW` isolado não autoriza finding/recomendação de conteúdo. Uma ação exige `RuleExecution`/finding específico e evidência.

## 11. Limiares de Consolidation

Valores vigentes da dimensão:

| Estado | Critério vigente | Permitido/recomendado |
|---|---|---|
| `CONSOLIDATED` | Coverage >= 80% e Confidence `HIGH`/`MEDIUM` | contrato fixo; não customizar sem versionamento |
| `PARTIAL` | mensurável, Coverage >= 50% e abaixo do gate completo | preservar o estado; não promover artificialmente |
| `NOT_CONSOLIDATED` | Coverage < 50% ou Confidence `UNAVAILABLE` | preservar ausência/insuficiência |
| `NOT_APPLICABLE` | legitimamente fora do universo aplicável | não imputar score |

Overall `CONSOLIDATED` exige simultaneamente:

- valor numérico existente;
- Overall Coverage >= 80%;
- Overall Confidence `HIGH`/`MEDIUM`;
- nenhuma dimensão crítica aplicável sem medição suficiente.

Overall `PARTIAL` exige:

- valor numérico existente;
- Coverage >= 50%;
- Confidence disponível;
- gate completo não satisfeito.

Overall `NOT_CONSOLIDATED` ocorre quando não há medição numérica, existe bloqueador crítico de medição ou a medição está abaixo do gate mínimo.

## 12. Relatórios

`report/readiness.html` e `report/scoring.html` distinguem:

- Score;
- Coverage;
- Confidence;
- Consolidation;
- `NOT_APPLICABLE`;
- `NOT_CONSOLIDATED`;
- contrato de scoring/agregação;
- Critical Readiness Gates;
- limitações e dimensões excluídas.

O relatório não pode apresentar valor numérico calculado sobre universo medido como se Coverage fosse 100% quando não é.

## 13. Reprodutibilidade e comparabilidade

`BR-GEO-054` valida integridade/reprodutibilidade do contrato de scoring persistido. Auditorias atuais usam `SCORE-GEO-004` com `HIERARCHICAL_WEIGHTED_READINESS_V1`.

Dadas as mesmas `RuleExecutions`, contribuições, evidências e fórmula/gates versionados, dimensões e estado Overall devem ser reconstruíveis sem reabrir o website nem chamar IA.

Auditorias históricas que persistam outro `scoring_version`/contrato de agregação devem permanecer reproduzíveis sob o próprio contrato e nunca ser recalculadas silenciosamente como `SCORE-GEO-004`. Quando o contrato persistido for incompatível com o vigente, a comparação deve expor `NOT_COMPARABLE`/limitação equivalente conforme a superfície consumidora.

## 14. Testes mínimos

Validar que:

1. ausência completa de `RuleExecutions` de uma dimensão produz `NOT_CONSOLIDATED`, nunca `NOT_APPLICABLE` benigno;
2. dimensão não crítica ausente reduz Overall Coverage ponderada e é limitada explicitamente, em vez de ser imputada como 0 ou 100;
3. dimensão crítica ausente/insuficiente bloqueia consolidação Overall;
4. `NOT_APPLICABLE` legítimo não recebe score artificial zero nem máximo;
5. pré-requisitos bloqueados permanecem não resolvidos/bloqueantes, e não benignamente não aplicáveis;
6. Structured Data presente torna regras relevantes aplicáveis;
7. `PASS`/`WARNING`/`FAIL` participam do valor conforme contrato de dimensão/grupo;
8. `UNKNOWN`/`ERROR` reduzem Coverage/Confidence sem se tornarem `FAIL`;
9. quantidade de páginas não multiplica importância do scoring group;
10. evidência determinística prevalece sobre corroboração de IA no mesmo escopo/grupo;
11. Structured Data legitimamente ausente não recebe score artificial;
12. limitações/dimensões excluídas do Overall e estados de Critical Gate são persistidos;
13. `BR-GEO-054` é reproduzível para o contrato persistido;
14. relatórios não equivalem Confidence `LOW` a conteúdo ruim;
15. heurísticas internas são distinguidas de fontes externas;
16. contratos incompatíveis de scoring/agregação não são mesclados silenciosamente.