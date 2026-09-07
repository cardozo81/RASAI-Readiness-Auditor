# SCORING_MODEL.md

**Status:** APPROVED
**Scoring baseline:** SCORE-GEO-002

## 0. Natureza metodológica e validade

`SCORE-GEO-002` é um **índice proprietário e interno do SearchGEO Readiness Auditor**.

O status `APPROVED` deste documento significa **aprovado como baseline normativo interno do projeto**. Não significa homologação, certificação, padronização ou validação por Google, OpenAI, Microsoft, Anthropic, NIST, W3C, schema.org ou qualquer outro mantenedor externo.

As dimensões e regras do modelo são informadas por documentação pública de mecanismos de busca e IA, literatura técnica, práticas de Information Retrieval, SEO/GEO e requisitos observáveis dos produtos avaliados. Entretanto, na versão `SCORE-GEO-002`:

- a fórmula de agregação é uma decisão metodológica interna;
- os pesos entre dimensões são internos;
- os fatores `PASS = 1.00`, `WARNING = 0.50` e `FAIL = 0.00` são heurísticos;
- os thresholds de Coverage, Confidence e Consolidation são internos;
- as faixas visuais 90/75/60/40 são internas;
- o Overall Readiness 0–100 não deve ser apresentado como probabilidade de citação, ranking, tráfego, conversão ou inclusão em resposta generativa;
- não existe, nesta versão, calibração estatística própria que demonstre que determinado Score corresponde a determinada probabilidade de presença/citação em mecanismos generativos.

Portanto, o modelo deve ser descrito como **heurístico, determinístico, evidence-backed e reprodutível**, mas **não como score científico, padrão oficial de GEO/AEO ou índice externamente homologado**.

Uma versão futura somente poderá ser descrita como `empiricamente calibrada` quando seus pesos, fatores e/ou thresholds forem derivados ou validados contra um conjunto observacional suficientemente representativo, com metodologia, amostra, métricas de validação, incerteza e limitações documentadas.

Referências externas e alternativas de validação estão documentadas em `docs/SCORING_VALIDATION.md`.

## 1. Estrutura

Todo resultado de score possui:

- Value;
- Coverage;
- Confidence;
- Consolidation Status;
- Contributions;
- Limitations;
- Scoring Version.

## 2. Dimensões

1. Acessibilidade Técnica
2. Capacidade de Indexação
3. Extração de Conteúdo
4. Estrutura Semântica
5. Clareza de Entidades
6. Dados Estruturados
7. Capacidade de Resposta
8. Preparação para Citação
9. Evidências e Confiabilidade
10. Cobertura de Intenções

Desktop e Mobile permanecem separados no modelo. O contexto de execução pode selecionar `mobile`, `desktop` ou `both`; um dispositivo não auditado não deve ser apresentado como resultado válido no report site.

As dez dimensões continuam pertencendo ao modelo. `SCORE-GEO-002` distingue dimensão legitimamente não aplicável de dimensão que deveria ser avaliada mas não consolidou.

## 3. RuleExecution

PASS = avaliado positivamente
WARNING = avaliado com perda parcial
FAIL = problema comprovado
UNKNOWN = insuficiente para concluir
ERROR = auditor não conseguiu executar
NOT_APPLICABLE = regra fora do universo aplicável

UNKNOWN, ERROR e NOT_APPLICABLE não são FAIL.

## 4. Fatores

Baseline:

PASS = 1.00
WARNING = 0.50 por padrão
FAIL = 0.00

warning_factor pode ser sobrescrito por regra e é versionado.

Os fatores acima são parâmetros heurísticos do baseline interno, não coeficientes externamente calibrados.

## 5. Fórmula

Dimension Score:

Σ(weight × result_factor)
/
Σ(weight evaluated)
× 100

Apenas PASS, WARNING e FAIL participam do denominador do score.

A forma matemática de média ponderada normalizada é convencional; a seleção das variáveis, dos pesos e dos fatores é específica do SearchGEO.

## 6. Coverage

Coverage:

evaluated applicable weight
/
total applicable weight

Evaluated:

- PASS
- WARNING
- FAIL

Applicable:

- PASS
- WARNING
- FAIL
- UNKNOWN
- ERROR

NOT_APPLICABLE fica fora.

Coverage baixa significa baixa completude da análise, não baixa qualidade atribuída ao website.

## 7. Aplicabilidade da dimensão

`SCORE-GEO-002` adiciona distinção explícita entre aplicabilidade e consolidação.

### 7.1 Sem RuleExecution

Se nenhuma RuleExecution da dimensão existir para o dispositivo:

- Value = null;
- Coverage = 0;
- Confidence = UNAVAILABLE;
- Consolidation = NOT_CONSOLIDATED;
- limitation = `NO_RULE_EXECUTIONS`.

Ausência de execução não pode ser convertida em `NOT_APPLICABLE`.

### 7.2 Todas as regras legitimamente NOT_APPLICABLE

Se RuleExecutions existem e todas as regras da dimensão estão legitimamente fora do universo aplicável:

- Value = null;
- Coverage = 0 na dimensão isolada;
- Confidence = UNAVAILABLE;
- Consolidation = NOT_APPLICABLE;
- limitation = `NO_APPLICABLE_RULES`.

A dimensão não recebe 0 nem 100 e é excluída da agregação Overall.

### 7.3 Pré-requisito bloqueado

Se `NOT_APPLICABLE` ocorreu porque um pré-requisito impediu a análise, isso não é não aplicabilidade benigna.

Reason codes contendo `PREREQUISITE_BLOCKED` mantêm a dimensão:

- Value = null;
- Consolidation = NOT_CONSOLIDATED;
- limitation = `APPLICABILITY_UNRESOLVED:PREREQUISITE_BLOCKED`.

## 8. Confidence

Níveis:

- HIGH
- MEDIUM
- LOW
- UNAVAILABLE

Confidence responde **quão forte é a conclusão do auditor**, considerando cobertura, evidência e confiabilidade da execução. Ela não responde diretamente se o texto do website é “bom”, “ruim” ou “aderente a GEO”.

Baseline algorítmica atual:

- HIGH: Coverage >= 90%, evidência completa e zero errors;
- MEDIUM: Coverage >= 80% e zero errors;
- LOW: Coverage > 0 sem atender HIGH/MEDIUM;
- UNAVAILABLE: Coverage <= 0.

Os thresholds 90%/80% são parâmetros internos do `SCORE-GEO-002`; não representam thresholds oficiais de GEO/AEO definidos por mantenedor externo.

`Confidence LOW` isoladamente **não pode gerar finding, recomendação nem ordem de reescrita de conteúdo**. Uma ação sobre conteúdo exige RuleExecution/finding evidence-backed que sustente a alteração.

Confidence do LLM em uma SemanticAssessment não é automaticamente a Confidence final do auditor.

## 9. Consolidation

Baseline para dimensões aplicáveis:

Coverage >= 80% e Confidence HIGH/MEDIUM
→ CONSOLIDATED

Coverage 50–79%
→ PARTIAL quando existe avaliação suficiente para esse estado

Coverage >= 80% mas Confidence LOW
→ PARTIAL ou NOT_CONSOLIDATED conforme regra de consolidação vigente

Coverage < 50%
→ NOT_CONSOLIDATED

Confidence UNAVAILABLE
→ NOT_CONSOLIDATED

Dimensão integralmente não aplicável:

→ NOT_APPLICABLE

Os limites de consolidação constituem governança interna do auditor e devem permanecer versionados.

## 10. Sem IA

Ausência de IA:

- reduz coverage quando regras semantic-only ficam sem base;
- pode reduzir confidence/consolidation;
- não reduz qualidade atribuída ao website;
- não transforma regra semantic-only em FAIL.

## 11. ScoreContribution

Toda contribuição registra:

- score_id;
- rule_id;
- rule_execution_id;
- dimension;
- device;
- weight;
- result;
- factor;
- effective contribution;
- scoring_group.

## 12. Double Counting

Regras correlacionadas utilizam `scoring_group`.

Baseline para regras correlacionadas:

MAX_IMPACT

## 13. Cascading Failures

Falha de pré-requisito não pode multiplicar penalizações e não pode remover artificialmente uma dimensão do universo aplicável.

## 14. Site-level rules

Regras globais como robots/sitemap não devem ser replicadas artificialmente por página.

## 15. Aggregation

No MVP:

- páginas possuem peso equivalente;
- não existe page importance subjetiva.

## 16. Overall

Existem conceitualmente:

- Overall Readiness — Desktop
- Overall Readiness — Mobile

Nunca uma única nota misturando dispositivos.

Overall exige materialização das dez dimensões e consolidação suficiente de todas as dimensões aplicáveis do respectivo dispositivo.

Fluxo:

1. materializar as dez dimensões;
2. excluir da agregação apenas dimensões `NOT_APPLICABLE` legítimas;
3. exigir Value e estado diferente de `NOT_CONSOLIDATED` para todas as dimensões restantes;
4. calcular média simples dos Values aplicáveis;
5. calcular Overall Coverage pela média das coverages aplicáveis;
6. persistir `DIMENSION_NOT_APPLICABLE:<DIMENSION>` para cada dimensão excluída.

Se uma dimensão aplicável necessária estiver NOT_CONSOLIDATED:

Overall = NOT_CONSOLIDATED

Uma dimensão `NOT_APPLICABLE` não reduz nota nem Coverage do Overall.

O report site só apresenta o Overall de um dispositivo como resultado de auditoria quando esse dispositivo possui snapshot no universo efetivamente executado.

## 17. JSON-LD / Structured Data

JSON-LD não é requisito universal para Compatibilidade GEO calculável.

Quando Structured Data está ausente e `BR-GEO-034..037` são legitimamente `NOT_APPLICABLE`:

- `STRUCTURED_DATA = NOT_APPLICABLE`;
- a dimensão não participa do Overall;
- não há penalidade pela ausência isolada.

Quando Structured Data é observado:

- a dimensão torna-se aplicável;
- BR-GEO-034..037 entram normalmente no fluxo;
- PASS/WARNING/FAIL influenciam score;
- UNKNOWN/ERROR influenciam coverage/consolidation;
- markup inválido ou contraditório pode reduzir o Overall.

## 18. Technical Readiness

Pode resumir:

- Technical Accessibility;
- Indexability;
- Content Extractability;
- Structured Data quando aplicável.

Somente se suficientemente consolidadas.

## 19. Semantic Readiness

Pode resumir:

- Semantic Structure;
- Entity Clarity;
- Answerability;
- Citation Readiness;
- Evidence & Trust;
- Intent Coverage.

## 20. Pesos entre dimensões

MVP:

equal weight entre dimensões aplicáveis.

Pesos iguais são uma decisão de neutralidade do MVP, não resultado de calibração externa. Não atribuir pesos “científicos” antes de calibração empírica documentada.

## 21. Blockers

Critical blockers são mostrados separadamente.

Um score relativamente alto não pode esconder um blocker crítico.

## 22. Classificação visual

As faixas 90/75/60/40 usadas pela UI são **classificação interna de apresentação** do SearchGEO. Não constituem threshold oficial de GEO/AEO de qualquer mantenedor externo e não devem ser convertidas em alegações de probabilidade de citação ou ranking.

## 23. Reprodutibilidade

Dadas:

- evidências;
- RuleExecutions;
- rule versions;
- scoring version;

o score e a decisão de aplicabilidade devem poder ser recalculados sem reexecutar website ou IA.

`BR-GEO-054` deve registrar `SCORE-GEO-002`.

## 24. Evidência externa e calibração futura

O SearchGEO deve diferenciar explicitamente três níveis de evidência:

1. **Requisito/sinal externo oficial** — regra diretamente sustentada por documentação do mantenedor, por exemplo requisitos técnicos de elegibilidade do Google Search ou controles de crawler documentados.
2. **Métrica externa calibrada/padronizada** — métrica cuja metodologia e referência quantitativa são externas, por exemplo Core Web Vitals, scoring de performance do Lighthouse ou métricas de Information Retrieval utilizadas por NIST/TREC.
3. **Heurística SearchGEO** — agregação, peso ou threshold criado pelo produto e ainda não calibrado contra outcome externo.

Métricas externas podem substituir ou complementar regras específicas quando medirem o mesmo fenômeno, mas não devem ser apresentadas como validação do Overall Readiness inteiro.

Qualquer evolução para `SCORE-GEO-003` que altere pesos/fatores/thresholds com base empírica deve documentar, no mínimo:

- outcome alvo, por exemplo presença, citação, posição/proeminência ou suporte factual;
- engines e superfícies avaliadas;
- conjunto de queries e critérios de amostragem;
- repetições temporais e tratamento da variabilidade estocástica;
- conjunto de treino/calibração separado do conjunto de validação;
- métricas estatísticas e intervalos de confiança;
- análise por domínio e por tipo de intenção;
- prevenção de leakage e overfitting;
- versão das engines/modelos e período de coleta;
- limitações de generalização.

Até essa calibração existir, `SCORE-GEO-002` permanece um índice interno de prontidão e não um estimador probabilístico de performance GEO observada.
