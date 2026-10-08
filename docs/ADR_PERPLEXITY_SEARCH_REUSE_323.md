# ADR-323 - Reutilização interna da Perplexity Search API

Status: **aprovada para fachada mínima audit-scoped; API independente de auditoria, adiada**.
Controle: #301 / #310; relacionada a #302, #317, #318. Implementação: PR #312.

## Constatações verificadas no código

| Camada / consumidor | Responsabilidade atual | Dependência real | Reutilizável? |
|---|---|---|---|
| `search_intelligence/perplexity_request_policy.py` | Validação de filtros e precedência de opções (sem rede) | Ambiente canônico; contexto explícito de região | **Sim**, biblioteca pura |
| `search_intelligence/perplexity.py` | HTTP `POST /search`, timeout, diagnóstico, parser, request SHA-256, preço nativo por request | `AuditWorkspace`, `audit_id`, `M18Persistence` e SQLite FK `audits` | **Sim dentro de uma AUD**, não independente dela |
| `console_search_intelligence.py` | Decisão operacional, queries opt-in, escopo, sequência de execução | Estado do console e workspace da auditoria | Consumidor CAT-05, **não** motor |
| `console_search_parameter_menu.py` | Inputs efêmeros de CAT-05, ativação/credencial no editor canônico | Console; `SearchConsoleState` | Consumidor de UI |
| `geo_observation.py` / `geo_report.py` | Projeção aditiva idempotente/read-only da evidência persistida | SQLite de AUD, tabelas Search/SERP | **Não** emitem requests |
| `geo_ai.py` | Interpretação competitiva opt-in de evidências GEO | Orquestrador de IA homologado | **Não** é adapter Perplexity; não adicionar provider |
| `report_completion.py` | Materialização de relatório após persistência | Manifest, fingerprint de SQLite e `report-catalog` | Não faz rede |
| RPR/replay | Reprojeções de evidências já existentes | Snapshot original | Não devem disparar Search API |

**Conclusão:** já há um núcleo único de HTTP e cálculo comercial. Não duplicar transporte, credenciais, pricing, rate control ou normalização de erro para novo consumer. Porém o método `execute_perplexity_search(workspace, audit_id, ...)` é **audit-scoped** e altera `audit.db` e ledger ledger de tentativas de IA. Separá-lo apenas por nomenclatura seria um falso desacoplamento.

## Escolha arquitetural e trade-off

- **A - Fachada interna audit-scoped sobre o adapter existente (recomendada agora).** Menor diff/risco, compartilha transporte, request policy, preço e status; exige um workspace de AUD mutável. Útil para CAT-05 e outros consumidores **durante** AUD. Adicionar `consumer_id`, `purpose`, `context_ref`, consentimento de custo e chave de idempotência na camada *aplicativa*, sem alterar motor, apenas quando houver segundo consumer real.
- **B - Port/adapter com persistence injetável (necessária para complemento externo selado #318).** Extrair fronteira pura `request -> response` + emissor de custos, passar sink isolado e original AUD read-only; exige contrato próprio de ledger, sidecar versionado e deduplicação resistente a corrida/crash. **Não** reutilizar ingenuamente `execute_perplexity_search` sobre `audit.db` já selado.
- **C - Serviço/API externa ou provider de orquestrador.** Escopo excessivo, risco alto para integridade e duplicação de encargos; **rejeitada** para este release. API Orqetia permanece independente.

## Contrato-alvo da fachada (não afirmar que já existe)

```text
SearchIntent {
  consumer_id, purpose, context_ref, optional audit_id,
  queries[1..5], search_type WEB|FAST, geo_scope, search_options,
  explicit_cost_authorization, idempotency_key, request_fingerprint,
  expected_usage_unit=PERPLEXITY_SEARCH_REQUEST
}
SearchOutcome {
  operation_id, request_payload_hash, status, attempted,
  billability KNOWN_TRUE|KNOWN_FALSE|UNKNOWN,
  native_usage, pricing_basis, sources, provenance, observed_at
}
```

**Gates antes do transporte:** query explicitamente requerida; toggle ON não autoriza cobrança; validação e orçamento; autorização por requisição (não por login/configuração); idempotency key única para a *intenção* e *escopo efetivo*; chave de segredo apenas em memória/headers; limite de tentativas; deduplicação atômica por consumer/context/intent. A API externa não documenta idempotência comercial equivalente à chave local; timeout após envio tem cobrança incerta, portanto **não repetir cegamente** uma tentativa em estado desconhecido.

**Persistência:** em AUD ativa, tabelas `perplexity_search_runs` e `perplexity_search_sources` com `attempt_id` no ledger ledger de tentativas de IA, `request_payload_hash` e materialização GEO. Em AUD COMPLETE **selada**, não modificar `audit.db`, `audit-snapshot.db` ou o `report-catalog` original: usar sidecar `supplement_id` independente, registro append-only, manifest próprio com SHA e vínculo audit_id/hash original. Reexecução idempotente deve devolver o suplemento existente sem nova requisição, inclusive após reinício; só gerar *nova* pesquisa com nova intenção autorizada. Reconstrução do pacote original continua verificável byte a byte.

## Segurança e aceitação

1. `RASAI_PERPLEXITY_ENABLED=false` significa **zero HTTP**. Credencial não armazenada em snapshot/manifest/log.
2. Queries SERP jamais viram requisição Perplexity por herança implícita. O menu CAT-05 oferece a **cópia explícita com confirmação**, opção 6 (#318).
3. Sucesso Search API não equivale a citação de IA gerativa nem promove automaticamente evidência a score/finding.
4. Não fazer fallback automático faturável, nem agregar o mesmo `attempt_id` em duas projeções econômicas.
5. Simulação de dois consumidores usando o mesmo transporte fake é o gate antes de entregar fachada B; casos: sem query, toggle OFF, sucesso, 429, timeout de billability desconhecida, concorrência/double-submit e falha de persistência.
6. Nenhuma chamada comercial em CI. Não modificar `AI=auto`, Orqetia, motor SERP ou precificação.

**Decisão de entrega:** #323 investigação documentada; #318 pode entregar UX pré-AUD imediatamente, mas a execução *pós-AUD* fica condicionada a um sidecar idempotente seguro, sem mutações retrospectivas. Nunca chamar o executor audit-scoped diretamente sobre pacote finalizado e declarar êxito.
