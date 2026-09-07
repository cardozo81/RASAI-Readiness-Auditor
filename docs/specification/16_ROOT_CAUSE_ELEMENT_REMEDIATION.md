# Remediação por causa raiz e elemento - Root Cause + Element-Level Remediation

**Status:** APPROVED EVOLUTION
**Baseline de entrada:** Experiência e organização dos relatórios + OpenAI provider hardening integrado em `main`
**Contratos preservados:** `SCORE-GEO-003`, `REPORT-GEO-003`, `REMEDIATION-GEO-001`

## 1. Objetivo

Elevar findings acionáveis de orientação genérica por regra para diagnóstico técnico por ocorrência, mantendo rastreabilidade até a evidência observada.

Quando tecnicamente possível, cada problema, alerta ou melhoria deve indicar:

- causa raiz evidence-backed;
- escopo afetado;
- página e device;
- elemento(s) HTML relacionado(s);
- selector observado quando determinável;
- HTML observado quando persistido;
- valor observado versus condição esperada;
- mudança exata recomendada;
- exemplo pós-correção quando seguro;
- critérios de aceite;
- passos de revalidação;
- decisão humana necessária quando aplicável.

## 2. Princípio de precisão

Remediação por causa raiz e elemento não pode criar falsa precisão.

Há três classes de localização:

1. `EXACT_ELEMENT` - finding possui vínculo determinístico com um único `ElementObservation`;
2. `ELEMENT_SET_OR_CONTEXT` - regra pertence a conjunto de nós ou região de conteúdo; vários elementos/um contêiner contextual podem ser mostrados sem afirmar que um único nó é a causa;
3. `RESOURCE_OR_DOCUMENT` - causa pertence a HTTP, header, robots.txt, sitemap ou documento e não possui selector DOM aplicável.

Quando um selector não puder ser provado:

```text
Selector: NÃO DETERMINADO
```

A ausência de selector não impede a apresentação da causa raiz quando a causa está sustentada por outra evidência.

## 3. RootCauseAnalysis

A projeção/persistência Remediação por causa raiz e elemento deve representar pelo menos:

- `analysis_id`;
- `audit_id`;
- `finding_id`;
- `rule_id`;
- `cause_type`;
- `affected_scope`;
- `cause_summary`;
- `evidence_basis`;
- `affected_elements`;
- `selector_status`;
- `observed_value`;
- `expected_condition`;
- `exact_change`;
- `example_after`;
- `acceptance_criteria`;
- `revalidation_steps`;
- `human_decision_required`;
- `diagnostic_confidence`;
- timestamp de materialização.

A confiança diagnóstica Remediação por causa raiz e elemento é uma classificação da precisão da localização/causa e **não participa do Score GEO**.

## 4. Elementos afetados

Um elemento afetado pode conter:

- `element_observation_id`;
- selector;
- tag;
- id/classes;
- `outer_html` bounded;
- text excerpt;
- bounding box;
- snapshot/device;
- `relation`: `EXACT`, `SET_MEMBER` ou `CONTEXT_REGION`.

### Exemplo de elemento único

Uma falha de `<title>` pode apontar para:

```text
selector: title
relation: EXACT
```

### Exemplo de propriedade do conjunto

Hierarquia de headings deve listar os headings observados relevantes. O relatório não escolhe arbitrariamente um único `h2` como culpado.

### Exemplo de região contextual

Regras de answerability/intenção podem apontar `<main>` como região onde o conteúdo foi avaliado, com `relation=CONTEXT_REGION`. Isso não significa que o próprio elemento `<main>` seja tecnicamente defeituoso.

## 5. Causa raiz

A causa raiz deve ser derivada de:

```text
RuleExecution.observed_value
+ Finding
+ Evidence
+ ElementObservation(s)
+ condição esperada da Business Rule
+ RemediationRecipe
```

A IA não pode inventar selector, HTML observado ou causa técnica sem evidência persistida.

Para regras semânticas avaliadas por provider, a causa pode reutilizar `reasoning_summary` e evidence IDs validados, mas deve permanecer distinguível de observação determinística.

## 6. Mudança exata

A remediação deve distinguir:

- alvo técnico;
- elemento/estrutura esperada;
- localização;
- tipo de ação;
- instrução exata;
- exemplo seguro quando disponível;
- decisão humana obrigatória.

Remediação por causa raiz e elemento deve preferir alterar um elemento existente quando essa é a correção adequada e não sugerir criar duplicatas artificiais.

## 7. Relatórios

### `report.html`

Na seção de cada finding, Remediação por causa raiz e elemento acrescenta bloco **Diagnóstico de causa raiz** antes da recomendação, contendo os elementos e a mudança exata.

### `remediation.html`

Cada grupo por problema continua agregado, mas deve possuir detalhamento por ocorrência/página, permitindo identificar:

- quais ocorrências têm a mesma causa;
- quais possuem elementos/selectors diferentes;
- quais são apenas contextuais/documentais;
- o que corrigir em cada ocorrência.

## 8. Regras globais e não DOM

HTTP, robots.txt, sitemap, headers e outros recursos globais devem ser diagnosticados sem selector artificial.

Exemplo:

```text
Escopo: DOMAIN_RESOURCE
Selector: NÃO APLICÁVEL
Recurso: /robots.txt
```

## 9. Invariantes

Remediação por causa raiz e elemento não altera:

- Business Rules;
- resultados de RuleExecution;
- severity;
- actionability;
- prioridade;
- weights;
- Score;
- Coverage;
- Confidence de scoring;
- Consolidation;
- política de IA.

Root cause e localização são projeções adicionais do estado evidence-backed.

## 10. Aceite mínimo

1. finding de elemento único mostra selector e HTML observado quando persistidos;
2. finding sem elemento único não recebe selector fabricado;
3. hierarquia de headings pode listar múltiplos elementos;
4. regra semântica pode indicar `<main>` como região contextual sem chamá-lo de elemento defeituoso;
5. problema global não recebe selector DOM;
6. causa raiz apresenta observado versus esperado;
7. mudança exata deriva da recipe aplicável;
8. critérios de aceite e revalidação permanecem visíveis;
9. `report.html` e `remediation.html` exibem diagnóstico por ocorrência;
10. suíte de regressão permanece verde.
