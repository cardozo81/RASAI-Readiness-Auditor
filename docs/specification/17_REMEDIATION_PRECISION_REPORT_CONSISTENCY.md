# Precisão e consistência das recomendações

## 1. Objetivo

Garantir que a remediação seja tecnicamente precisa e semanticamente coerente sem alterar Business Rules, `RuleResult`, severity, actionability, prioridade, Score, Coverage, Confidence ou Consolidation.

A camada deve reduzir ambiguidades entre:

- causa genérica da regra e motivo técnico efetivamente persistido;
- elemento observado e elemento/selector alvo da correção;
- finding, problema comprovado, revisão recomendada e melhoria opcional;
- tentativa de IA e análise externa efetivamente concluída;
- `RuleExecution` e Finding correspondente.

## 2. Projeção aditiva de precisão

A persistência aditiva usa:

```text
root_cause_precision
```

Ela é derivada de `root_cause_analyses`, Evidence e `RemediationRecipe` e contém, por `finding_id`, os dados necessários para a projeção vigente, incluindo:

- `reason_code`;
- `precise_cause_summary`;
- `observed_element_status`;
- `observed_selector`;
- `target_selector`;
- `target_element`;
- `target_location`;
- timestamp de materialização.

A tabela de causa raiz não deve ser reescrita destrutivamente para produzir essa projeção.

## 3. Reason code antes do resumo genérico

Quando Evidence contém um motivo técnico específico, ele deve prevalecer sobre resumo genérico da família da regra.

Exemplo:

```text
reason = CANONICAL_ABSENT
observed.canonicals = []
```

A apresentação deve indicar que nenhuma declaração canonical foi observada, em vez de reduzir o caso a texto ambíguo como “ausente, conflitante ou inválida” quando a evidência já distingue o motivo.

Quando não existir mapeamento humano específico para o reason code, o código persistido deve permanecer visível junto ao resumo evidence-bound; não deve ser descartado.

## 4. Elemento observado versus alvo técnico

### Elemento observado

Estados permitidos:

```text
PRESENT
ABSENT
CONTEXT_ONLY
NOT_APPLICABLE
NOT_DETERMINED
```

O selector observado somente pode vir de `ElementObservation` persistido.

### Alvo técnico da correção

Pode ser derivado deterministicamente de `RemediationRecipe`/regra e deve ser identificado explicitamente como alvo, não como observação.

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

A projeção deve preservar:

| Valor técnico | Rótulo pt-BR |
|---|---|
| `REQUIRED_FIX` | AÇÃO NECESSÁRIA |
| `REVIEW_RECOMMENDED` | REVISÃO RECOMENDADA |
| `OPTIONAL_IMPROVEMENT` | MELHORIA OPCIONAL |
| `INSUFFICIENT_EVIDENCE` | AÇÃO NO SITE NÃO DETERMINADA |
| `NO_ACTION` | NENHUMA AÇÃO NECESSÁRIA |

O resumo não deve chamar todo Finding de “problema”.

Priority e actionability são conceitos separados. `P1` ordena uma revisão; não converte `WARNING` em `FAIL` nem uma revisão em ação obrigatória.

## 6. Uso de IA

O relatório deve distinguir:

1. provider não utilizado;
2. tentativa sem sucesso (`UNAVAILABLE`);
3. resultado externo válido persistido;
4. execução parcialmente disponível.

A existência de capability configurada não autoriza afirmar que análises externas foram concluídas.

## 7. Distribuição das informações no mini-site

### `report/index.html`

Mantém visão executiva, scores e atalhos para as áreas especializadas. Não deve repetir recipes completas por ocorrência.

### `report/mobile.html` / `report/desktop.html`

Quando materializadas, mostram estado por dispositivo, páginas e findings daquele contexto e podem encaminhar à remediação detalhada.

### `report/remediation.html`

Concentra:

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

`report.html` na raiz do workspace **não é superfície pública vigente** e não deve ser usado como contrato final.

## 8. Integridade RuleExecution → Finding

A projeção técnica deve verificar:

- toda `RuleExecution` `FAIL`/`WARNING` versus `findings.rule_execution_id` quando a política da regra exige Finding;
- todo Finding versus `RuleExecution` correspondente.

Divergências devem expor:

- tipo de inconsistência;
- `rule_id`;
- resultado;
- device;
- `rule_execution_id`.

A camada não cria Finding automaticamente apenas para mascarar uma divergência de persistência/contrato.

## 9. Multi-URL

A regressão deve cobrir ao menos duas páginas do mesmo origin com o mesmo `rule_id` e comprovar que:

- existe um único grupo transversal quando a causa é compartilhada;
- as páginas permanecem listadas individualmente;
- cada ocorrência possui diagnóstico técnico próprio;
- selectors/alvos de uma página não são atribuídos à outra.

## 10. Invariantes

A precisão de remediação não altera:

- Business Rules;
- `RuleResult`;
- severity;
- actionability classifier;
- prioridade/priority score;
- weights;
- Coverage;
- Confidence;
- Consolidation;
- política de crawler;
- política de IA.

## 11. Critérios de conclusão

1. `CANONICAL_ABSENT` gera causa específica;
2. elemento ausente não recebe selector observado inventado;
3. selector observado e selector alvo são semanticamente separados;
4. `UNAVAILABLE` não é descrito como análise externa concluída;
5. resumo separa findings, ações obrigatórias e revisões;
6. P1 de `REVIEW_RECOMMENDED` continua visualmente revisão;
7. `report/index.html` não duplica recipe detalhada;
8. `report/remediation.html` preserva detalhamento por ocorrência;
9. inconsistência RuleExecution → Finding é diagnosticada explicitamente;
10. teste multi-URL comprova agrupamento e diagnósticos independentes;
11. suíte determinística aplicável permanece verde;
12. documentação e artefatos não contêm secrets nem contratos históricos de workflow/branch.