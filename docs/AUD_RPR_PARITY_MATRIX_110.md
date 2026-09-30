# Matriz de paridade e convergência AUD/RPR - issue #110

Revisão estática do código em 30/09/2026, após #107, #111 e #109.
**Não equivale a homologação ponta a ponta.** A issue #110 permanece aberta
até a convergência dos desvios abaixo e o smoke controlado #15/#92.
O processamento e o RPR compartilham regras apenas quando isso é comprovado
por funções chamadas, contratos persistidos e testes direcionados; não basta
que dois caminhos produzam o mesmo estado nominal.

## Matriz verificável

| Domínio | AUD inicial | RPR seletivo | Situação e teste de aceite |
| --- | --- | --- | --- |
| Plano e escopos | `audit_resume_runtime.persist_resume_plan`; `initialize_execution_fulfillment` | `load_resume_plan`; `materialize_planned_work_items`; política de seleção | Mesmo contrato durável, mas exigir teste de todos os serviços selecionados antes do gate; fallback de versões anteriores sem contrato deve falhar fechado. |
| Aquisição HTTP / descoberta | `m2.execute_m2` e M5 | `core_reprocessing._recover_discovery/_recover_http`; `ensure_m5_foundation_from_persisted_m2` | Verificar no mesmo fixture conteúdo bruto, cabeçalhos, redirecionamentos, políticas e escopo, comparando chamadas físicas e hashes. Não presumir paridade só pela reutilização de evidências. |
| Renderização M3 | `m3.execute_m3` com `BrowserIdentityRenderer` e `m3.persist_render_capture` | `core_reprocessing._recover_render` usa **o mesmo** renderer e `m3.persist_render_capture` | Executor/persistência canônicos compartilhados; RPR difere legitimamente no namespace de artefatos e na reposição pontual de contexto. Confirmar diagnóstico #107 e preservação dos sucessos num smoke real. |
| Extração M4 | `m4.execute_m4` | `_recover_extraction` invoca `m4.execute_m4` apenas com o snapshot pendente | Executor comum; comparar extração equivalente e ausência de recriação de snapshots intactos. |
| Web Performance M21 | Executor `m21_web_performance` do fluxo inicial | `reprocess_measurements.recover_web_performance` contém loop próprio de PSI/CrUX; compartilha clientes e persistência com M21 | **Gap estrutural:** a orquestração de serviços, limites, tratamento de respostas e reaproveitamento não reside integralmente em um único executor. Extrair função canônica com contexto e déficit, sem recálculo duplicado; testes com PSI sucesso/CrUX falha, falha parcial inversa, cache persistido, múltiplos dispositivos e reprocessamento repetido. |
| Apdex de navegação M23 | `m23.execute_m23_apdex` | Sem run anterior chama `m23.execute_m23_apdex`; com run parcial usa loop de déficit próprio e funções canônicas `m23._sample/_summary` | Fórmulas de classificação e resumo compartilhadas; **orquestração parcial duplicada**. Validar orçamento de tentativas entre AUD e sucessivos RPRs, concorrência e política de pace antes de modificar. A recuperação parcial usa concorrência operacional 1, embora preserve no registro a concorrência original; verificar se é exceção metodológica justificada. |
| Apdex de experiência M25 | `m25.execute_m25_experience` | Sem run anterior chama executor; com run parcial usa `m25._measure_device`, `_persisted_sample` e `_summary` com loop próprio | Cálculo e captura física reutilizados, mas planejamento de déficit é diferente. Comparar perfis, calibração, mix, erros JS/requisição, limites e persistência anterior antes de centralizar coordenação. |
| Search Intelligence / GSC | hooks de coleta registrados | Recuperação opcional seletiva; GSC recupera hook registrado, busca tem caminho de recuperação específico | Comprovar mesmo adapter e semântica de profundidade, erro, evidência e validade temporal; nenhum serviço não solicitado entra no denominador. |
| Segurança passiva | integração determinística e inteligência externa configurada | Recalcula somente quando faltante/impactado, via funções da própria segurança passiva | Verificar assinatura de componentes e reaproveitamento de resultados externos para evitar coleta redundante. |
| Gate de IA | `audit_runner` sincroniza work-items e usa `audit_collection_gate.evaluate_collection_readiness` após coleta | `governed_reprocess_runtime` invoca o **mesmo** avaliador antes dos fluxos anteriores e da IA registrada | Implementação #111: sem plano durável, item ausente ou coleta não concluída, bloquear provedor. **Pendente:** demonstrar que todo `SUCCESS` exigível possui evidência materializada íntegra nos dois caminhos, e que não existe hook alternativo adiantado. |
| Estado e ledger | Fulfillment e selagem por escopo | Mesmas tabelas, com RPR, tentativa causal e reaproveitamento de sucessos | #108 corrige contadores de estados bloqueados e proprietário de fechamento; não declarar encerrado antes de integrar PR e validar DB/console/log/relatório. |
| Derivações, pontuação e publicação | Funções de derivação/persistência e `materialize_catalog_report_projection` | Derivação impactada por escopo, mesma projeção final; snapshot gerado após encerramento | Verificar igualdade de derivação sob mesmas evidências, presença de hashes de provenance, relatório preliminar na ausência de coleta e ausência de reescrita histórica. |

## Fronteira comum de fases

`PLAN -> MATERIALIZE -> COLLECT -> VALIDATE -> SEAL -> SHARED_AI_GATE -> AUTHORIZED_AI -> DERIVE -> FINAL_LEDGER -> REPORT`.

Um `RPR-*` pode selecionar só o déficit, reutilizar evidência válida e gravar
novas tentativas com provenance própria. Não pode adotar novas fórmulas ou
materializar `FINAL` por ter finalizado operacionalmente uma tentativa parcial.
O conjunto de itens exigíveis é **por componente e escopo**, nunca a contagem
de coletores que chegaram a executar.

O gate #111 é uma salvaguarda compartilhada, **não** substitui a verificação
de integridade dos arquivos e do banco por item `SUCCESS`. A composição dos
wrappers ainda exige convergência de coordenação; não refatorar o executor
físico de M3/M4 já compartilhado para criar superficialmente uma nova API.

## Ordem segura para concluir a Fase B de #110

1. Congelar fixtures de evidência inicial e de interrupção para M21/M23/M25,
   preservando contrato original, perfis, hashes, timestamps e os resultados
   homologados. Escolher casos com sucessos anteriores, falhas parciais,
   alterações na disponibilidade externa e dados expirados.
2. Extrair **uma** função canônica de aquisição/continuação por componente,
   parametrizada apenas pelo plano e pelas evidências anteriores. AUD fornece
   universo completo; RPR fornece o déficit elegível. Implementar um componente
   por branch e PR isolado: M21, depois M23, depois M25. **Não** alterar
   simultaneamente fórmulas, thresholds, scores, perfis ou políticas de coleta.
3. Consolidar decisão de aplicabilidade, validação de persistência, transições
   e selagem entre `audit_runner`, `core_reprocessing` e
   `governed_reprocess_runtime`. Preferir componentes compartilhados explícitos
   em vez de novas cadeias de monkeypatches ou um segundo motor RPR.
4. Em cada PR, testar **somente** a superfície alterada e seus contratos diretos,
   incluindo reversibilidade de falhas, preservação dos sucessos, nenhuma IA
   prematura e equivalência de saída com a mesma evidência.
5. Confrontar separadamente ledger, eventos e apresentação (#108/#109).
   Só após integração sem conflitos executar smoke humano da #15 e avaliar
   homologação global #92.

## Critério impeditivo de homologação

Não afirmar que AUD e RPR usam integralmente um motor canônico enquanto a
orquestração de **M21/M23/M25 parcial** continuar duplicada ou enquanto o
teste ponta a ponta de `SUCCESS` materializado e gate de IA não estiver
reconciliado. Os testes dirigidos de #107/#111/#108/#109 demonstram superfícies
específicas; não substituem a auditoria real interrompida/retomada.
