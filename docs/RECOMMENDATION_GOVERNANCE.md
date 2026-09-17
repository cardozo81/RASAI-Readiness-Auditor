# Governança de Recomendações do CAT-09

## Objetivo

O `CAT-09 · Remediações` é a superfície responsável por transformar findings/evidências dos demais catálogos em ações possíveis. Ele não pode tratar toda saída de IA ou todo diagnóstico técnico como ação do cliente.

O contrato `RECOMMENDATION-GOVERNANCE-001` classifica e valida cada candidato antes de apresentá-lo no plano governado.

## Classes de alvo

Cada recomendação recebe uma classe explícita:

- `TARGET_SITE` — alteração no site/propriedade auditada;
- `AUDITOR_INTERNAL` — problema ou ajuste interno do RASAi/auditor;
- `EXTERNAL_PROVIDER` — ação em fornecedor/CDN/dependência de terceiro;
- `ENVIRONMENTAL` — ação em ambiente/infraestrutura fora do ativo auditado;
- `INFORMATIONAL` — orientação sem ownership seguro ou sem obrigação de implementação.

A classe descreve **quem é o alvo da ação**, não o catálogo de origem.

## Decisão

Estados persistidos:

- `ACCEPTED` — pode entrar no plano governado;
- `REJECTED` — permanece auditável, mas não entra no plano do cliente.

Campos de governança persistidos em `recommendation_governance` incluem:

- origem e identificador da recomendação;
- catálogo/fonte;
- classe de alvo;
- decisão;
- `rejection_reason`;
- `conflict_group`;
- evidências de origem;
- racional da decisão;
- versão do contrato.

## Regras obrigatórias

### Problemas internos do auditor

Ação cujo alvo é `AUDITOR_INTERNAL` é excluída do plano do cliente. Ela pode permanecer visível em área técnica/auditável.

### Third-party

Remediação derivada de erro de requisição `THIRD_PARTY` é classificada como `EXTERNAL_PROVIDER`, não como alteração automática do site.

Remediação `FIRST_PARTY` é classificada como `TARGET_SITE`.

Quando ownership não puder ser determinado com segurança, a orientação fica `INFORMATIONAL`.

### Coerência com evidência de JSON-LD

Uma recomendação não pode presumir que existe JSON-LD quando a evidência persistida registra ausência.

Exemplo inválido:

```text
existing_types = []
recomendação = "Corrigir JSON-LD existente"
```

Resultado:

```text
REJECTED
rejection_reason = JSONLD_ABSENT_EXISTING_CONFLICT
conflict_group = JSONLD_EXISTENCE
```

Quando o JSON-LD está ausente, uma recomendação de criação pode ser aceita se houver payload/ação de criação coerente com a evidência.

## Relação com IA

A decisão de governança é determinística. IA pode produzir sugestão de remediação, mas não decide se a própria sugestão é coerente com os fatos persistidos nem se deve entrar no plano do cliente.

A governança não altera SARI/SCORE-GEO.

## Relatório

O CAT-09 separa:

1. **Plano de ação aceito** — somente recomendações `ACCEPTED`;
2. **Itens rejeitados ou informativos** — auditáveis, fora do plano;
3. **Inventário técnico de origem** — trilha bruta preservada para rastreabilidade, explicitamente não apresentada como plano governado.

A governança é materializada antes do fingerprint e do snapshot final de `report-catalog`, portanto o pacote entregue contém as mesmas decisões exibidas.

## Fontes atualmente governadas

- recomendações determinísticas;
- sugestões de conteúdo assistidas por IA;
- sugestões de JSON-LD;
- recomendações da análise profunda/CAT-08;
- remediações agrupadas de requisições/runtime CAT-06/CAT-07.

Orientações técnicas meramente informativas continuam podendo existir na trilha técnica sem serem promovidas automaticamente a obrigação do cliente.
