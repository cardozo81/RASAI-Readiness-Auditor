# ROOT_CAUSE_REMEDIATION_GUIDE.md

## Objetivo

Remediação por causa raiz e elemento/Precisão e consistência das recomendações transformam um finding evidence-backed em diagnóstico acionável sem alterar o resultado original da regra.

A projeção final fica em:

```text
report/remediation.html
```

## Separação de conceitos

- **finding:** problema/alerta comprovado pela RuleExecution;
- **root cause:** causa técnica materializada sobre as evidências existentes;
- **precision:** reason code, elemento observado e alvo técnico preciso;
- **recommendation:** ação priorizada;
- **actionability:** se a evidência justifica ação, revisão, melhoria opcional ou nenhuma ação.

Nenhum desses conceitos deve ser derivado apenas de `Confidence LOW` do score.

## Dados Remediação por causa raiz e elemento

`root_cause_analyses` registra, conforme disponível:

- `finding_id`;
- `rule_id`;
- `cause_type`;
- `affected_scope`;
- `cause_summary`;
- `evidence_basis`;
- elementos afetados;
- selector status;
- observed value;
- expected condition;
- exact change;
- example after;
- acceptance criteria;
- revalidation steps;
- human decision required;
- diagnostic confidence.

## Dados Precisão e consistência das recomendações

`root_cause_precision` complementa sem reescrever Remediação por causa raiz e elemento:

- `reason_code`;
- `precise_cause_summary`;
- `observed_element_status`;
- `observed_selector`;
- `target_selector`;
- `target_element`;
- `target_location`.

## Elemento observado × alvo técnico

Não confundir:

- **selector observado:** nó que realmente foi encontrado na evidência;
- **target selector:** local/estrutura onde a correção deve ocorrer.

Quando o problema é ausência de um elemento, pode não existir selector observado, mas pode existir alvo técnico recomendado.

## `report/remediation.html`

A página final agrupa remediation groups e permite abrir cada ocorrência. Quando a materialização existe, mostra:

- causa precisa;
- reason code;
- escopo;
- selector observado;
- alvo técnico;
- local esperado;
- precisão diagnóstica;
- mudança recomendada;
- observado versus esperado;
- exemplo pós-correção;
- decisão humana;
- critérios de aceite;
- passos de revalidação.

## UNKNOWN / evidência insuficiente

`UNKNOWN` ou `ERROR` não devem gerar correção fictícia.

Actionability pode ficar:

```text
INSUFFICIENT_EVIDENCE
```

Nesse caso a ação correta é melhorar a capacidade de diagnóstico, não inventar mudança no website.

## Conteúdo semântico

Quando uma regra semântica específica sustenta um finding, a remediação pode orientar clareza, contexto, atribuição, resposta à intenção etc.

Isso não autoriza concluir que todo `Confidence LOW` requer reescrita. Confidence é reliability do auditor.

Uma futura etapa opcional por IA poderá propor texto/local de inserção com base em findings e evidências, mas deve permanecer separada do scoring e desligada por padrão.

## Fonte de verdade

A página HTML não recalcula a causa. Ela projeta:

```text
audit.db
└─ findings / root_cause_analyses / root_cause_precision / recommendations
```
