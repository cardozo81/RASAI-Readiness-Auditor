# Pipeline governado de evidência e IA

## Objetivo

O RASAi executa IA somente depois de encerrar a coleta aplicável, persistir as evidências e materializar as análises determinísticas necessárias ao contexto daquela execução.

O contrato causal canônico é:

```text
CONFIGURAÇÃO
  -> COLETA CORE
  -> COLETA EXTERNA / INTEGRAÇÕES
  -> ANÁLISE DETERMINÍSTICA
  -> EVIDENCE_SEALED
  -> IA
  -> AI_SEALED
  -> DERIVAÇÕES FINAIS / SCORE / RECOMENDAÇÕES
  -> REPORT PROJECTION
  -> COMPLETE
```

A regra vale para execução local, console interativo e job `AUDIT` do SaaS. Não existe um segundo pipeline de negócio específico para o worker ou para o console.

## Princípios obrigatórios

1. **IA não é coletor.** Nenhum provider substitui HTTP, browser, GSC, PageSpeed/CrUX, Clarity, SERP ou outro coletor configurado.
2. **Coleta requerida termina antes da IA.** Um coletor não precisa terminar em `SUCCESS`, mas precisa chegar a um estado terminal explicitamente classificado.
3. **Contexto de IA é versionado.** A IA referencia uma versão imutável da evidência da AUD.
4. **Nenhum coletor acrescenta evidência para a mesma versão depois do início da fase de IA.** Nova evidência exige nova versão.
5. **IA é o último consumidor analítico da evidência.** Score, regras de integridade, priorização e recomendações podem ocorrer depois, mas não podem abrir nova coleta ou chamada de provider.
6. **Renderer é projeção.** Geração/enriquecimento de HTML pode ler `audit.db` e escrever artefatos de relatório; não pode coletar, chamar IA nem mutar o estado canônico da AUD.
7. **Reprocessamento é seletivo.** Uma alteração de evidência invalida somente tarefas de IA cuja fatia de dependência mudou.

## Estados de coleta

### Terminais

Os estados abaixo encerram uma tentativa de coleta para efeito do gate de IA:

- `SUCCESS`
- `PARTIAL`
- `ERROR`
- `FAILED_RETRYABLE`
- `FAILED_PERMANENT`
- `BLOCKED`
- `SKIPPED`
- `DISABLED`
- `NOT_CONFIGURED`
- `NOT_APPLICABLE`
- `NO_DATA`
- `REQUESTED_NOT_EXECUTED`
- `SKIPPED_SOURCE_BLOCKER`

Estado terminal não significa sucesso. Ele significa que o runtime já conhece o resultado daquela dependência para a versão atual.

### Não terminais

- `PENDING`
- `RUNNING`
- `PROCESSING`
- `WAITING_FOR_DATA`
- `UNKNOWN`

Estados futuros/desconhecidos são tratados como não terminais até serem classificados explicitamente. O comportamento é fail-closed.

## Gate por dependência

O gate é por finalidade de IA e não um único `all_success` global.

Uma tarefa declara:

- dependências esperadas;
- dependências que apenas precisam estar terminais;
- dependências que precisam estar em `SUCCESS` para aquela finalidade;
- escopo de evidência efetivamente consumido.

Exemplo:

```text
GSC=PARTIAL, CLARITY=ERROR
```

pode liberar uma tarefa que não exige sucesso desses serviços. A mesma situação bloqueia uma tarefa que declarou `GSC` em `success_required`.

Uma falha opcional e não relacionada não deve provocar rerun ou bloqueio de uma tarefa independente.

## Versão imutável de evidência

`ai_evidence_versions` registra uma fotografia lógica da AUD antes da IA, incluindo:

- `audit_id`;
- `evidence_snapshot_id`;
- `version_number`;
- fingerprint;
- IDs de evidência persistidos;
- estados de coleta;
- contexto determinístico associado;
- snapshot anterior substituído;
- versão do contrato;
- momento do seal.

O fingerprint é determinístico sobre o conjunto persistido usado no seal. Repetir o seal sem alterar esse conteúdo reutiliza a mesma versão. Alterar evidência, estado de coleta ou contexto do seal gera uma nova versão.

## Tarefas e rounds de IA

`ai_tasks` e `ai_request_rounds` complementam — não substituem — os registros globais de provider, request/response, tokens, custo e fallback.

Uma tarefa pode registrar:

- finalidade;
- escopo;
- versão de evidência;
- contrato semântico;
- prompt e versão;
- requisitos esperados;
- requisitos aceitos, rejeitados e ausentes;
- estado da tarefa;
- razão de staleness.

Rounds permitem continuação controlada sem sobrescrever requisito que já foi aceito para a mesma versão de evidência.

## Invalidação seletiva

`ai_task_dependency_specs` registra a fatia efetivamente consumida por cada tarefa:

- tipo de dependência;
- scope key;
- collection keys;
- fingerprint da dependência;
- versão de evidência na qual o fingerprint foi validado.

Quando uma nova versão é selada:

1. o fingerprint global da AUD pode mudar;
2. cada tarefa existente recalcula somente sua fatia de dependência;
3. se a fatia mudou, a tarefa fica `STALE`;
4. se a fatia não mudou, o resultado permanece válido e apenas avança seu `validated_snapshot_id`.

Portanto, `GSC ERROR -> retry -> GSC SUCCESS` não força rerun de uma tarefa que depende somente de Clarity ou de evidência semântica de uma página não alterada.

## Execução inicial

A sequência de `audit_runner` é, conceitualmente:

1. criar AUD e persistir configuração/contexto;
2. M2/M3 e demais coleta/extratação core;
3. coletores externos registrados;
4. comparações e reconciliações determinísticas pré-seal;
5. lado determinístico/network de M24;
6. `EVIDENCE_SEALED`;
7. diagnósticos de source quality por IA quando aplicável;
8. M7 semântico;
9. IA técnica M24 quando habilitada;
10. M20 content remediation quando habilitado;
11. tarefas de IA registradas, incluindo análise profunda quando habilitada;
12. `AI_SEALED`;
13. regras finais de integridade pré-score;
14. M9 scoring;
15. M10 recomendações e linking;
16. reconciliação final de fulfillment persistido;
17. M11 e projeções de relatório.

Não deve existir chamada de provider depois do passo 12 nem coletor depois do passo 6 para a mesma versão.

## Coletores externos

Integrações opcionais são registradas como collection hooks e executadas antes do seal. Isso inclui, conforme configuração/capacidade:

- PageSpeed / CrUX e APDEX associados;
- Google Search Console;
- CrUX History;
- Microsoft Clarity;
- Common Crawl quando aplicável ao contrato atual;
- Search Intelligence solicitado dentro da AUD;
- W3C HTML/CSS;
- MDN Observatory;
- Web Platform Baseline;
- outras integrações que venham a ser adicionadas ao registry.

`SEARCH_MONITOR` contínuo do SaaS permanece um job independente e não bloqueia `EVIDENCE_SEALED` de uma AUD.

## Análise determinística

O registry de deterministic hooks executa reconciliações persistentes que devem fazer parte do contexto antes do seal, por exemplo:

- métricas base de standards/readiness;
- information retrieval;
- métricas HTTP operacionais;
- dados estruturados;
- métricas derivadas de GSC;
- sincronização de fulfillment necessária ao contexto.

Uma deterministic hook não pode chamar provider de IA. Observação remota pertence à fase de coleta.

## Report projection read-only

A fase de relatório possui dois mecanismos complementares:

1. funções historicamente usadas por wrappers são protegidas enquanto o contexto de report projection está ativo;
2. o finalizer calcula um fingerprint lógico de `audit.db` antes e depois da materialização. Se houver mudança, a execução falha com `REPORT_RENDERER_MUTATED_AUDIT_DB`.

O fulfillment foi separado em dois efeitos:

- **reconciliação durável:** ocorre antes do primeiro renderer;
- **projeção:** `processing-status.json` e banner HTML são gerados a partir do summary já persistido, sem `recalculate()` e sem escrita em SQLite.

A mesma regra vale para rerender: reabrir/materializar HTML não pode gerar custo de rede/IA nem modificar a evidência auditada.

## Reprocessamento RPR

O RPR usa o mesmo modelo de governança:

```text
RECOVERY / RECOLLECTION
  -> DETERMINISTIC RECONCILIATION
  -> NEW EVIDENCE SEAL (se houve mudança)
  -> SELECTIVE AI INVALIDATION
  -> rerun somente de tarefas STALE/elegíveis
  -> AI_SEALED
  -> fulfillment persistido
  -> report projection
```

O runtime não transforma toda alteração de AUD em rerun global de IA.

Coleta live vencida ou falha pode ser reexecutada conforme o contrato de fulfillment. Evidência anteriormente registrada como sucesso, mas cujo artefato histórico desapareceu, continua sendo tratada como problema de integridade; uma versão posterior do site não deve substituir silenciosamente o histórico.

## SaaS e lease do worker

O SaaS mantém um único job durável `AUDIT`; as fases são internas ao pipeline canônico.

Como a coleta completa pode alongar o tempo antes da IA, o worker renova `lease_until` periodicamente enquanto está saudável. O heartbeat:

- preserva a propriedade do job pelo mesmo worker;
- usa um handle de control plane separado;
- não compartilha transação SQLite/PostgreSQL com a auditoria;
- não converte falha transitória de heartbeat em cancelamento de provider/collector no meio da chamada;
- mantém o mecanismo existente de recuperação de lease expirado em caso de falha real do worker.

A solução não depende de simplesmente aumentar um timeout fixo.

## Console interativo

O console continua lançando/observando a execução canônica; não contém uma implementação paralela de regras de negócio.

A apresentação de progresso deve refletir a ordem causal:

```text
Inicialização
Coleta core
Coleta externa / integrações
Análise determinística / consolidação de evidência
Evidence sealed
Análise de IA
AI sealed
Score e recomendações finais
Relatórios
Finalização
```

Configuração de provider/model/reasoning pode ser resolvida antes da execução. Isso é um **AI configuration snapshot** e não deve ser confundido com o **AI evidence snapshot**, que só existe depois da coleta/análise determinística.

## Segredos e rastreabilidade

Evidence snapshots e payloads duráveis de job não armazenam credenciais. Segredos continuam sendo resolvidos por environment/secret management.

A política global existente continua autoridade para:

- provider/model/reasoning;
- AUTO/fallback;
- retries;
- circuit breaker/quarantine;
- pricing;
- tokens/cached tokens/reasoning tokens;
- custo observado/estimado;
- provider attempts;
- exchange log sanitizado.

A governança de evidência adiciona causalidade e proveniência; não cria uma segunda política de IA.

## Invariantes de teste

A suíte deve provar de forma isolada, no mínimo:

- estados terminais/não terminais e fail-closed para estado desconhecido;
- gate que diferencia terminalidade de sucesso obrigatório;
- seal idempotente para fingerprint igual;
- nova versão para fingerprint alterado;
- ausência de contexto de IA antes de `EVIDENCE_SEALED`;
- invalidação somente da tarefa cuja dependência mudou;
- ordem `collection -> seal -> AI -> AI_SEALED -> pre-score -> score -> recommendation -> report`;
- projeção de fulfillment sem mutação de `audit.db`;
- idempotência do banner/status de relatório;
- extensão de lease somente pelo worker proprietário de job ativo.
