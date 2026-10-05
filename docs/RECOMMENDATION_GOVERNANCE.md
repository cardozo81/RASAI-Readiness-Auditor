# Governança de Recomendações do CAT-09

## Objetivo

O `CAT-09 · Remediações` é a superfície responsável por transformar findings/evidências dos demais catálogos em ações possíveis. Ele não pode tratar toda saída de IA ou todo diagnóstico técnico como ação do cliente.

O contrato `RECOMMENDATION-GOVERNANCE-003` classifica e valida cada candidato antes de apresentá-lo no plano governado.

## Classes de alvo

Cada recomendação recebe uma classe explícita:

- `TARGET_SITE` - alteração no site/propriedade auditada;
- `AUDITOR_INTERNAL` - problema ou ajuste interno do RASAi/auditor;
- `EXTERNAL_PROVIDER` - ação em fornecedor/CDN/dependência de terceiro;
- `ENVIRONMENTAL` - ação em ambiente/infraestrutura fora do ativo auditado;
- `INFORMATIONAL` - orientação sem ownership seguro ou sem obrigação de implementação.

A classe descreve **quem é o alvo da ação**, não o catálogo de origem.

## Decisão

Estados persistidos:

- `ACCEPTED` - a ação está sustentada pela evidência e pode entrar no plano governado;
- `VERIFY_DECIDE` - o problema/estado pode estar comprovado, mas falta uma decisão externa ou fato suficiente para prescrever a implementação; fica fora do plano direto até confirmação;
- `REJECTED` - permanece auditável, mas não entra no plano do cliente.

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

Recomendação do CAT-08 que deriva de finding com target determinístico de CAT-10 reutiliza `target.owner_class` quando esse campo foi persistido pela análise determinística. A governança não reinfere ownership por texto da IA. `EXTERNAL_PROVIDER` continua externo; `INFORMATIONAL` e `AUDITOR_INTERNAL` não são promovidos ao plano aceito.

Remediação `FIRST_PARTY` é classificada como `TARGET_SITE`.

Quando ownership não puder ser determinado com segurança, a orientação fica `INFORMATIONAL`.

### Estados neutros de discovery

Ausência válida ou avaliação explicitamente neutra de recursos de discovery não é promovida automaticamente a ação do cliente. O contrato mantém o item auditável como `INFORMATIONAL / REJECTED` quando a evidência persistida demonstra:

- `BR-GEO-003`: sitemap convencional ausente, sem erro material no recurso observado;
- `BR-GEO-017`: `robots.txt` ausente, quando a própria regra registra que ausência não é falha de crawling;
- `BR-GEO-055` e `BR-GEO-056`: avaliação técnica assistida por IA com `ai_verdict=NEUTRAL`.

Estados inválidos, erros ou evidência material de defeito continuam elegíveis ao plano de ação. A regra de governança não altera findings nem scoring; apenas evita transformar uma evidência neutra em obrigação de correção.

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

Quando o JSON-LD está ausente, um baseline `WebPage` só pode ser aceito quando os campos derivam de evidência persistida. Tipos específicos, entidades ou propriedades adicionais ficam em `VERIFY_DECIDE` quando conteúdo/entidade correspondente não estiver comprovado. JSON-LD não substitui conteúdo ausente e não autoriza inventar fatos.

### Decisões evidence-bound

Canonical, redirect e indexabilidade seguem a mesma regra: o diagnóstico técnico não prova automaticamente a decisão de negócio.

- canonical ausente não autoriza escolher uma URL preferencial; sem `preferred_url`/decisão equivalente persistida, a ação fica `VERIFY_DECIDE`;
- um destino de redirect só pode ser prescrito quando o destino estiver comprovado na evidência; reduzir uma cadeia excessiva pode continuar sendo orientação técnica sem inventar destino;
- `noindex` observado não autoriza removê-lo: a intenção de indexabilidade precisa estar persistida antes de uma ação prescritiva;
- quando uma prescrição diverge de um destino/intenção comprovado, ela é retida como `VERIFY_DECIDE` e o conflito é explicitado.

Essas decisões não alteram finding, RuleResult, score nem a resposta bruta de IA. Controlam somente a promoção da recomendação ao plano governado.

## Relação com IA

A decisão de governança é determinística. IA pode produzir sugestão de remediação, mas não decide se a própria sugestão é coerente com os fatos persistidos nem se deve entrar no plano do cliente.

A governança não altera SARI/SCORE-GEO.

## Relatório

O CAT-09 separa:

1. **Plano de ação aceito** - somente recomendações `ACCEPTED`;
2. **Verificar / decidir antes de implementar** - itens `VERIFY_DECIDE`, com a decisão/fato faltante explicitado;
3. **Itens rejeitados ou informativos** - auditáveis, fora do plano;
4. **Inventário técnico de origem** - trilha bruta preservada para rastreabilidade, explicitamente não apresentada como plano governado.

A governança é materializada antes do fingerprint e do snapshot final de `report-catalog`, portanto o pacote entregue contém as mesmas decisões exibidas.

## Fontes atualmente governadas

- recomendações determinísticas;
- sugestões de conteúdo assistidas por IA;
- sugestões de JSON-LD;
- recomendações da análise profunda/CAT-08;
- remediações agrupadas de requisições/runtime CAT-06/CAT-07.

Orientações técnicas meramente informativas continuam podendo existir na trilha técnica sem serem promovidas automaticamente a obrigação do cliente.
