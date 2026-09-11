# Remediação por causa raiz e elemento

## 1. Objetivo

Elevar findings acionáveis de orientação genérica por regra para diagnóstico técnico por ocorrência, mantendo rastreabilidade até a evidência observada.

Quando tecnicamente possível, cada problema, alerta ou melhoria deve indicar:

- causa raiz evidence-bound;
- escopo afetado;
- página e dispositivo;
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

A remediação por causa raiz e elemento não pode criar falsa precisão.

Há três classes de localização:

1. `EXACT_ELEMENT` - o finding possui vínculo determinístico com um único `ElementObservation`;
2. `ELEMENT_SET_OR_CONTEXT` - a regra pertence a um conjunto de nós ou região de conteúdo; vários elementos ou um contêiner contextual podem ser mostrados sem afirmar que um único nó é a causa;
3. `RESOURCE_OR_DOCUMENT` - a causa pertence a HTTP, header, `robots.txt`, sitemap ou documento e não possui selector DOM aplicável.

Quando um selector não puder ser comprovado:

```text
Selector: NÃO DETERMINADO
```

A ausência de selector não impede a apresentação da causa raiz quando ela estiver sustentada por outra evidência.

## 3. RootCauseAnalysis

A projeção/persistência deve representar, conforme o contrato vigente, pelo menos:

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

A confiança diagnóstica desta camada classifica a precisão da localização/causa e **não participa do SARI-001 nem do SCORE-GEO-004**.

## 4. Elementos afetados

Um elemento afetado pode conter:

- `element_observation_id`;
- selector;
- tag;
- id/classes;
- `outer_html` limitado;
- trecho textual;
- bounding box;
- snapshot/dispositivo;
- `relation`: `EXACT`, `SET_MEMBER` ou `CONTEXT_REGION`.

### Exemplo de elemento único

Uma falha de `<title>` pode apontar para:

```text
selector: title
relation: EXACT
```

### Exemplo de propriedade do conjunto

A hierarquia de headings deve listar os headings observados relevantes. O relatório não escolhe arbitrariamente um único `h2` como culpado.

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

Para regras semânticas avaliadas por provider, a causa pode reutilizar `reasoning_summary` e `evidence_ids` validados, mas deve permanecer distinguível de observação determinística.

## 6. Mudança exata

A remediação deve distinguir:

- alvo técnico;
- elemento/estrutura esperada;
- localização;
- tipo de ação;
- instrução exata;
- exemplo seguro quando disponível;
- decisão humana obrigatória.

A remediação deve preferir alterar um elemento existente quando essa for a correção adequada e não sugerir duplicatas artificiais.

## 7. Superfícies de relatório

O contrato público atual é o mini-site estático em `report/`.

### `report/index.html`

É a visão executiva. Pode resumir contagens e principais oportunidades e encaminhar o usuário à remediação detalhada, mas não deve duplicar toda a evidência de causa raiz.

### `report/remediation.html`

É a superfície canônica de remediação. Cada grupo por problema continua agregado, mas deve possuir detalhamento por ocorrência/página, permitindo identificar:

- quais ocorrências têm a mesma causa;
- quais possuem elementos/selectors diferentes;
- quais são apenas contextuais/documentais;
- o que corrigir em cada ocorrência.

### `report/mobile.html` e `report/desktop.html`

Quando materializadas, as páginas por dispositivo podem expor findings e observações daquele contexto e encaminhar à remediação detalhada. Elas não substituem `report/remediation.html` como superfície central de ação.

`report.html` na raiz do workspace não é contrato público vigente e não deve ser documentado como destino final.

## 8. Regras globais e não DOM

HTTP, `robots.txt`, sitemap, headers e outros recursos globais devem ser diagnosticados sem selector artificial.

Exemplo:

```text
Escopo: DOMAIN_RESOURCE
Selector: NÃO APLICÁVEL
Recurso: /robots.txt
```

## 9. Invariantes

A remediação por causa raiz e elemento não altera:

- Business Rules;
- resultados de `RuleExecution`;
- severity;
- actionability;
- prioridade;
- pesos;
- Score;
- Coverage;
- Confidence de scoring;
- Consolidation;
- política de IA.

Causa raiz e localização são projeções adicionais do estado evidence-bound.

## 10. Aceite mínimo

1. finding de elemento único mostra selector e HTML observado quando persistidos;
2. finding sem elemento único não recebe selector fabricado;
3. hierarquia de headings pode listar múltiplos elementos;
4. regra semântica pode indicar `<main>` como região contextual sem chamá-lo de elemento defeituoso;
5. problema global não recebe selector DOM;
6. causa raiz apresenta observado versus esperado;
7. mudança exata deriva da recipe aplicável;
8. critérios de aceite e revalidação permanecem visíveis;
9. `report/remediation.html` apresenta diagnóstico por ocorrência e o restante do mini-site apenas projeta resumos/atalhos coerentes;
10. a suíte de regressão aplicável permanece verde.