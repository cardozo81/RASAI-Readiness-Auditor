# RASAi - Plano de evidências e conclusão das issues elegíveis

> Checkpoint verificado em 15/10/2026: `main@d91bf6eb89bc5570464c69323c44b673655bcafa`; 15 issues abertas ≥ #301; PRs abertas: 0; CI final 17/17 checks e 12/12 workflows push SUCCESS. Este documento **é plano**, não relatório de testes executados neste ciclo.

## Norma de execução

- Somente issues ≥ #301 podem receber trabalho. A issue #322 mantém a restrição experimental expressa: não implementar nem ativar sem autorização específica. #1/#127/#192 e #210 podem ser consultadas como antecedentes, sem alterar seus escopos.
- Uma branch serial para trabalhos futuros correlacionados; commits pequenos e PRs por recorte coeso, sem desenvolvimento em `main`. Não fazer mudanças artificiais em código só para indicar progresso.
- Distinguir `IMPLEMENTED_AND_PROVEN`, `IMPLEMENTED_NOT_PROVEN`, `PARTIALLY_IMPLEMENTED`, `BLOCKED_EXTERNAL`, `NEEDS_DECISION`. Presença de código, CI sintética e URL de PR não bastam para afirmar prova física/comercial.
- `N/D` é uma saída correta quando a proveniência é insuficiente. Não fabricar clocks, coortes, consentimentos, recibos, verdade regulatória, posição SERP, comparabilidade de providers ou scores.
- Não chamar APIs remuneradas, não executar AUD real, não modificar SQLite histórico, nem alterar M23/M25, SARI, SCORE-GEO-004, orquestração IA, CONS-3 ou design aprovado apenas para encerrar issues.

## Ordem para maximizar comprovação antes de codificar

1. **Ciclo de prova offline prioritário:** #523, #319, #602 e #600 (inventários/metadados, replay CLI em **cópia estável existente da AUD** quando disponível e testes dos contratos já integrados). Se falta a AUD, registrar `EVIDENCE_NOT_AVAILABLE`; não criar AUD paga como substituta.
2. **Ciclo de engenharia limitada:** #601 e #603 (componentes/consumidores de fronteira de confiança isolados), #523 (somente adapters/matriz faltantes), #319 (somente telemetria efetivamente faltante). Antes de alterar, apresentar teste que comprova a lacuna.
3. **Ciclo de fontes externas e autorização:** #304, #355, #330. Avançar offline até o limite; a coleta real depende de fonte/escopo/credenciais/autorização explícitos. Não declarar que Search API Perplexity comprova equivalência de país/idioma/device nem que RUM equivale ao Synthetic.
4. **Ciclo metodológico:** #602 (ADR e decisão sobre regra de score), #601 (BR-GEO-039/049), #311 (CONS-3/longitudinal), #322 (experimental e bloqueada).
5. **Épicos e dívida:** reconciliar #301/#357/#604 após os gates de suas filhas obrigatórias; #639 continua por lotes de baixa regressão, nunca bloqueando correções P1.

## Modelo obrigatório de dossiê de aceite

Cada critério deve possuir: `criterion_id`, descrição textual preservada, status, evidência existente (módulo/teste/PR/SHA), comando reproduzível, artefato/hashes (ou razão de indisponibilidade), classe de prova (`SYNTHETIC`, `OFFLINE_REAL`, `LIVE_AUTHORIZED`, `HUMAN_ACCEPTED`), exceção formal, resultado observado, risco residual e decisão `CLOSE/KEEP_OPEN/BLOCKED`.

Nenhuma célula deve ser preenchida como PROVEN apenas por indicação do plano ou por teste anterior que não cobre aquele critério. O checklist de issue é atualizado após cada PR/validação, com vínculo explícito ao HEAD do merge.

## Direcionamento individual e gates

### Issue #523 - P2 · IMPLEMENTED_NOT_PROVEN + PARTIALLY_IMPLEMENTED

**Já presente / evidência técnica:** `console_configuration_inventory_523`, `console_config_provenance_523`, testes de save/load em processos independentes, projeção M23/M25, draft Perplexity não autorizativo.

**Critério residual e risco:** Matriz de todos os consumidores/runtime, precedência efetiva variável a variável, paridade completa de categoria e smoke humano Windows ainda sem certificado.

**Implementação ou verificação direcionada:** Gerar inventário metadata-only sobre INI temporário; confrontar cada EnvironmentSpec e campo tipado com loader/serializador/consumidor; criar apenas adapters/tests faltantes, sem tocar M23/M25. Usar relatório de exceções por variável, não alegar paridade de secret execution-only.

**Testes selecionados (planejados, não executados aqui):** `python -m rasai.console_configuration_inventory_523 --ini <INI_TEMP> --verify-apdex`; `python -m pytest -q tests/test_console_configuration_inventory_523.py tests/test_console_fresh_process_roundtrip_523.py tests/test_console_persistence_matrix_523.py tests/test_console_config_provenance_523.py`.

**Prova exigida para fechamento:** CSV/JSON secret-safe de 100% do registry (categoria, source, persistência, origem, loader, consumidor, precedência e resultado), round-trip não default em 2 processos, comparação de efeitos em adapters, prova Windows específica sem credenciais reais. Fechar só com matriz completa e gate Windows pertinente.

### Issue #319 - P2 · PARTIALLY_IMPLEMENTED

**Já presente / evidência técnica:** `audit-attempts`, `audit_fulfillment_timing_319`, cronômetros de logs operacionais, forecasts, exclusão de custos Directed/Search opcionais (PR #629).

**Critério residual e risco:** Clocks exclusivos confiáveis de todas as etapas não-IA, atribuição financeira por fase e separação correta entre soma das tarefas e wall-time; histórico real não comprova toda a partição.

**Implementação ou verificação direcionada:** Executar inspeção read-only em AUD física estabilizada; construir cobertura por fase distinguindo OBSERVED/UNVERIFIED/N/D. Somente se houver fonte física segura, adicionar pontos de observabilidade nas bordas do runtime sem alterar lógica orquestradora; nunca inferir duração exclusiva por subtração.

**Testes selecionados (planejados, não executados aqui):** `rasai audit-attempts <AUD_DIR>`; `python -m pytest -q tests/test_audit_stage_scope_319.py tests/test_audit_attempt_timeline_319.py tests/test_audit_duration_forecast_319.py tests/test_audit_cost_explain_319.py tests/test_cost_forecast.py`.

**Prova exigida para fechamento:** Reconciliação das 8 tentativas IA (M18 + remediação), momentos overlapped, custos por operação, expected/observed e P90 não-teto, cobertura por fase; N/D preservado quando relógio ausente; no duplicate-cost. Fechar com equivalência comprovada console/prévia/relatório e cobertura exigível demonstrada.

### Issue #602 - P1 · IMPLEMENTED_NOT_PROVEN + NEEDS_DECISION

**Já presente / evidência técnica:** Classificador opcional/contradição/desconhecido, ADR, laboratório in-memory, CLI read-only `optional_seo_audit_replay_602` sem alterar SCORE-GEO-004.

**Critério residual e risco:** Replay físico golden sobre cópia estável da AUD de 14/10 executado em Windows e aprovado em 15/10/2026; permanece a decisão explícita de finalidade/política e versão de score para mudança numérica.

**Implementação ou verificação direcionada:** Reproduzir score canônico sobre cópia isolada, comparar bytes SHA-256 antes/depois e overall/dimensões/gates/coverage/confidence; gerar cenários sem promover a produção. Submeter ADR/efeitos a gate metodológico. Somente após decisão, implementar versão nova e migração de leitura histórica não destrutiva.

**Testes selecionados (planejados, não executados aqui):** `python -m rasai.optional_seo_audit_replay_602 <AUD_COPIA> --device MOBILE`; `python -m pytest -q tests/test_scoring_discovery_refinement_20260908.py tests/test_score_geo_004.py tests/test_score_geo_004_applicability.py`.

**Prova exigida para fechamento:** Golden da AUD com 59 rule executions e score persistido 86,484962, comparação BR-GEO-003/013/017 e matriz de delta por dimensão, política aprovada e contrato versionado, replays idempotentes, nenhuma alteração da AUD original. Sem decisão: issue OPEN.

### Issue #601 - P1 · PARTIALLY_IMPLEMENTED + BLOCKED_AUTH

**Já presente / evidência técnica:** Classificador de transição FAQ no DOM e `faq_interaction_receipt_601` HMAC, com guard `crawler_discovery_verified=false`; testes em `test_ymyl_context_flow.py`.

**Critério residual e risco:** Coletor browser opt-in seguro com gesto real em contexto isolado, prova DOM pré/pós em mesmo alvo, matriz lazy-mount e decisão metodológica versionada BR-GEO-039/049.

**Implementação ou verificação direcionada:** Criar componente isolado de replay FAQ explicitamente opt-in, com allowlist de alvo/URL, bloqueio de forms/auth/clicks arbitrários, duração limitada, egress pós-load bloqueado, hashes/tempos UTC, recibo do coletor; preservar o DOM canônico. Separar disponibilidade humana, acesso crawler e ausência editorial.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_ymyl_context_flow.py` + novos testes sem browser externo para FAQ SSR, DOM oculto, lazy mount SPA, aria-controls quebrado/duplicado, timeout/erro/negação, falha de MAC e zero network.

**Prova exigida para fechamento:** Fixtures reais autorizadas e rastreáveis com recibos íntegros do mesmo alvo e URL, distinção de estados read-only, relatório sem alegar ausência editorial ou indexação sem prova; score histórico intacto. Qualquer alteração numérica depende de contrato/versionamento próprio.

### Issue #600 - P1 · IMPLEMENTED_NOT_PROVEN + GATED

**Já presente / evidência técnica:** SARI/overview com cobertura percentual/fração, scope ORIGIN versus URL, Lighthouse/CrUX/Apdex com ressalvas, destaque LOW/PARTIAL e SERP 9/20, após PRs #620/#621 e UX #633.

**Critério residual e risco:** Matriz de aceite visual/semântico consolidada da AUD real após decisões #601/#602; evitar que Overall HIGH seja usado como certificação de experiência/search/IA.

**Implementação ou verificação direcionada:** Gerar preview read-only a partir de dados imutáveis e fixture negativa SARI alto + Lighthouse ruim + escopo ORIGIN, comparar todos 6 critérios sem recalcular scores; corrigir apenas projeção semântica se evidência apontar divergência.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_sari_readiness_presentation.py tests/test_report_semantics.py tests/test_report_presentation.py tests/test_external_sari_materialization.py`.

**Prova exigida para fechamento:** Capturas/asserções da apresentação do 86,5 HIGH e coverage 97,5%, dimensão CONTENT_VALUE LOW/PARTIAL, ORIGIN vs URL, 9/20 SERP; gate semântico #601/#602 formalmente reconciliado. Não exigir performance real boa como condição do SARI.

### Issue #603 - P2 · PARTIALLY_IMPLEMENTED + BLOCKED_EXTERNAL

**Já presente / evidência técnica:** Classificador de claims, recibo de revisor HMAC e CLI importador offline, mensagem `official_regulator_source_verified=false` até autenticidade independente.

**Critério residual e risco:** Pipeline de autenticação de fonte primária fora da página/LLM, documentos vigentes auditáveis por produto/claim e integração governada dos resultados no relatório.

**Implementação ou verificação direcionada:** Especificar fronteira confiável independente (issuer/URL/version/effective window/document SHA256/revisor allowlisted); implementar adapter read-only para receber fonte autenticada sem transformar boolean autodeclarado em confiança; mapear decisão e estado N/D à apresentação, sem certificação jurídica.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_ymyl_context_flow.py` + fixtures documento inexistente, fora de vigência, produto divergente, digest/MAC inválido, origem adulterada, claim contraditório e revisor não autorizado.

**Prova exigida para fechamento:** Dossiê de fonte primária autenticada e recebimento sob autorização, prova por claim/versão/escopo, teste de ausência de credencial no INI, relatório `CLAIM_UNVERIFIED_EXTERNAL` na falta de fonte. Sem documento/revisor externo, não fechar se a aceitação exige corroboração.

### Issue #304 - P1 · PARTIALLY_IMPLEMENTED + BLOCKED_EXTERNAL

**Já presente / evidência técnica:** GEO OBSERVATION v8, `geo_query_ledger_304`, URL exata/host alternativo, denominadores e abstenções, N/D por query sem proveniência, UI descritiva.

**Critério residual e risco:** Prova de equivalência externa de mercado, idioma, dispositivo, intenção/branded e tempo Perplexity × SERP; validação de fonte física sem paid calls neste ciclo.

**Implementação ou verificação direcionada:** Inspecionar ledger físico já persistido por query, declarar matriz das dimensões de comparabilidade que o provider realmente entrega. Implementar somente atributos observados/adapters, nunca inferir o que a API não retorna; caso contrato de provider não ofereça equivalência, reportar NOT_VERIFIABLE e manter métricas DESCRIPTIVE_ONLY.

**Testes selecionados (planejados, não executados aqui):** `rasai geo-query-ledger <AUD_DIR> --format json`; `python -m pytest -q tests/test_geo_query_ledger.py tests/test_geo_observation.py tests/test_geo_report.py`.

**Prova exigida para fechamento:** Amostra de pares com request IDs, query, intent, país/idioma/device/collected_at e hashes físicos, denominadores válidos, multi-query positivo/negativo. Sem provider comparável, aceitar apenas alegação descritiva, não certificar ranking/share/citação.

### Issue #311 - P3 · PARTIALLY_IMPLEMENTED + NEEDS_DECISION

**Já presente / evidência técnica:** `geo-longitudinal`, `geo_cons_companion_311`, pacote derivado e preflight seguro, trends N/D, CONS-3 intocado.

**Critério residual e risco:** Zero coortes elegíveis na revisão histórica de 21 AUDs; falta contrato metodológico aprovado e integração nativa ao CONS, caso autorizada.

**Implementação ou verificação direcionada:** Decidir se o escopo aceitável é companion consultivo ou tendência medida; construir 2+ AUDs genuinamente comparáveis (não fabricar). Se integração nativa for aprovada, produzir contrato CONS versionado, fingerprint e testes de idempotência e limites; não inserir taxas não equivalentes.

**Testes selecionados (planejados, não executados aqui):** `rasai geo-longitudinal <AUD_A> <AUD_B>`; `python -m pytest -q tests/test_geo_longitudinal.py tests/test_geo_cons_companion.py tests/test_geo_cons_package.py`.

**Prova exigida para fechamento:** Proveniência por coorte, mesma URL/query/mercado/método/versão, série N/D quando não homogênea, package source hashes, contrato CONS aprovado, teste de fingerprints e não alteração de CONS-3. Sem metodologia: OPEN.

### Issue #330 - P3 · PARTIALLY_IMPLEMENTED + BLOCKED_AUTH

**Já presente / evidência técnica:** Coleta HTTP opcional gated por consent-host/robots, transporte pinado, evidência content/bundle/sidecar e comparação read-only; docs com nomes estáveis pós PR #643.

**Critério residual e risco:** Consentimento persistente e revogável, autorização operacional/egress SaaS, coleta SPA pós-hidratação e evidência primária de conteúdo com mercado/device/epoch equivalentes.

**Implementação ou verificação direcionada:** Implementar política de consentimento opt-in revogável independente do auditor principal, limites por host/finalidade, trilha de escopo e cancelamento; pipeline de captura JS autorizada isolado e estados `N/D` para shell/timeout/robots; preservar materialização existente.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_geo_competitor_fetch.py tests/test_geo_competitor_pinned_egress.py tests/test_geo_competitor_content_provenance.py tests/test_geo_competitor_capture_bundle.py`.

**Prova exigida para fechamento:** Fixtures HTTP de shell vazio/robots/403/redirect/SPA; para aceite externo obter consentimento por alvo, log autorizado de egress, URL inicial/final mesma origem autorizada, hash HTML renderizado, captura principal e provenance com observation_id; sem opt-in não navegar.

### Issue #355 - P2 · IMPLEMENTED_NOT_PROVEN + BLOCKED_EXTERNAL

**Já presente / evidência técnica:** Advisory arquitetura, Settings 2.0, RUM USQL, crosschecks offline/live opt-in e transporte pinado; CAT-07 diferencia RUM vs Synthetic.

**Critério residual e risco:** Tenant autorizado, coorte real correlacionada por app/browser/URL/device/time, action types Load/XHR/Custom e thresholds/soft-route comprovados; ajustes de apresentação onde houver defasagem.

**Implementação ou verificação direcionada:** Primeiro executar comparadores offline com export/snapshot autorizado, confirmar KPM/threshold/fallback por action e contexto de coorte; no gate autorizado, executar somente consulta RUM read-only no tenant controlado, sem inventar settings nem alterar M23/M25.

**Testes selecionados (planejados, não executados aqui):** `rasai dynatrace-rum-crosscheck` com snapshots locais verificados; `python -m pytest -q tests/test_dynatrace_apdex_arch_advisory.py tests/test_dynatrace_population_crosscheck.py tests/test_dynatrace_live_crosscheck.py tests/test_cat07_architecture_integration_358.py`.

**Prova exigida para fechamento:** Settings snapshot físico e metadados tenant/app + USQL action populations com janela temporal; captura do CAT-07 `N/D` quando não obtido, distinção load vs SPA route e método Synthetic; homologação humana do crosscheck real exigida no contrato.

### Issue #322 - EXCEÇÃO · BLOCKED_AUTH / EXPERIMENTAL

**Já presente / evidência técnica:** Sidecar experimental offline, Playwright pilot e A/B de overhead; sem conexão ao gateway M25 e sem ativação produtiva.

**Critério residual e risco:** Gate original experimental permanece vigente: sensor same-sample real, custos físicos/overhead comparável, feature gate e decisão metodológica/operacional.

**Implementação ou verificação direcionada:** Não implementar nem ativar no atual ciclo sem autorização específica expressa. Consultar resultados históricos como informação; não bloquear advisory autônomo #355/#357 pela ausência do sensor opcional.

**Testes selecionados (planejados, não executados aqui):** Somente as regressões existentes `tests/test_apdex_content_readiness_322.py`, `tests/test_playwright_primary_content_probe_322.py`, `tests/test_readiness_matched_pilot_322.py` se algum contrato externo ao escopo for tocado (não previsto).

**Prova exigida para fechamento:** Para uma futura autorização: identidade física page/sample/clock, baseline e overhead, aceitação feature gate, não alteração M23/M25. Estado OPEN até lá.

### Issue #357 - EPIC/P2 · EPIC_GATED

**Já presente / evidência técnica:** Perfis consultivos de arquitetura/CAT-07, interface de presets e observabilidade Dynatrace independente com testes; #321 e #324 históricas concluídas.

**Critério residual e risco:** Homologação #355 e cruzamento configuracional #523 ainda não fechados; integração do sensor #322 é experimental e explicitamente separada.

**Implementação ou verificação direcionada:** Conferir gates e condições das filhas #355, #358 e relação consultiva com #523; separar entregas de advisory aprováveis sem RUM de alegações que requerem tenant real. Não reabrir #322 como atalho e não alterar M23/M25.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_cat07_architecture_integration_358.py tests/test_dynatrace_apdex_arch_advisory.py tests/test_m25_dynatrace_compat_defaults.py`.

**Prova exigida para fechamento:** Matriz dos critérios do épico com ponte para evidências #355/#523 e histórico de PRs, CAT-07 real read-only, aceites exigíveis. Fechar somente o épico contratualmente completo, sem condicionar parte independente ao sensor opt-in.

### Issue #301 - EPIC/P1 · EPIC_GATED

**Já presente / evidência técnica:** Pipeline GEO observacional, Perplexity opt-in, relatório GEO e integrações aprovadas no recorte da AUD; release #310 encerrada.

**Critério residual e risco:** Contratos remanescentes diretamente pertencentes ao épico, especialmente equivalência/denominadores #304; não confundir roadmaps #311/#330 com gate de release já homologado.

**Implementação ou verificação direcionada:** Reconstruir checklist somente das filhas originalmente integrantes do épico e do escopo residual ativo; classificar cada relação como BLOCKER/RELATED/ROADMAP, exigir prova GEO por consulta e gates comerciais sem chamadas automáticas. #311/#330 não devem ampliar retroativamente aceite do release #310.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_geo_observation.py tests/test_geo_query_ledger.py tests/test_geo_report.py tests/test_perplexity_search_intelligence.py`.

**Prova exigida para fechamento:** Rastreabilidade de cada filha obrigatória, evidência de fontes, fechamento de #304 quando contratualmente possível, paridade geo.html e motor preservado. Aceitar descritivo com N/D apenas se contrato do épico permitir explicitamente; se não, OPEN.

### Issue #604 - EPIC/P1 · EPIC_GATED

**Já presente / evidência técnica:** Predecessores #597/#598/#599 concluídos e PRs de interpretação / indicadores integradas; #600-#603 seguem parcial/condicionado.

**Critério residual e risco:** Gate de política #601/#602, claim assurance #603 e aprovação executiva #600 sem declarar score factual externamente validado.

**Implementação ou verificação direcionada:** Manter grafo G0→G1→G2→G3; comparar as filhas por critério e prova, não por status da UI #633. Concluir #600 somente com ressalvas metodológicas reais e aceite do contrato vigente.

**Testes selecionados (planejados, não executados aqui):** Executar testes direcionados das filhas; smoke visual consolidado uma única vez após gates e PRs integradas, sem nova AUD paga.

**Prova exigida para fechamento:** Matriz fechada #597-#603, commits/PRs, release read-only, hash AUD, CI final, aceite humano apenas onde expressamente exigido; então fechar épico.

### Issue #639 - P3 · PARTIALLY_IMPLEMENTED

**Já presente / evidência técnica:** Gate incremental de novos paths (#640), migração documental (#641/#642/#643) e docs de política; 238 caminhos numéricos por inventário de árvore não truncada.

**Critério residual e risco:** Inventário de ID opaco não coberto por regex, referências por categoria, exceções públicas/externas e 238 paths anteriores ainda não migrados.

**Implementação ou verificação direcionada:** Por lotes semânticos em mesma branch integradora: docs restantes (28), workflows (55), scripts (1), testes (94), módulos src (60). Antes de cada rename gerar grafo de imports/CLI/workflows/docs, atualizar referências de CI e entradas documentadas; preferir git mv e nenhuma alteração de bytes quando possível.

**Testes selecionados (planejados, não executados aqui):** `python -m pytest -q tests/test_repository_filename_policy.py` + pytest/import/CLI dos caminhos efetivamente renomeados + jobs afetados Linux/Windows; comparar `git diff --find-renames` e refs antigas.

**Prova exigida para fechamento:** 0 violações não excepcionadas numa varredura completa, exceções versionadas e documentadas, CI verde em cada lote, imports/CLI/links estáveis. Não trocar 238 renames por regressão transversal.

## Gates de finalização e reversibilidade

1. Fixar SHA do HEAD e localizar evidência imutável antes de qualquer replay. Na análise de AUD, usar **cópia isolada**, SQLite `immutable=1`/read-only quando suportado; rejeitar WAL/SHM/journal pendentes; gerar SHA-256 antes/depois de `audit.db`.
2. Executar **apenas** pytest/CLI do recorte afetado, mais gates de contrato diretamente relevantes; não executar matriz manual completa. A PR aciona checks regulares do GitHub.
3. Preservar o resultado do fluxo anteriores como golden em paridade; nunca reinterpretar versão histórica nova a partir de estado metodológico atual. Quando mudança numérica de score for necessária, nova versão, ADR, backtest, fixture negativa/positiva e aceite decisório explícito.
4. Integrar a PR apenas com checks obrigatórios verdes; confirmar HEAD final e workflows push separadamente. Diferenciar falha de startup de contêiner de falha de testes; reexecutar apenas job de infra afetado.
5. Fechar issue como `COMPLETED` **somente** com todos os critérios exigíveis comprovados na `main`, testes e provas necessárias, nenhuma homologação/decisão humana obrigatória faltante.
6. Se faltar apenas prova externa/autorização, registrar exatamente fonte, escopo, responsável, custo e critério de desbloqueio; prosseguir nas demais issues. Épicos não são concluídos por encerramento administrativo, UX previamente aprovada ou quantidade de commits.

## Evidência física posterior ao plano (15/10/2026)

As instruções das seções acima foram concebidas antes do gate físico. O estado de aceite abaixo substitui exclusivamente as lacunas cuja comprovação foi efetivamente apresentada pelo operador; não substitui os requisitos remanescentes.

- **#523 - branch/CI:** preflight de `main@beb5cc8c5e287ecee6e869779881702efb74eb07` em Windows: `41 passed, 4 skipped`; `registry_size=189`, campos tipados `72/73` com único campo derivado `synthetic_apdex_experience.device_mix`, zero violações secret/INI, zero requests, zero escritas em AUD. Na branch `chore/acceptance-evidence-reconciliation@8058bbbb`, o operador executou os quatro arquivos de regressão: `43 passed, 4 skipped`, e o preflight relatou `load_warning_count=22`, todos `unknown_or_nonpersistible_environment`; as outras quatro categorias tiveram zero. O inventário não demonstrou origem/consumidor de 100% dos campos. Um refinamento sanitizado da causa dos avisos foi adicionado à PR #645 e ainda precisa de CI e preflight físico **sobre o novo HEAD**. Manter OPEN até reconciliação dos rejeitados, matriz efetiva e smoke save/reopen.
- **#319 - Windows físico:** `140 passed, 3 skipped` nas regressões direcionadas; oito tentativas de IA (incluindo Content Remediation), `641249,761 ms` acumulados e `812189 ms` de duração física de sessão. `US$ 0,153062004` é estimativa post-hoc, não cobrança observada. Persistem `non_ai_stages_measured=false` e ausência de cronômetros exclusivos físicos das fases não-IA; não somar durações sobrepostas. Manter OPEN.
- **#602 - golden físico aprovado:** cópia isolada `AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF`, 59 rule executions, replay `VERIFIED_SCORE_GEO_004`, hash antes/depois do banco `036EC79119C937540A29DAD0571607D0F24F5B404C31D11ADEE4FF44760274C3`. Score canônico 86,484962 / ATTENTION, sem alteração dos índices ou dados. Cenários `OPTIONAL_ABSENCE_NOT_APPLICABLE=89,800752` e `OPTIONAL_ABSENCE_PASS=89,958647` são apenas simulações, não política aprovada. `19 passed` em regressões focais; manter OPEN até decisão metodológica e versionamento, caso aplicável.

## Pontos de governança corrigidos na reconciliação

- **#301:** #311 e #330 são roadmaps relacionados e não devem ser introduzidos retroativamente como gates obrigatórios do release GEO #310 já encerrado. Reconciliar os requisitos explícitos restantes do épico sem apagar #304.
- **#357:** o advisory de arquitetura é independente do sensor experimental #322; manter o gate próprio #355 e a compatibilidade de configuração #523. #322 não é autorização de alterar motores.
- **#523:** documentação histórica anterior sobre queries Perplexity não persistirem foi **substituída** pelo contrato posterior de `[perplexity_draft]`, que persiste somente rascunho não autorizativo. Não classificar draft restaurado como consentimento.
- **#600:** as correções de apresentação #633 não constituem prova de scores novos; o cálculo canônico pode permanecer numericamente inalterado enquanto falta decisão de semântica #601/#602.
- **#639:** política incremental verifica novos nomes, não certifica migração dos 238 anteriores. Renomear arquivos históricos não tem prioridade sobre falhas P1 ou gates físico/metodológicos.
