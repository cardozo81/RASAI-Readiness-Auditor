# Precisão e consistência das recomendações - Remediation Precision + Report Consistency

**Status:** APPROVED EVOLUTION
**Baseline de entrada:** Remediação por causa raiz e elemento integrado em `main`
**Contratos preservados:** `SCORE-GEO-003`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`

## 1. Objetivo

Corrigir inconsistências observadas em smoke real após Remediação por causa raiz e elemento sem alterar Business Rules, RuleResult, severity, actionability, prioridade, Score, Coverage, Confidence ou Consolidation.

Precisão e consistência das recomendações torna a remediação mais precisa e reduz ambiguidade operacional entre:

- causa genérica da regra e motivo técnico efetivamente persistido;
- elemento observado e elemento/selector alvo da correção;
- finding, problema comprovado, revisão recomendada e melhoria opcional;
- tentativa de IA e análise externa efetivamente concluída;
- RuleExecution e Finding correspondente.

## 2. Projeção aditiva de precisão

Precisão e consistência das recomendações adiciona a tabela:

```text
root_cause_precision
```

Ela é derivada de `root_cause_analyses` + Evidence + RemediationRecipe e contém, por `finding_id`:

- `reason_code`;
- `precise_cause_summary`;
- `observed_element_status`;
- `observed_selector`;
- `target_selector`;
- `target_element`;
- `target_location`;
- timestamp de materialização.

A tabela Remediação por causa raiz e elemento não é reescrita destrutivamente.

## 3. Reason code antes do resumo genérico

Quando Evidence contém um motivo técnico específico, ele deve prevalecer sobre resumo genérico da família da regra.

Exemplo:

```text
reason = CANONICAL_ABSENT
observed.canonicals = []
```

Deve produzir causa semelhante a:

```text
Nenhuma declaração <link rel="canonical"> foi encontrada no documento avaliado.
```

Não deve ser reduzida a texto ambíguo como "ausente, conflitante ou inválida" quando a evidência já distingue o caso.

Quando não existir mapeamento humano específico para o reason code, o código persistido deve permanecer visível junto ao resumo evidence-backed; não deve ser descartado.

## 4. Elemento observado versus alvo técnico

Precisão e consistência das recomendações separa obrigatoriamente:

### Elemento observado

Estado permitido:

- `PRESENT`;
- `ABSENT`;
- `CONTEXT_ONLY`;
- `NOT_APPLICABLE`;
- `NOT_DETERMINED`.

O selector observado somente pode vir de `ElementObservation` persistido.

### Alvo técnico da correção

Pode ser derivado deterministicamente da RemediationRecipe/regra e deve ser identificado explicitamente como alvo, não como observação.

Exemplo para canonical ausente:

```text
Elemento observado: ABSENT
Selector observado: NÃO APLICÁVEL
Elemento alvo: <link rel="canonical">
Selector técnico alvo: head > link[rel="canonical"]
Local esperado: <head>
```

O auditor não deve alegar ter observado um nó inexistente.

## 5. Semântica de actionability

O relatório deve preservar a distinção:

- `REQUIRED_FIX` → AÇÃO NECESSÁRIA;
- `REVIEW_RECOMMENDED` → REVISÃO RECOMENDADA;
- `OPTIONAL_IMPROVEMENT` → MELHORIA OPCIONAL;
- `INSUFFICIENT_EVIDENCE` → AÇÃO NO SITE NÃO DETERMINADA;
- `NO_ACTION` → NENHUMA AÇÃO NECESSÁRIA.

O resumo não deve chamar todo Finding de "problema".

O plano priorizado deve combinar prioridade e actionability. Exemplo:

```text
REVISÃO RECOMENDADA · P1
```

`P1` ordena a revisão e não converte WARNING em FAIL nem revisão em ação obrigatória.

## 6. Uso de IA

O relatório deve distinguir:

1. provider não utilizado;
2. tentativa sem sucesso (`UNAVAILABLE`);
3. resultados externos válidos persistidos (`OPENAI`);
4. execução parcialmente disponível (`OPENAI` + `UNAVAILABLE`).

A presença da capability configurada não autoriza afirmar que análises externas foram concluídas.

## 7. Redução de duplicação

`report.html` deve manter:

- resumo;
- scores;
- página/device;
- finding;
- evidência observada;
- diagnóstico preciso de causa raiz;
- alvo técnico;
- link para remediação completa.

`remediation.html` deve concentrar:

- recipe comum do problema;
- páginas afetadas;
- ocorrências Desktop/Mobile;
- causa específica de cada ocorrência;
- elementos/selectors observados;
- alvo técnico;
- exemplo;
- decisão humana;
- aceite;
- revalidação.

O bloco legado "Correções técnicas detalhadas" em `report.html` passa a orientar o usuário para `remediation.html`, evitando repetir toda a recipe várias vezes.

## 8. Integridade RuleExecution → Finding

O relatório técnico deve verificar:

- toda RuleExecution `FAIL`/`WARNING` versus `findings.rule_execution_id`;
- todo Finding versus RuleExecution correspondente.

Divergências devem ser exibidas explicitamente com:

- tipo de inconsistência;
- rule_id;
- resultado;
- device;
- rule_execution_id.

Precisão e consistência das recomendações não cria Finding automaticamente para corrigir uma divergência, pois isso alteraria semântica de regra sem diagnóstico da origem.

## 9. Multi-URL

O gate de regressão deve incluir ao menos duas páginas do mesmo origin com o mesmo rule_id e comprovar que:

- existe um único grupo transversal;
- as duas páginas permanecem listadas;
- cada ocorrência possui diagnóstico técnico próprio;
- selectors/alvos de uma página não são atribuídos à outra.

## 10. Invariantes

Precisão e consistência das recomendações não altera:

- Business Rules;
- RuleResult;
- severity;
- actionability classifier;
- prioridade/priority score;
- SCORE-GEO-003;
- weights;
- Coverage;
- Confidence;
- Consolidation;
- política de crawler;
- política de IA.

## 11. Critérios de conclusão

1. `CANONICAL_ABSENT` gera causa específica;
2. elemento ausente não aparece como selector observado desconhecido quando o estado `ABSENT` é comprovável;
3. selector observado e selector alvo são campos semanticamente separados;
4. `UNAVAILABLE` não é descrito como análise externa concluída;
5. resumo separa findings de ações obrigatórias e revisões;
6. P1 de REVIEW permanece visualmente revisão;
7. `report.html` reduz repetição da recipe;
8. `remediation.html` preserva detalhamento completo por ocorrência;
9. inconsistência RuleExecution → Finding é explicitamente diagnosticada;
10. teste multi-URL comprova agrupamento e diagnósticos independentes;
11. suíte determinística permanece verde;
12. diff final não contém workflow temporário nem secrets.
