# SearchGEO Readiness Index — SGRI-001

## 1. Objetivo

O **SearchGEO Readiness Index (SGRI-001)** é a identidade pública da metodologia proprietária usada pelo SearchGEO para consolidar sinais de prontidão relacionados a descoberta, interpretação, recuperação, resposta e uso do conteúdo como evidência em Search e AI Search.

O índice é:

- determinístico sobre as `RuleExecutions` persistidas;
- evidence-based nas observações que o alimentam;
- versionado;
- reprodutível;
- auditável;
- explicitamente separado de métricas externas como Core Web Vitals, Lighthouse e Apdex.

O índice **não é**:

- um padrão oficial de GEO/AEO;
- uma nota do Google, Bing, OpenAI ou outro mantenedor;
- uma probabilidade de ranking;
- uma probabilidade de citação por IA;
- uma certificação de qualidade;
- uma combinação aritmética de métricas externas.

## 2. Compatibilidade com SCORE-GEO-002

Nesta evolução, a identidade pública muda para:

```text
SGRI-001
```

mas o motor de cálculo persistido continua identificado como:

```text
SCORE-GEO-002
```

A decisão é intencional.

Não houve nesta mudança:

- alteração de pesos;
- alteração dos fatores PASS/WARNING/FAIL;
- alteração dos thresholds de Coverage/Confidence/Consolidation;
- recalibração empírica;
- migração destrutiva de auditorias históricas.

Portanto, `SGRI-001` descreve a **metodologia pública e sua apresentação**, enquanto `SCORE-GEO-002` permanece a versão técnica do cálculo persistido até que a aritmética seja efetivamente alterada.

Uma futura mudança matemática deve receber nova versão de motor e documentação de migração/comparabilidade.

## 3. Dimensões atuais

O motor atual trabalha com as dimensões:

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

O `OVERALL_READINESS` é derivado das dimensões aplicáveis suficientemente consolidadas.

## 4. Fórmula atual

Para cada dimensão:

```text
Dimension Score = Σ(weight × result_factor)
                  ─────────────────────────
                  Σ(weight evaluated)
                  × 100
```

Fatores padrão:

```text
PASS    = 1.00
WARNING = 0.50
FAIL    = 0.00
```

`UNKNOWN`, `ERROR` e `NOT_APPLICABLE` não são convertidos automaticamente em `FAIL`.

Regras correlacionadas podem ser agrupadas para evitar dupla penalização do mesmo fenômeno dentro do mesmo escopo.

## 5. Overall Readiness

O `OVERALL_READINESS` atual é a média simples das dimensões aplicáveis quando existe base suficiente para consolidação.

Uma dimensão legitimamente `NOT_APPLICABLE` fica fora do denominador. Uma dimensão cuja aplicabilidade não pôde ser resolvida por falta de evidência não é silenciosamente tratada como não aplicável.

Essa agregação é **heurística SearchGEO**. Não existe fonte externa que homologue a média ou seus pesos como um score GEO universal.

## 6. Coverage

Coverage mede a parcela do universo aplicável que foi efetivamente avaliada:

```text
Coverage = evaluated applicable weight / total applicable weight
```

Coverage não mede qualidade do site.

Uma página pode ter score alto e Coverage insuficiente. Nesse caso, a conclusão deve ser comunicada com ressalvas.

## 7. Confidence

Confidence qualifica a força da conclusão do auditor.

Os thresholds atuais são internos e versionados pelo SearchGEO. Eles consideram Coverage, completude de evidência e erros de execução.

Confidence não é:

- confiança estatística no sentido de intervalo de confiança;
- probabilidade de acerto de uma IA;
- qualidade do texto;
- chance de ranking ou citação.

## 8. Consolidation

Consolidation indica se existe base suficiente para publicar uma conclusão agregada.

Os estados incluem:

- `CONSOLIDATED`
- `PARTIAL`
- `NOT_CONSOLIDATED`
- `NOT_APPLICABLE`

Os thresholds são decisões internas do SearchGEO e devem permanecer identificados como tal.

## 9. Proveniência por componente

A validade conceitual do SGRI depende da separação entre:

1. **observação** — o que foi medido/coletado;
2. **base externa** — standard, métrica ou orientação oficial que sustenta o fenômeno;
3. **interpretação SearchGEO** — como a observação é transformada em RuleResult;
4. **threshold** — quando aplicável, quem definiu o limite;
5. **agregação** — como RuleResults contribuem para dimensões e Overall.

Uma regra pode usar um fenômeno definido oficialmente e ainda possuir threshold ou agregação heurística SearchGEO.

Exemplo conceitual:

```text
Observação: redirect chain length
Base técnica: HTTP/RFC e documentação do crawler
Threshold de WARNING: SearchGEO
Impacto no índice: SearchGEO
```

Uma fonte oficial para o fenômeno não transforma automaticamente o threshold interno em standard externo.

## 10. Groundability

Groundability é tratado no `SGRI-001` como **conjunto de sinais**, não como subscore adicional.

São destacados:

- `ANSWERABILITY`
- `CITATION_READINESS`
- `EVIDENCE_TRUST`

A pergunta operacional é:

> O conteúdo observado apresenta informação que pode ser recuperada, compreendida, atribuída e utilizada como suporte para uma resposta sem exigir inferência excessiva?

Não é calculada uma média própria de Groundability nesta versão. Criar um novo número sem calibração aumentaria a camada heurística sem ganho metodológico comprovado.

## 11. YMYL e E-E-A-T

YMYL/E-E-A-T entram como **contexto de risco e rigor da análise**, não como score numérico oficial.

Quando o contexto editorial indica maior risco:

- suporte factual recebe maior atenção;
- autoria/responsabilidade pode se tornar mais relevante;
- freshness pode exigir interpretação mais rigorosa;
- afirmações materiais exigem maior rastreabilidade;
- recomendações de IA devem permanecer evidence-bound e sujeitas a revisão humana.

O SearchGEO não apresenta um “E-E-A-T Score” nem um “YMYL Score” como se fossem métricas oficiais do Google.

Fonte primária:

- Google Search Central — Creating helpful, reliable, people-first content.

## 12. Separação de métricas externas

As métricas abaixo **não entram automaticamente no SGRI-001**:

- Core Web Vitals;
- Lighthouse Performance;
- Lighthouse Accessibility;
- WCAG;
- Synthetic Navigation Apdex.

Elas podem ser usadas para diagnóstico e correlação, mas sua metodologia permanece própria.

No relatório:

```text
index.html            -> síntese executiva
searchgeo.html        -> SGRI-001
web-performance.html  -> CWV + Lighthouse Performance
accessibility.html    -> Lighthouse Accessibility + evidências WCAG automatizáveis
apdex.html            -> Synthetic Navigation Apdex
```

## 13. Dashboard executivo

O `index.html` mostra o resultado final disponível de cada indicador sem criar uma nova agregação transversal.

Quando há várias URLs/contextos, o dashboard deve preferir:

- quantidade de contextos válidos;
- faixa observada por dispositivo;
- status de aprovação por contexto quando a métrica externa define esse estado.

O dashboard deve evitar criar uma “média oficial do site” quando a fonte externa não define essa agregação.

Exemplo:

```text
Lighthouse Performance
Mobile 78–91/100 · Desktop 92–97/100
6 contextos válidos
```

é preferível a declarar arbitrariamente:

```text
Lighthouse do site = 89
```

## 14. Readiness versus AI Visibility observada

Readiness e resultado observado são fenômenos diferentes.

```text
Readiness
= o que o conteúdo está preparado para oferecer

Observed AI Visibility
= o que efetivamente ocorreu em uma engine/surface/query/período
```

O SGRI-001 não transforma readiness em probabilidade de citação.

Uma futura camada de AI Visibility deve persistir, no mínimo:

- engine/surface;
- query;
- timestamp/período;
- país/idioma quando relevante;
- URL citada;
- presença de citação;
- posição/proeminência quando observável;
- repetição/amostragem.

## 15. Caminho para calibração empírica

A evolução metodológica deve usar outcomes observáveis em vez de ajustar pesos manualmente.

Dataset conceitual:

```text
SearchGEO features
        ↓
queries / engines / múltiplas execuções
        ↓
resultado observado de citação/grounding
        ↓
dataset longitudinal
```

Depois podem ser estudados:

- correlação;
- estabilidade temporal;
- poder discriminativo;
- calibração;
- regressão logística regularizada ou outro modelo interpretável;
- sensibilidade por vertical/YMYL;
- generalização entre engines.

Somente após evidência suficiente deve ser avaliada uma versão empiricamente calibrada do índice.

## 16. Validação da IA semântica

Quando uma RuleExecution depende de avaliação semântica por LLM, o provider não deve ser tratado como verdade normativa.

A evolução prevista inclui um gold dataset humano com métricas como:

- Precision;
- Recall;
- F1;
- agreement entre avaliadores;
- Cohen's Kappa ou outra métrica adequada ao desenho do dataset.

A versão do classificador semântico deve ser rastreável junto ao provider/modelo e às evidências utilizadas.

## 17. Governança de versão

Alterações que exigem nova versão metodológica incluem:

- mudança de fórmula;
- mudança de peso;
- mudança de warning factor;
- inclusão de nova dimensão no Overall;
- inclusão de subscore agregado;
- alteração de thresholds de Confidence/Consolidation;
- calibração empírica que modifique coeficientes.

Mudanças somente de apresentação, textos explicativos ou organização de páginas não devem modificar resultados persistidos.

## 18. Estado de validação do SGRI-001

Classificação atual:

```text
Fundamentação conceitual: evidence-based
Reprodutibilidade: sim
Auditabilidade: sim
Validação externa do índice composto: não estabelecida
Calibração contra outcome real de AI visibility: não estabelecida
```

Essa limitação deve permanecer pública até existir evidência que permita uma afirmação mais forte.
